import logging
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from app.models.job import JobBase, Salary
from app.parsers.base import BaseParser, format_category

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
}


NOFLUFFJOBS_BASE = "https://nofluffjobs.com"
NOFLUFFJOBS_LISTING = "https://nofluffjobs.com/pl"
NOFLUFFJOBS_API = "https://nofluffjobs.com/api/posting"


class NoFluffJobsParser(BaseParser):
    def can_handle(self, url: str) -> bool:
        return "nofluffjobs.com" in url

    @staticmethod
    def fetch_all_postings() -> list[dict]:
        """Fetch all postings from the NoFluffJobs JSON API."""
        resp = requests.get(NOFLUFFJOBS_API, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return data.get("postings", [])

    @staticmethod
    def parse_api_posting(posting: dict) -> JobBase:
        """Convert an API posting dict into a JobBase without extra HTTP requests."""
        url_slug = posting.get("url", posting.get("id", ""))
        url = f"{NOFLUFFJOBS_BASE}/pl/job/{url_slug}"

        title = posting.get("title", "")
        company = posting.get("name", "")

        cat_data = posting.get("category")
        category_raw = None
        if isinstance(cat_data, dict):
            category_raw = cat_data.get("name") or cat_data.get("id")
        elif isinstance(cat_data, str) and cat_data:
            category_raw = cat_data
        category = format_category(category_raw)

        locations = []
        loc_data = posting.get("location", {})
        for place in loc_data.get("places", []):
            city = place.get("city", "")
            if city and city not in locations:
                locations.append(city)

        fully_remote = loc_data.get("fullyRemote", False) or posting.get("fullyRemote", False)
        work_type = "Remote" if fully_remote else ("Hybrid" if loc_data.get("hybridDesc") else None)

        sal_data = posting.get("salary")
        salary = None
        if sal_data and sal_data.get("from") is not None:
            sal_type = (sal_data.get("type") or "").upper()
            if sal_type == "B2B":
                emp_type_label = "B2B"
            elif sal_type in ("PERMANENT", "UOP"):
                emp_type_label = "Permanent"
            else:
                emp_type_label = sal_type
            salary = Salary(
                min=sal_data.get("from"),
                max=sal_data.get("to"),
                currency=(sal_data.get("currency") or "PLN").upper(),
                type=emp_type_label,
            )

        skills = []
        tiles = posting.get("tiles", {})
        for tile in tiles.get("values", []):
            if tile.get("type") == "requirement":
                val = tile.get("value", "")
                if val and val not in skills:
                    skills.append(val)

        seniority_list = posting.get("seniority", [])
        seniority = seniority_list[0].capitalize() if seniority_list else None

        emp_types = []
        if salary and salary.type:
            emp_types.append(salary.type)

        posted_ts = posting.get("posted")
        date_published = None
        if posted_ts:
            try:
                date_published = datetime.fromtimestamp(posted_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                pass

        return JobBase(
            url=url,
            source="nofluffjobs.com",
            title=title,
            company=company,
            location=locations,
            salary=salary,
            skills_required=skills,
            skills_nice_to_have=[],
            seniority=seniority,
            work_type=work_type,
            employment_types=emp_types,
            description="",
            category=category,
            date_published=date_published,
            date_expires=None,
        )

    def parse(self, url: str) -> JobBase:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        title = self._extract_title(soup)
        company = self._extract_company(soup)
        location = self._extract_locations(soup)
        salary = self._extract_salary(soup)
        skills_required, skills_nice = self._extract_skills(soup)
        seniority = self._extract_seniority(soup)
        work_type = self._extract_work_type(soup)
        employment_types = self._extract_employment_types(soup, salary)
        description = self._extract_description(soup)
        date_expires = self._extract_expiry(soup)

        category = self._extract_category_from_url(url)

        return JobBase(
            url=url,
            source="nofluffjobs.com",
            title=title,
            company=company,
            location=location,
            salary=salary,
            skills_required=skills_required,
            skills_nice_to_have=skills_nice,
            seniority=seniority,
            work_type=work_type,
            employment_types=employment_types,
            description=description,
            category=category,
            date_published=None,
            date_expires=date_expires,
        )

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        h1 = soup.find("h1")
        return h1.get_text(strip=True) if h1 else ""

    @staticmethod
    def _extract_company(soup: BeautifulSoup) -> str:
        # Company name usually follows h1 in a separate element
        h1 = soup.find("h1")
        if h1:
            sibling = h1.find_next_sibling()
            if sibling:
                return sibling.get_text(strip=True)
            parent = h1.parent
            if parent:
                for child in parent.children:
                    text = getattr(child, "get_text", lambda **_: "")(**{"strip": True})
                    if text and text != h1.get_text(strip=True):
                        return text

        # Fallback: look in the page title
        title_tag = soup.find("title")
        if title_tag:
            parts = title_tag.get_text().split("|")
            for part in parts:
                part = part.strip()
                if part and "No Fluff" not in part and "Praca" not in part:
                    tokens = part.split()
                    if len(tokens) <= 6:
                        return part
        return ""

    @staticmethod
    def _extract_locations(soup: BeautifulSoup) -> list[str]:
        KNOWN_CITIES = [
            "Warszawa", "Kraków", "Wrocław", "Gdańsk", "Poznań", "Łódź",
            "Katowice", "Lublin", "Szczecin", "Bydgoszcz", "Białystok",
            "Gdynia", "Rzeszów", "Toruń", "Kielce", "Olsztyn", "Opole",
            "Gliwice", "Zielona Góra", "Radom", "Sosnowiec", "Bielsko-Biała",
        ]
        SKIP_WORDS = {
            "job", "backend", "ai", "frontend", "devops", "fullstack",
            "data", "testing", "security", "mobile", "embedded", "pm",
            "Krak%C3%B3w",
        }

        locations = []
        text = soup.get_text()

        for city in KNOWN_CITIES:
            if city in text:
                locations.append(city)

        if not locations:
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/pl/" in href and "criteria" in href:
                    decoded = requests.utils.unquote(href)
                    for city in KNOWN_CITIES:
                        if city in decoded and city not in locations:
                            locations.append(city)

        return locations

    @staticmethod
    def _extract_salary(soup: BeautifulSoup) -> Salary | None:
        text = soup.get_text()
        # Normalize non-breaking spaces and other whitespace variants to regular spaces
        normalized = text.replace("\xa0", " ").replace("\u202f", " ")

        patterns = [
            # "13 000 – 17 500 PLN" or "4 204.23 - 7 287.33 USD"
            re.compile(r"(\d[\d\s]*(?:[.,]\d+)?)\s*[–\-]\s*(\d[\d\s]*(?:[.,]\d+)?)\s*(PLN|USD|EUR|GBP|CHF)"),
            # "13,000 – 17,500 PLN" (comma-separated thousands)
            re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*[–\-]\s*(\d[\d,]*(?:\.\d+)?)\s*(PLN|USD|EUR|GBP|CHF)"),
        ]

        for pattern in patterns:
            match = pattern.search(normalized)
            if not match:
                continue

            min_str = match.group(1).strip().replace(" ", "").replace(",", "")
            max_str = match.group(2).strip().replace(" ", "").replace(",", "")
            currency = match.group(3)

            try:
                min_val = float(min_str)
                max_val = float(max_str)
            except ValueError:
                continue
            if max_val < 500:
                continue

            contract_type = ""
            context = normalized[max(0, match.start() - 200): match.end() + 200]
            if "B2B" in context:
                contract_type = "B2B"
            elif "UoP" in context or "Permanent" in context or "umowa o prac" in context.lower():
                contract_type = "Permanent"

            return Salary(min=min_val, max=max_val, currency=currency, type=contract_type)

        return None

    @staticmethod
    def _extract_skills(soup: BeautifulSoup) -> tuple[list[str], list[str]]:
        required = []
        nice_to_have = []
        current_list = required

        headings = soup.find_all("h2")
        for heading in headings:
            text = heading.get_text(strip=True).lower()
            if "obowiązkowe" in text or "required" in text or "must have" in text:
                ul = heading.find_next_sibling("ul")
                if ul:
                    for li in ul.find_all("li"):
                        skill = li.get_text(strip=True)
                        if skill and len(skill) < 50:
                            required.append(skill)
            elif "mile widziane" in text or "nice to have" in text:
                ul = heading.find_next_sibling("ul")
                if ul:
                    for li in ul.find_all("li"):
                        skill = li.get_text(strip=True)
                        if skill and len(skill) < 50:
                            nice_to_have.append(skill)

        # Fallback: look for skill lists by scanning all <ul> near headings
        if not required:
            all_text = soup.get_text()
            # Common skill section markers on nofluffjobs
            for section in soup.find_all(["section", "div"]):
                section_text = section.get_text(strip=True).lower()
                if "obowiązkowe" in section_text or "required" in section_text:
                    for li in section.find_all("li"):
                        skill = li.get_text(strip=True)
                        if skill and len(skill) < 50 and skill not in required:
                            current_list = required
                            current_list.append(skill)
                elif "mile widziane" in section_text or "nice to have" in section_text:
                    for li in section.find_all("li"):
                        skill = li.get_text(strip=True)
                        if skill and len(skill) < 50 and skill not in nice_to_have:
                            nice_to_have.append(skill)

        return required, nice_to_have

    @staticmethod
    def _extract_seniority(soup: BeautifulSoup) -> str | None:
        text = soup.get_text()
        for level in ["Junior", "Mid", "Senior", "Lead", "Expert"]:
            if level in text:
                return level
        return None

    @staticmethod
    def _extract_work_type(soup: BeautifulSoup) -> str | None:
        text = soup.get_text().lower()
        if "zdalnie" in text or "remote" in text or "w pełni zdalnie" in text:
            if "hybryd" in text:
                return "Hybrid"
            return "Remote"
        if "hybryd" in text or "hybrid" in text:
            return "Hybrid"
        if "stacjonarnie" in text or "onsite" in text or "on-site" in text:
            return "Onsite"
        return None

    @staticmethod
    def _extract_employment_types(soup: BeautifulSoup, salary: Salary | None) -> list[str]:
        text = soup.get_text()
        types = []
        if "B2B" in text:
            types.append("B2B")
        if "UoP" in text or "umowa o pracę" in text.lower() or "Permanent" in text:
            types.append("Permanent")
        if not types and salary and salary.type:
            types.append(salary.type)
        return types

    @staticmethod
    def _extract_description(soup: BeautifulSoup) -> str:
        desc_parts = []
        for heading in soup.find_all("h2"):
            text = heading.get_text(strip=True).lower()
            if any(kw in text for kw in ["opis", "description", "zakres", "responsibilities", "wymagań"]):
                sibling = heading.find_next_sibling()
                while sibling and sibling.name != "h2":
                    part = sibling.get_text(separator="\n", strip=True)
                    if part:
                        desc_parts.append(part)
                    sibling = sibling.find_next_sibling()
        return "\n\n".join(desc_parts)

    @staticmethod
    def _extract_category_from_url(url: str) -> str | None:
        KNOWN = {
            "backend": "Backend", "frontend": "Frontend", "fullstack": "Fullstack",
            "devops": "DevOps", "data": "Data", "mobile": "Mobile",
            "testing": "Testing", "security": "Security", "embedded": "Embedded",
            "pm": "PM", "ai": "AI", "game": "Game", "analytics": "Analytics",
            "erp": "ERP", "support": "Support", "architecture": "Architecture",
        }
        parts = url.rstrip("/").split("/")
        for part in reversed(parts):
            low = part.lower()
            if low in KNOWN:
                return KNOWN[low]
        return None

    @staticmethod
    def _extract_expiry(soup: BeautifulSoup) -> str | None:
        text = soup.get_text()
        match = re.search(r"(?:ważna do|valid until)[:\s]*(\d{2}[./]\d{2}[./]\d{4})", text, re.I)
        if match:
            raw = match.group(1)
            parts = re.split(r"[./]", raw)
            if len(parts) == 3:
                return f"{parts[2]}-{parts[1]}-{parts[0]}"
        return None
