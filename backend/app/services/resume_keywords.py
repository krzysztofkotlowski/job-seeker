"""Extract keywords/skills from resume PDF for matching against job skills."""

import io
import re

try:
    from pypdf import PdfReader
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

# Common stopwords (English + Polish) to drop from raw text
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of",
    "with", "by", "from", "as", "is", "was", "are", "were", "been", "be",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "can", "this", "that", "these", "those",
    "i", "you", "he", "she", "it", "we", "they", "my", "your", "his", "her",
    "its", "our", "their", "me", "him", "us", "them",
    "oraz", "jest", "sie", "się", "nie", "na", "w", "do", "od", "po", "za",
    "przy", "przed", "nad", "pod", "dla", "bez", "z", "o", "u", "i", "ale",
    "czy", "że", "co", "jak", "gdy", "gdzie", "który", "która", "które",
}


def _tokenize(text: str) -> set[str]:
    """Lowercase, split on non-letters/numbers, drop short and stopwords."""
    if not text:
        return set()
    text = text.replace("\n", " ").replace("\r", " ")
    # Keep words (letters, digits, optional hyphens)
    tokens = re.findall(r"[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)*", text)
    out = set()
    for t in tokens:
        t = t.lower().strip()
        if len(t) < 2:
            continue
        if t in STOPWORDS:
            continue
        out.add(t)
    return out


def _match_known_skills_in_text(text: str, known_skills: set[str]) -> set[str]:
    """Return skill names that appear in text (word-boundary match)."""
    if not text or not known_skills:
        return set()
    text_lower = text.lower()
    found = set()
    for skill in known_skills:
        pattern = re.escape(skill.lower())
        if re.search(r"(?:^|[\s,;()\[\]/|.]){}(?:[\s,;()\[\]/|.]|$)".format(pattern), text_lower):
            found.add(skill)
    return found


def extract_text_from_pdf(content: bytes) -> str:
    """Extract raw text from PDF bytes. Raises ValueError on invalid PDF."""
    if not HAS_PDF:
        raise ValueError("PDF support not available. Install pypdf.")
    if not content:
        raise ValueError("PDF file is empty.")
    if content[:4] != b"%PDF":
        raise ValueError("File does not look like a PDF (missing %PDF header).")
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception as e:
        raise ValueError(f"Could not read PDF: {e!s}") from e
    text_parts = []
    try:
        for page in reader.pages:
            try:
                text_parts.append(page.extract_text() or "")
            except Exception:
                pass
    except Exception as e:
        raise ValueError(f"Could not read PDF pages: {e!s}") from e
    return " ".join(text_parts)


def extract_keywords_from_text(text: str, known_skills: set[str] | None = None) -> set[str]:
    """Extract keywords from resume text. Uses raw tokens + known skill names found in text."""
    keywords = _tokenize(text)
    if known_skills:
        keywords |= _match_known_skills_in_text(text, known_skills)
    return keywords


def extract_keywords_from_pdf(content: bytes, known_skills: set[str] | None = None) -> set[str]:
    """Extract keywords from PDF bytes. Uses raw tokens + known skill names found in text.
    When known_skills is empty or sparse, raw tokens are returned to avoid empty results."""
    text = extract_text_from_pdf(content)
    return extract_keywords_from_text(text, known_skills)
