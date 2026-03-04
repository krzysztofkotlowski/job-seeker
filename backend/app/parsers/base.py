import re
from abc import ABC, abstractmethod

from app.models.job import JobBase

CATEGORY_MAP = {
    "businessintelligence": "Business Intelligence",
    "businessanalysis": "Business Analysis",
    "productmanagement": "Product Management",
    "projectmanager": "Project Manager",
    "gamedev": "Game Dev",
    "devops": "DevOps",
    "ai/ml": "AI / ML",
    "ux/ui": "UX / UI",
    "fullstack": "Fullstack",
    "backend": "Backend",
    "frontend": "Frontend",
    "mobile": "Mobile",
    "embedded": "Embedded",
    "testing": "Testing",
    "security": "Security",
    "architecture": "Architecture",
    "data": "Data",
    "erp": "ERP",
    "support": "Support",
    "pm": "PM",
    "agile": "Agile",
    "hr": "HR",
    "other": "Other",
}


def format_category(raw: str | None) -> str | None:
    """Normalize category slugs into human-readable names."""
    if not raw:
        return None
    key = raw.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    if key in CATEGORY_MAP:
        return CATEGORY_MAP[key]
    if raw.lower() in CATEGORY_MAP:
        return CATEGORY_MAP[raw.lower()]
    # Fallback: insert spaces before uppercase runs and title-case
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw)
    spaced = re.sub(r"[-_]", " ", spaced)
    return spaced.strip().title() if spaced.strip() else None


class BaseParser(ABC):
    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True if this parser can handle the given URL."""

    @abstractmethod
    def parse(self, url: str) -> JobBase:
        """Fetch the URL and return parsed job data."""
