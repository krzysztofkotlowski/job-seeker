"""LLM-based skill extraction from resume text. Complements rule-based extraction."""

import json
import logging
import re

from app.services.llm_service import LLMRequestError, OpenAIStreamError

log = logging.getLogger(__name__)

SKILL_EXTRACTION_SYSTEM = """You are a resume parser. Extract technical and professional skills from the resume text.
Output ONLY a JSON object with this exact structure: {"skills": ["Skill1", "Skill2", ...]}
- Include programming languages, frameworks, tools, methodologies, soft skills.
- Normalize synonyms: use "React" not "React.js", "Python" not "Python 3", "JavaScript" not "JS".
- Use canonical names (e.g. "Docker" not "Docker containers").
- Return 5-50 skills. No duplicates. No explanations."""

_MAX_TEXT_LEN = 6000  # chars to avoid token limits


def _truncate_for_prompt(text: str) -> str:
    if not text or len(text) <= _MAX_TEXT_LEN:
        return (text or "").strip()
    return text.strip()[: _MAX_TEXT_LEN] + "\n\n[truncated]"


def _parse_skills_json(raw: str) -> set[str]:
    """Parse LLM response into a set of skill strings."""
    if not raw or not raw.strip():
        return set()
    text = raw.strip()
    # Try to extract JSON block
    match = re.search(r"\{[^{}]*\"skills\"[^{}]*\[.*?\]\s*[^{}]*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    try:
        data = json.loads(text)
        skills = data.get("skills")
        if isinstance(skills, list):
            return {str(s).strip() for s in skills if s and str(s).strip()}
    except json.JSONDecodeError:
        pass
    # Fallback: look for ["x","y"] pattern
    match = re.search(r"\[\s*\"([^\"]+)\"(?:\s*,\s*\"([^\"]+)\")*\s*\]", text)
    if match:
        first = match.group(1)
        rest = match.groups()[1:] if len(match.groups()) > 1 else []
        return {first.strip()} | {r.strip() for r in rest if r}
    return set()


async def extract_skills_from_text_llm(
    text: str,
    ai_config: dict | None = None,
) -> set[str]:
    """
    Use LLM to extract skills from resume text. Returns empty set on failure.
    ai_config from get_ai_config(db); uses provider and API keys.
    """
    if not text or not text.strip():
        return set()
    truncated = _truncate_for_prompt(text)
    messages = [
        {"role": "system", "content": SKILL_EXTRACTION_SYSTEM},
        {"role": "user", "content": f"Extract skills from this resume:\n\n{truncated}"},
    ]
    provider = (ai_config or {}).get("provider", "ollama")
    try:
        if provider == "openai" and (ai_config or {}).get("openai_api_key"):
            from app.services.llm_service import _chat_openai

            result, _ = await _chat_openai(
                messages,
                api_key=ai_config["openai_api_key"],
                model=(ai_config or {}).get("openai_llm_model", "gpt-4o-mini"),
                max_tokens=500,
                temperature=0.1,
                timeout=30,
            )
            if result:
                return _parse_skills_json(result)
        else:
            from app.services.llm_service import _chat

            result = await _chat(
                messages,
                max_tokens=500,
                temperature=0.1,
                timeout=30,
                model=(ai_config or {}).get("llm_model"),
            )
            if isinstance(result, tuple):
                text_out, _ = result
            else:
                text_out = result
            if text_out:
                return _parse_skills_json(text_out)
    except (OpenAIStreamError, LLMRequestError) as e:
        log.debug("LLM skill extraction failed (skipping): %s", e)
    except Exception as e:
        log.warning("LLM skill extraction error: %s", e)
    return set()
