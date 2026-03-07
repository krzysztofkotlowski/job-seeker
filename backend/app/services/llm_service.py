"""LLM service: summarize resume-job matches via Ollama API."""

import json
import logging
import os
import re
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

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

DEFAULT_LLM_MODEL = "phi3:mini"


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
        max_output_tokens = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", "1024") or "1024")
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


async def check_ollama_health() -> bool:
    """
    Verify Ollama is reachable and the chat model is loaded.
    Returns True if healthy, False otherwise.
    """
    cfg = get_llm_config()
    if not cfg.url:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{cfg.url}/api/tags")
            if resp.status_code != 200:
                return False
            models = resp.json().get("models") or []
            return any(
                m.get("name", "").startswith(cfg.model) or cfg.model in m.get("name", "")
                for m in models
            )
    except Exception as e:
        log.debug("Ollama health check failed: %s", e)
        return False


async def _chat(
    messages: list[dict],
    stream: bool = False,
    max_tokens: int | None = None,
    timeout: int | None = None,
) -> str | None:
    """
    Low-level Ollama chat. Returns full text when stream=False, None on error.
    """
    cfg = get_llm_config()
    if not cfg.url:
        return None
    if max_tokens is None:
        max_tokens = cfg.max_output_tokens
    effective_timeout = timeout if timeout is not None else cfg.summarize_timeout

    url = f"{cfg.url}/api/chat"
    payload = {
        "model": cfg.model,
        "messages": messages,
        "stream": stream,
        "options": {"num_predict": max_tokens},
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
                return (msg.get("content") or "").strip() or None
    except httpx.TimeoutException:
        log.warning("LLM request timed out after %ds", effective_timeout)
        return None
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
            f" | Ollama response: {err_body}" if err_body else "",
        )
        return None
    except Exception as e:
        log.warning("LLM request failed: %s", e)
        return None


async def summarize_resume_match(
    extracted_skills: list[str],
    matches: list[dict],
    by_category: list[dict],
    timeout: int | None = None,
) -> str | None:
    """
    Call Ollama to generate a human-readable summary of the resume-job match.
    Returns None if LLM is disabled, unavailable, or errors.
    """
    if not extracted_skills and not by_category:
        return None

    prompt = _build_prompt(extracted_skills, matches or [], by_category)
    messages = [
        {"role": "system", "content": SYSTEM_MSG},
        {"role": "user", "content": prompt},
    ]

    text = await _chat(messages, stream=False, timeout=timeout)
    if text:
        return _ensure_markdown(text)
    return None


async def summarize_resume_match_stream(
    extracted_skills: list[str],
    matches: list[dict],
    by_category: list[dict],
    timeout: int | None = None,
):
    """
    Stream summary chunks from Ollama. Yields text chunks as they arrive.
    """
    if not extracted_skills and not by_category:
        return

    prompt = _build_prompt(extracted_skills, matches or [], by_category)
    messages = [
        {"role": "system", "content": SYSTEM_MSG},
        {"role": "user", "content": prompt},
    ]

    cfg = get_llm_config()
    if not cfg.url:
        return

    url = f"{cfg.url}/api/chat"
    effective_timeout = timeout if timeout is not None else cfg.summarize_timeout
    payload = {
        "model": cfg.model,
        "messages": messages,
        "stream": True,
        "options": {"num_predict": cfg.max_output_tokens},
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
                            yield chunk
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
    except httpx.TimeoutException:
        log.warning("LLM stream timed out after %ds", effective_timeout)
    except httpx.HTTPStatusError as e:
        log.warning("LLM API error: %s", e)
    except Exception as e:
        log.warning("LLM stream failed: %s", e)
