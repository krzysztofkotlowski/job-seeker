"""LLM service: summarize resume-job matches via a self-hosted runtime or OpenAI."""

import asyncio
import json
import logging
import os
import re
import random
from dataclasses import dataclass

import httpx

from app.services.self_hosted_runtime_service import (
    get_self_hosted_runtime_status,
    is_self_hosted_model_ready,
)

log = logging.getLogger(__name__)

# Retry config for OpenAI 429 (user prefers no retries; set to 1 = single attempt)
_OPENAI_MAX_RETRIES = int(os.environ.get("OPENAI_MAX_RETRIES", "1") or "1")
_OPENAI_BASE_DELAY = 2
_OPENAI_MAX_DELAY = 60


class OpenAIStreamError(Exception):
    """Raised when OpenAI stream fails with a user-friendly message."""

    pass


class LLMRequestError(Exception):
    """Raised when the self-hosted runtime request fails with a user-facing message."""

    pass


def _parse_openai_error(response: httpx.Response) -> str:
    """Parse OpenAI error response into a user-friendly message."""
    try:
        body = response.json()
        err = body.get("error") or {}
        code = (err.get("code") or err.get("type") or "").lower()
        msg = (err.get("message") or "").strip()
        if "insufficient_quota" in code or "quota" in msg.lower():
            return "OpenAI quota exceeded. Check your billing at platform.openai.com."
        if response.status_code == 429:
            return "OpenAI rate limit exceeded. Please wait a few minutes and try again."
        if response.status_code in (401, 403):
            return "OpenAI API key invalid or unauthorized."
        if msg:
            return f"AI summary failed: {msg[:200]}"
    except Exception:
        pass
    return f"AI summary failed: HTTP {response.status_code}"


def _parse_self_hosted_error(response: httpx.Response) -> str:
    """Parse self-hosted runtime error payload into a user-friendly message."""
    try:
        body = response.json()
        if isinstance(body, dict):
            if isinstance(body.get("error"), str) and body["error"].strip():
                return body["error"].strip()[:300]
            detail = body.get("detail")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()[:300]
    except Exception:
        pass
    text = (response.text or "").strip()
    if text:
        return text[:300]
    return f"Self-hosted runtime error: HTTP {response.status_code}"


def _is_retryable_openai_error(exc: BaseException) -> bool:
    """Return True if the OpenAI error is retryable (429 rate limit, not quota)."""
    if not isinstance(exc, httpx.HTTPStatusError):
        return False
    resp = getattr(exc, "response", None)
    if not resp or resp.status_code != 429:
        return False
    try:
        body = resp.json()
        err = body.get("error") or {}
        code = (err.get("code") or err.get("type") or "").lower()
        return "insufficient_quota" not in code
    except Exception:
        return True  # If we can't parse, assume retryable


def _get_openai_retry_delay(response: httpx.Response, attempt: int) -> float:
    """
    Get delay in seconds for retry. Uses Retry-After or x-ratelimit-reset-* headers
    when present, otherwise exponential backoff with jitter.
    """
    # Retry-After: seconds (or HTTP-date)
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return min(float(retry_after), _OPENAI_MAX_DELAY)
        except ValueError:
            pass

    # x-ratelimit-reset-requests: e.g. "33s", "1m0s", "6m0s"
    reset = response.headers.get("x-ratelimit-reset-requests") or response.headers.get(
        "x-ratelimit-reset-tokens"
    )
    if reset:
        seconds = _parse_duration(reset)
        if seconds is not None:
            return min(seconds, _OPENAI_MAX_DELAY)

    # Exponential backoff with jitter (OpenAI-recommended)
    delay = min(_OPENAI_BASE_DELAY**attempt, _OPENAI_MAX_DELAY)
    jitter = delay * 0.1 * random.random()
    return delay + jitter


def _parse_duration(s: str) -> float | None:
    """Parse duration like '33s', '1m0s', '6m0s' into seconds."""
    s = (s or "").strip().lower()
    if not s:
        return None
    total = 0.0
    i = 0
    while i < len(s):
        num = ""
        while i < len(s) and s[i].isdigit():
            num += s[i]
            i += 1
        if not num:
            i += 1
            continue
        unit = ""
        while i < len(s) and s[i].isalpha():
            unit += s[i]
            i += 1
        n = float(num)
        if unit == "s":
            total += n
        elif unit == "m":
            total += n * 60
        elif unit == "h":
            total += n * 3600
        else:
            total += n  # assume seconds
    return total if total > 0 else None


# Patterns that may indicate prompt injection attempts
_INJECTION_PATTERNS = (
    r"ignore\s+(previous|all|above)\s+instructions",
    r"disregard\s+(previous|all|above)",
    r"you\s+are\s+now\s+",
    r"pretend\s+you\s+are",
    r"act\s+as\s+if\s+you",
    r"system\s*:\s*",
    r"<\|[a-z_]+\|>",  # special tokens
)
_INJECTION_RE = re.compile("|".join(f"({p})" for p in _INJECTION_PATTERNS), re.IGNORECASE)

DEFAULT_LLM_MODEL = "qwen2.5:7b"


@dataclass
class LLMConfig:
    """Validated LLM configuration from environment."""

    url: str
    model: str
    timeout: int
    summarize_timeout: int
    max_output_tokens: int

    @classmethod
    def from_env(cls) -> "LLMConfig":
        url = (os.environ.get("LLM_URL", "") or "").rstrip("/")
        model = os.environ.get("LLM_MODEL", DEFAULT_LLM_MODEL) or DEFAULT_LLM_MODEL
        timeout = int(os.environ.get("LLM_TIMEOUT", "30") or "30")
        summarize_timeout = int(os.environ.get("LLM_SUMMARIZE_TIMEOUT", "90") or "90")
        max_output_tokens = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", "400") or "400")
        return cls(
            url=url,
            model=model,
            timeout=timeout,
            summarize_timeout=summarize_timeout,
            max_output_tokens=max_output_tokens,
        )


def _load_config() -> LLMConfig:
    return LLMConfig.from_env()


_config: LLMConfig | None = None


def get_llm_config() -> LLMConfig:
    global _config
    if _config is None:
        _config = _load_config()
    return _config


SYSTEM_MSG = (
    "You are a career advisor. The user message contains resume match data (categories and skills). "
    "Output ONLY: ## Your strongest fields, then 1-2 sentences per category (strengths, skills to add). "
    "Do NOT list jobs. Use markdown: ## headers, **bold**, - lists. Be concise."
)


_ECHO_PREFIXES = (
    "Format:",
    "Resume skills:",
    "By role/field",
    "Do not repeat",
    "TASK:",
    "Section 1:",
    "Section 2:",
    "Section 3:",
    "Categories:",
    "Jobs to recommend:",
    "Write the analysis",
    "Analyze the data",
    "Use ONLY",
    "I don't have access",
    "I don't have access to",
    "here's an example of how",
)

_CATEGORY_MATCH = re.compile(r"^(.+?):\s*match\s*(\d+)/100\.?\s*(.+)$", re.MULTILINE)

# Approximate chars per token for truncation (conservative)
_CHARS_PER_TOKEN = 4
_MAX_PROMPT_CHARS = 2048 * _CHARS_PER_TOKEN


_DISCLAIMER_PHRASES = (
    "i don't have access",
    "i cannot see",
    "i don't have access to",
    "i cannot access",
    "as an ai i",
    "i'm unable to see",
    "here's an example of how the output would look",
)


def _ensure_markdown(text: str) -> str:
    """
    Post-process plain text into basic markdown when model ignores formatting.
    Strips prompt echo, disclaimer paragraphs, converts "Category: match N/100" to bullets.
    """
    if not text or not text.strip():
        return text

    # Strip leading disclaimer paragraphs (e.g. "I don't have access to the user's input...")
    lowered = text.strip().lower()
    if any(p in lowered[:400] for p in _DISCLAIMER_PHRASES):
        paras = text.strip().split("\n\n")
        out = []
        for p in paras:
            pl = p.strip().lower()
            if any(d in pl for d in _DISCLAIMER_PHRASES) and len(pl) < 300:
                continue
            out.append(p)
        text = "\n\n".join(out).strip()
        if not text:
            return ""

    lines = text.strip().split("\n")
    filtered: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            filtered.append("")
            continue
        if any(stripped.startswith(p) for p in _ECHO_PREFIXES):
            continue
        filtered.append(stripped)

    cleaned = "\n".join(filtered)
    if not cleaned.strip():
        return text.strip()

    # Convert "Category: match N/100. Your strengths: X. Consider adding: Y" to markdown
    category_bullets: list[str] = []
    other_lines: list[str] = []
    for line in cleaned.split("\n"):
        line = line.strip()
        if not line:
            other_lines.append("")
            continue
        m = _CATEGORY_MATCH.match(line)
        if m:
            cat, score, rest = m.group(1).strip(), m.group(2), m.group(3).strip()
            category_bullets.append(f"- **{cat} ({score}/100)**: {rest}")
        else:
            other_lines.append(line)

    if category_bullets:
        section = "## Your strongest fields\n\n" + "\n".join(category_bullets)
        if other_lines:
            rest_lines = []
            for l in other_lines:
                if l.strip() == "Recommended jobs" or l.strip().startswith("Recommended jobs"):
                    rest_lines.append("## Recommended jobs")
                else:
                    rest_lines.append(l)
            rest = "\n".join(rest_lines).strip()
            if rest:
                section = section + "\n\n" + rest
        return section

    # Already has markdown structure
    if "##" in cleaned or "**" in cleaned or re.search(r"\[.+\]\(.+\)", cleaned):
        return cleaned

    # Fallback: short lines ending with colon as headers
    out: list[str] = []
    for line in cleaned.split("\n"):
        line = line.strip()
        if not line:
            out.append("")
            continue
        if len(line) < 60 and line.endswith(":"):
            out.append(f"## {line[:-1]}")
        else:
            out.append(line)
    return "\n\n".join(out)


def _sanitize_for_prompt(text: str, max_len: int = 500) -> str:
    """
    Sanitize user-provided text before including in LLM prompts.
    Reduces risk of prompt injection.
    """
    if not text or not isinstance(text, str):
        return ""
    # Keep only printable ASCII + common Unicode (letters, numbers, basic punct)
    cleaned = "".join(c for c in text if c.isprintable() or c in " \n\t")
    # Remove lines that match injection patterns
    lines = cleaned.split("\n")
    safe_lines = []
    for line in lines:
        stripped = line.strip()
        if _INJECTION_RE.search(stripped):
            continue
        safe_lines.append(line)
    result = "\n".join(safe_lines).strip()
    return result[:max_len] if len(result) > max_len else result


def _sanitize_skill(s: str) -> str:
    """Sanitize a single skill string."""
    if not s or not isinstance(s, str):
        return ""
    return _sanitize_for_prompt(s, max_len=80)


def _is_valid_url(u: str) -> bool:
    u = (u or "").strip()
    return len(u) > 20 and (u.startswith("http://") or u.startswith("https://"))


def _dedupe_matches(matches: list[dict]) -> list[dict]:
    """Deduplicate matches by (title, company)."""
    seen: set[tuple[str, str]] = set()
    deduped = []
    for m in matches:
        job = m.get("job") or {}
        key = (job.get("title", "") or "", job.get("company", "") or "")
        if key not in seen and key != ("", ""):
            seen.add(key)
            deduped.append(m)
    return deduped[:8]


def _build_prompt(
    extracted_skills: list[str],
    matches: list[dict],
    by_category: list[dict],
) -> str:
    """Build a short, structured prompt (skills and categories only; no jobs)."""
    # Sanitize user-provided content to reduce prompt injection risk (extracted_skills used via cat_lines)
    top_cats = sorted(by_category, key=lambda c: c.get("match_score", 0), reverse=True)[:5]
    cat_lines = []
    for c in top_cats:
        cat = _sanitize_for_prompt(str(c.get("category", "?")), max_len=50)
        score = c.get("match_score", 0)
        matching = c.get("matching_skills") or []
        to_add = c.get("skills_to_add") or []
        match_skills = ", ".join(_sanitize_skill(s.get("skill", "")) for s in matching[:6]) if matching else "none"
        add_skills = ", ".join(_sanitize_skill(s.get("skill", "")) for s in to_add[:4]) if to_add else "none"
        cat_lines.append(f"- {cat} ({score}/100): strengths: {match_skills}. Add: {add_skills}")

    prompt = f"""Analyze this resume match data. The data is provided here—do not say you lack access to it.

CATEGORIES (match scores):
{chr(10).join(cat_lines)}

Write your response: ## Your strongest fields, then 1-2 sentences per category (strengths, skills to add). Do NOT list jobs."""

    if len(prompt) > _MAX_PROMPT_CHARS:
        prompt = prompt[: _MAX_PROMPT_CHARS] + "\n\n[truncated]"
    return prompt


async def check_ollama_health(model: str | None = None) -> bool:
    """
    Verify the self-hosted runtime is reachable and the active chat model is ready.
    Uses model from DB when provided, else from env.
    Returns True if healthy, False otherwise.
    """
    cfg = get_llm_config()
    if not cfg.url:
        return False
    target_model = (model or cfg.model or "").strip() or cfg.model
    if not target_model:
        return False
    try:
        return is_self_hosted_model_ready(target_model)
    except Exception as e:
        log.debug("Self-hosted runtime health check failed: %s", e)
        return False


async def _chat_openai(
    messages: list[dict],
    *,
    api_key: str,
    model: str = "gpt-4o-mini",
    max_tokens: int = 2048,
    temperature: float = 0.3,
    stream: bool = False,
    timeout: int = 90,
) -> tuple[str | None, int | None]:
    """Call OpenAI chat completions API. Returns (text, usage_total_tokens). Raises OpenAIStreamError on failure."""
    if not api_key or not api_key.strip():
        raise OpenAIStreamError("OpenAI API key not configured.")
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    last_error = None
    for attempt in range(_OPENAI_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                text = (msg.get("content") or "").strip() or None
                usage = data.get("usage") or {}
                total = usage.get("total_tokens") or usage.get("completion_tokens")
                return (text, total)
        except httpx.TimeoutException as e:
            log.warning("OpenAI request timed out after %ds", timeout)
            raise OpenAIStreamError("Summary timed out. Try again.") from e
        except httpx.HTTPStatusError as e:
            last_error = e
            if _is_retryable_openai_error(e) and attempt < _OPENAI_MAX_RETRIES - 1:
                delay = _get_openai_retry_delay(e.response, attempt)
                log.warning(
                    "OpenAI 429 rate limit, retrying in %.1fs (attempt %d/%d)",
                    delay,
                    attempt + 1,
                    _OPENAI_MAX_RETRIES,
                )
                await asyncio.sleep(delay)
                continue
            log.warning("OpenAI API error: %s", e)
            raise OpenAIStreamError(_parse_openai_error(e.response)) from e
        except Exception as e:
            log.warning("OpenAI request failed: %s", e)
            raise OpenAIStreamError(f"AI summary failed: {e!s}") from e
    if last_error:
        raise OpenAIStreamError(_parse_openai_error(last_error.response)) from last_error
    raise OpenAIStreamError("AI summary failed.")


async def _chat_openai_stream(
    messages: list[dict],
    *,
    api_key: str,
    model: str = "gpt-4o-mini",
    max_tokens: int = 2048,
    temperature: float = 0.3,
    timeout: int = 90,
):
    """Stream OpenAI chat completions. Yields text chunks. Raises OpenAIStreamError on failure."""
    if not api_key or not api_key.strip():
        raise OpenAIStreamError("OpenAI API key not configured.")
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    last_error = None
    for attempt in range(_OPENAI_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            for choice in data.get("choices") or []:
                                delta = choice.get("delta") or {}
                                chunk = delta.get("content", "")
                                if chunk:
                                    yield chunk
                        except json.JSONDecodeError:
                            continue
            return
        except httpx.TimeoutException as e:
            log.warning("OpenAI stream timed out after %ds", timeout)
            raise OpenAIStreamError("Summary timed out. Try again.") from e
        except httpx.HTTPStatusError as e:
            last_error = e
            if _is_retryable_openai_error(e) and attempt < _OPENAI_MAX_RETRIES - 1:
                delay = _get_openai_retry_delay(e.response, attempt)
                log.warning(
                    "OpenAI 429 rate limit, retrying in %.1fs (attempt %d/%d)",
                    delay,
                    attempt + 1,
                    _OPENAI_MAX_RETRIES,
                )
                await asyncio.sleep(delay)
                continue
            log.warning("OpenAI API error: %s", e)
            raise OpenAIStreamError(_parse_openai_error(e.response)) from e
        except Exception as e:
            log.warning("OpenAI stream failed: %s", e)
            raise OpenAIStreamError(f"AI summary failed: {e!s}") from e
    if last_error:
        raise OpenAIStreamError(_parse_openai_error(last_error.response)) from last_error
    raise OpenAIStreamError("AI summary failed.")


async def _chat(
    messages: list[dict],
    stream: bool = False,
    max_tokens: int | None = None,
    timeout: int | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> str | tuple[str | None, int | None] | None:
    """
    Low-level self-hosted chat.
    Raises LLMRequestError when the runtime is unavailable or returns an error.
    """
    cfg = get_llm_config()
    if not cfg.url:
        raise LLMRequestError("Self-hosted runtime URL not configured.")
    effective_model = model or cfg.model
    if max_tokens is None:
        max_tokens = cfg.max_output_tokens
    effective_timeout = timeout if timeout is not None else cfg.summarize_timeout

    if effective_model and not is_self_hosted_model_ready(effective_model):
        runtime_status = get_self_hosted_runtime_status(selected_chat_model=effective_model)
        detail = (
            runtime_status.get("chat_error")
            or runtime_status.get("embedding_error")
            or f"Selected chat model '{effective_model}' is not ready in the self-hosted runtime."
        )
        raise LLMRequestError(str(detail))

    options: dict = {"num_predict": max_tokens}
    if temperature is not None:
        options["temperature"] = temperature

    url = f"{cfg.url}/api/chat"
    payload = {
        "model": effective_model,
        "messages": messages,
        "stream": stream,
        "options": options,
    }
    try:
        async with httpx.AsyncClient(timeout=effective_timeout) as client:
            if stream:
                full = ""
                async with client.stream("POST", url, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            msg = data.get("message") or {}
                            chunk = msg.get("content", "")
                            if chunk:
                                full += chunk
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
                return full or None
            else:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                msg = data.get("message") or {}
                text = (msg.get("content") or "").strip() or None
                eval_count = data.get("eval_count")
                return (text, eval_count)
    except httpx.TimeoutException:
        log.warning("LLM request timed out after %ds", effective_timeout)
        raise LLMRequestError("Self-hosted runtime timed out. Try again.") from None
    except httpx.HTTPStatusError as e:
        err_body = ""
        if hasattr(e, "response") and e.response is not None:
            try:
                err_body = e.response.text[:500] if e.response.text else ""
            except Exception:
                pass
        log.warning(
            "LLM API error: %s%s",
            e,
            f" | Runtime response: {err_body}" if err_body else "",
        )
        raise LLMRequestError(_parse_self_hosted_error(e.response)) from e
    except Exception as e:
        log.warning("LLM request failed: %s", e)
        raise LLMRequestError(f"AI summary failed: {e!s}") from e


async def summarize_resume_match(
    extracted_skills: list[str],
    matches: list[dict],
    by_category: list[dict],
    ai_config: dict | None = None,
    timeout: int | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> tuple[str | None, int | None]:
    """
    Call LLM to generate a human-readable summary of the resume-job match.
    Returns (summary_text, eval_count). summary_text is None if LLM is disabled, unavailable, or errors.
    ai_config from get_ai_config(db); when provider=openai uses OpenAI API.
    """
    if not extracted_skills and not by_category:
        return (None, None)

    prompt = _build_prompt(extracted_skills, matches or [], by_category)
    messages = [
        {"role": "system", "content": SYSTEM_MSG},
        {"role": "user", "content": prompt},
    ]

    provider = (ai_config or {}).get("provider", "ollama")
    effective_max = max_tokens or (ai_config or {}).get("max_output_tokens") or 400
    # Clamp for summary task — reduces 429 risk
    effective_max = min(effective_max, 500)
    effective_temp = temperature if temperature is not None else (ai_config or {}).get("temperature", 0.3)

    if provider == "openai" and (ai_config or {}).get("openai_api_key"):
        effective_model = model or (ai_config or {}).get("openai_llm_model", "gpt-4o-mini")
        text, eval_count = await _chat_openai(
            messages,
            api_key=ai_config["openai_api_key"],
            model=effective_model,
            max_tokens=effective_max,
            temperature=effective_temp,
            stream=False,
            timeout=timeout or 90,
        )
    else:
        effective_model = model or (ai_config or {}).get("llm_model")
        text, eval_count = await _chat(
            messages,
            stream=False,
            timeout=timeout,
            max_tokens=max_tokens or effective_max,
            model=effective_model,
            temperature=effective_temp,
        )

    if text:
        return (_ensure_markdown(text), eval_count)
    return (None, eval_count)


async def summarize_resume_match_stream(
    extracted_skills: list[str],
    matches: list[dict],
    by_category: list[dict],
    ai_config: dict | None = None,
    timeout: int | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
):
    """
    Stream summary chunks from LLM. Yields text chunks as they arrive.
    ai_config from get_ai_config(db); when provider=openai uses OpenAI API.
    """
    if not extracted_skills and not by_category:
        return

    prompt = _build_prompt(extracted_skills, matches or [], by_category)
    messages = [
        {"role": "system", "content": SYSTEM_MSG},
        {"role": "user", "content": prompt},
    ]

    provider = (ai_config or {}).get("provider", "ollama")
    effective_max = max_tokens or (ai_config or {}).get("max_output_tokens") or 400
    # Clamp for summary task — reduces 429 risk
    effective_max = min(effective_max, 500)
    effective_temp = temperature if temperature is not None else (ai_config or {}).get("temperature", 0.3)

    if provider == "openai" and (ai_config or {}).get("openai_api_key"):
        effective_model = model or (ai_config or {}).get("openai_llm_model", "gpt-4o-mini")
        try:
            async for chunk in _chat_openai_stream(
                messages,
                api_key=ai_config["openai_api_key"],
                model=effective_model,
                max_tokens=effective_max,
                temperature=effective_temp,
                timeout=timeout or 90,
            ):
                yield {"chunk": chunk}
        except OpenAIStreamError as e:
            yield {"error": str(e)}
        return

    cfg = get_llm_config()
    if not cfg.url:
        yield {"error": "Self-hosted runtime URL not configured."}
        return

    effective_model = model or (ai_config or {}).get("llm_model") or cfg.model
    effective_timeout = timeout if timeout is not None else cfg.summarize_timeout
    if effective_model and not is_self_hosted_model_ready(effective_model):
        runtime_status = get_self_hosted_runtime_status(selected_chat_model=effective_model)
        detail = (
            runtime_status.get("chat_error")
            or runtime_status.get("embedding_error")
            or f"Selected chat model '{effective_model}' is not ready in the self-hosted runtime."
        )
        yield {"error": str(detail)}
        return
    options: dict = {"num_predict": effective_max}
    if temperature is not None:
        options["temperature"] = temperature

    url = f"{cfg.url}/api/chat"
    payload = {
        "model": effective_model,
        "messages": messages,
        "stream": True,
        "options": options,
    }
    try:
        async with httpx.AsyncClient(timeout=effective_timeout) as client:
            async with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        msg = data.get("message") or {}
                        chunk = msg.get("content", "")
                        if chunk:
                            yield {"chunk": chunk}
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
    except httpx.TimeoutException:
        log.warning("LLM stream timed out after %ds", effective_timeout)
        yield {"error": "Summary timed out. Try again."}
    except httpx.HTTPStatusError as e:
        log.warning("LLM API error: %s", e)
        yield {"error": _parse_self_hosted_error(e.response)}
    except Exception as e:
        log.warning("LLM stream failed: %s", e)
        yield {"error": f"AI summary failed: {e!s}"}
