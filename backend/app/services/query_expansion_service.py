"""Query expansion for RAG: generate multiple query variants for richer retrieval."""

import json
import logging
import re

from app.services.llm_service import LLMRequestError, OpenAIStreamError

log = logging.getLogger(__name__)

QUERY_EXPANSION_SYSTEM = """You are a job search assistant. Given a list of resume skills, generate 2-3 short search query variants (each 3-8 words) that would find relevant job postings.
Output ONLY a JSON object: {"queries": ["query1", "query2", "query3"]}
Examples: ["Python backend developer", "Django FastAPI engineer", "Python API development"]
No explanations."""

_MAX_SKILLS = 30


async def expand_query_llm(
    skills: set[str],
    ai_config: dict | None = None,
    max_variants: int = 3,
) -> list[str]:
    """
    Use LLM to generate 2-3 query variants from skills. Returns [original] on failure.
    """
    if not skills:
        return []
    skill_list = sorted(skills)[:_MAX_SKILLS]
    original = " ".join(skill_list)
    messages = [
        {"role": "system", "content": QUERY_EXPANSION_SYSTEM},
        {"role": "user", "content": f"Skills: {', '.join(skill_list)}\n\nGenerate 2-3 search query variants:"},
    ]
    try:
        if ai_config and ai_config.get("provider") == "openai" and ai_config.get("openai_api_key"):
            from app.services.llm_service import _chat_openai

            result, _ = await _chat_openai(
                messages,
                api_key=ai_config["openai_api_key"],
                model=(ai_config or {}).get("openai_llm_model", "gpt-4o-mini"),
                max_tokens=150,
                temperature=0.2,
                timeout=15,
            )
            if result:
                queries = _parse_queries_json(result)
                if queries:
                    return [original] + [q for q in queries if q and q != original][:max_variants - 1]
        else:
            from app.services.llm_service import _chat

            out = await _chat(
                messages,
                max_tokens=150,
                temperature=0.2,
                timeout=15,
                model=(ai_config or {}).get("llm_model"),
            )
            if isinstance(out, tuple):
                text_out, _ = out
            else:
                text_out = out
            if text_out:
                queries = _parse_queries_json(text_out)
                if queries:
                    return [original] + [q for q in queries if q and q != original][:max_variants - 1]
    except (OpenAIStreamError, LLMRequestError) as e:
        log.debug("Query expansion failed: %s", e)
    except Exception as e:
        log.warning("Query expansion error: %s", e)
    return [original]


def _parse_queries_json(raw: str) -> list[str]:
    if not raw or not raw.strip():
        return []
    text = raw.strip()
    match = re.search(r"\{\s*\"queries\"\s*:\s*\[(.*?)\]\s*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads("{\"queries\": [" + match.group(1) + "]}")
            qs = data.get("queries", [])
            if isinstance(qs, list):
                return [str(q).strip() for q in qs if q and str(q).strip()]
        except json.JSONDecodeError:
            pass
    return []
