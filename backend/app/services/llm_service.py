"""LLM service: summarize resume-job matches via Ollama API."""

import logging
import os

import httpx

log = logging.getLogger(__name__)

LLM_URL = os.environ.get("LLM_URL", "").rstrip("/")
LLM_MODEL = os.environ.get("LLM_MODEL", "tinyllama")
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "30"))
# Longer timeout for on-demand summarize (small containers may need 90s+)
LLM_SUMMARIZE_TIMEOUT = int(os.environ.get("LLM_SUMMARIZE_TIMEOUT", "90"))


def _build_prompt(
    extracted_skills: list[str],
    matches: list[dict],
    by_category: list[dict],
) -> str:
    """Build a structured prompt for the LLM."""
    skills_str = ", ".join(sorted(extracted_skills)[:50])
    if len(extracted_skills) > 50:
        skills_str += f" (and {len(extracted_skills) - 50} more)"

    top_matches = matches[:5]
    matches_lines = []
    for m in top_matches:
        job = m.get("job") or {}
        title = job.get("title", "?")
        company = job.get("company", "?")
        matched = m.get("matched_skills") or []
        count = m.get("match_count", 0)
        matched_str = ", ".join(matched[:10]) if matched else "none"
        if len(matched) > 10:
            matched_str += f" (+{len(matched) - 10} more)"
        matches_lines.append(f"- {title} at {company}: matched {matched_str} ({count} skills)")

    top_cats = sorted(by_category, key=lambda c: c.get("match_score", 0), reverse=True)[:3]
    cat_lines = []
    for c in top_cats:
        cat = c.get("category", "?")
        score = c.get("match_score", 0)
        matching = c.get("matching_skills") or []
        to_add = c.get("skills_to_add") or []
        match_skills = ", ".join(s.get("skill", "") for s in matching[:8]) if matching else "none"
        add_skills = ", ".join(s.get("skill", "") for s in to_add[:5]) if to_add else "none"
        cat_lines.append(
            f"- {cat}: match {score}/100. Your strengths: {match_skills}. Consider adding: {add_skills}"
        )

    return f"""You are a career advisor. Summarize this resume-job match analysis in 2-4 short paragraphs. Be concise and actionable.

Resume skills: {skills_str}

Top job matches:
{chr(10).join(matches_lines)}

By role:
{chr(10).join(cat_lines)}

Write a concise, actionable summary for the job seeker."""


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
    if not LLM_URL:
        return None
    if not extracted_skills and not matches and not by_category:
        return None

    prompt = _build_prompt(extracted_skills, matches, by_category)
    url = f"{LLM_URL}/api/generate"
    payload = {
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    effective_timeout = timeout if timeout is not None else LLM_SUMMARIZE_TIMEOUT

    try:
        async with httpx.AsyncClient(timeout=effective_timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            text = data.get("response", "").strip()
            return text if text else None
    except httpx.TimeoutException:
        log.warning("LLM summarization timed out after %ds", effective_timeout)
        return None
    except httpx.HTTPStatusError as e:
        log.warning("LLM API error: %s", e)
        return None
    except Exception as e:
        log.warning("LLM summarization failed: %s", e)
        return None
