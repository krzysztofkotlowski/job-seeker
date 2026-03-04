import json
import re

import requests
from bs4 import BeautifulSoup

from app.models.job import JobBase, Salary
from app.parsers.base import BaseParser, format_category

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
}


JUSTJOIN_BASE = "https://justjoin.it"
JUSTJOIN_LISTING = "https://justjoin.it/job-offers/all-locations"
JUSTJOIN_OFFER_PREFIX = "https://justjoin.it/job-offer/"


class JustJoinParser(BaseParser):
    def can_handle(self, url: str) -> bool:
        return "justjoin.it" in url

    @staticmethod
    def scrape_listing_page(offset: int = 0) -> list[str]:
        """Scrape a JustJoin.it listing page and return offer URLs.

        Pagination uses ?from=N with 100 items per page.
        """
        url = f"{JUSTJOIN_LISTING}?from={offset}"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        urls: list[str] = []
        for match in re.findall(r'job-offer/([a-z0-9][a-z0-9-]+)', resp.text):
            full = JUSTJOIN_OFFER_PREFIX + match
            if full not in urls:
                urls.append(full)
        return urls

    def parse(self, url: str) -> JobBase:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        rsc_data = self._extract_rsc_data(soup)
        jsonld = self._extract_jsonld(soup)

        if rsc_data:
            return self._parse_rsc(rsc_data, jsonld, url)
        if jsonld:
            return self._parse_jsonld(jsonld, soup, url)
        return self._parse_html(soup, url)

    def _extract_rsc_data(self, soup: BeautifulSoup) -> dict | None:
        """Extract job data from Next.js RSC self.__next_f.push() payloads."""
        for script in soup.find_all("script"):
            text = script.string or ""
            if "self.__next_f.push" not in text:
                continue
            if '"slug"' not in text or '"companyName"' not in text:
                continue
            # Extract the JSON substring containing the offer data
            match = re.search(
                r'\{"slug":"[^"]+","title":"[^"]+","experienceLevel".*?"workplaceType":"[^"]*"',
                text,
            )
            if not match:
                match = re.search(
                    r'\{"slug":"[^"]+","title":"[^"]+","experienceLevel".*?"multilocation":\[.*?\]',
                    text,
                )
            if match:
                raw = match.group(0)
                # Find the complete JSON object by balancing braces
                start = text.index(raw[:50])
                depth = 0
                end = start
                for i in range(start, len(text)):
                    if text[i] == "{":
                        depth += 1
                    elif text[i] == "}":
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
        return None

    @staticmethod
    def _extract_jsonld(soup: BeautifulSoup) -> dict | None:
        for script in soup.find_all("script", type="application/ld+json"):
            if script.string:
                try:
                    data = json.loads(script.string)
                    if data.get("@type") == "JobPosting":
                        return data
                except json.JSONDecodeError:
                    pass
        return None

    def _parse_rsc(self, rsc: dict, jsonld: dict | None, url: str) -> JobBase:
        title = rsc.get("title", "")
        company = rsc.get("companyName", "")

        locations = []
        for loc in rsc.get("multilocation", []):
            city = loc.get("city", "")
            if city and city not in locations:
                locations.append(city)
        if not locations:
            city = rsc.get("city", "")
            if city:
                locations.append(city)

        salary = self._extract_salary_rsc(rsc)

        skills_required = []
        skills_nice = []
        for skill in rsc.get("requiredSkills", rsc.get("skills", [])):
            if isinstance(skill, dict):
                name = skill.get("name", "")
                if skill.get("level", 1) >= 3:
                    skills_required.append(name)
                else:
                    skills_nice.append(name)
            else:
                skills_required.append(str(skill))

        for skill in rsc.get("niceToHaveSkills", []):
            name = skill.get("name", skill) if isinstance(skill, dict) else str(skill)
            if name and name not in skills_nice:
                skills_nice.append(name)

        exp = rsc.get("experienceLevel", {})
        seniority = exp.get("label", exp.get("value", "")) if isinstance(exp, dict) else str(exp)

        work_type = rsc.get("workplaceType", "")

        cat_val = rsc.get("categoryId") or rsc.get("category", "")
        if isinstance(cat_val, dict):
            cat_str = cat_val.get("name") or cat_val.get("id") or ""
        else:
            cat_str = str(cat_val) if cat_val else ""
        category = format_category(cat_str)

        emp_types = []
        for et in rsc.get("employmentTypes", []):
            t = et.get("type", "")
            if t and t not in emp_types:
                emp_types.append(t)

        description = ""
        if jsonld:
            description = jsonld.get("description", "")
        if not description:
            description = rsc.get("body", "")

        date_published = rsc.get("publishedAt", "")
        if not date_published and jsonld:
            date_published = jsonld.get("datePosted", "")
        if date_published and "T" in date_published:
            date_published = date_published.split("T")[0]

        date_expires = ""
        if jsonld:
            date_expires = jsonld.get("validThrough", "")
        if date_expires and "T" in date_expires:
            date_expires = date_expires.split("T")[0]

        return JobBase(
            url=url,
            source="justjoin.it",
            title=title,
            company=company,
            location=locations,
            salary=salary,
            skills_required=skills_required,
            skills_nice_to_have=skills_nice,
            seniority=seniority.capitalize() if seniority else None,
            work_type=self._normalize_work_type(work_type),
            employment_types=emp_types,
            description=description,
            category=category,
            date_published=date_published or None,
            date_expires=date_expires or None,
        )

    @staticmethod
    def _detect_period(et: dict) -> str | None:
        """Extract pay period from an employment type entry."""
        for key in ("timeUnit", "period", "salaryPeriod"):
            val = et.get(key, "")
            if val:
                low = str(val).lower()
                if low in ("hour", "hourly", "h"):
                    return "hourly"
                if low in ("day", "daily", "d"):
                    return "daily"
                if low in ("month", "monthly", "m"):
                    return "monthly"
                if low in ("year", "yearly", "annual"):
                    return "yearly"
        return None

    @classmethod
    def _extract_salary_rsc(cls, rsc: dict) -> Salary | None:
        """Pick the best salary from RSC employment types (prefer PLN B2B, then USD B2B)."""
        emp_types = rsc.get("employmentTypes", [])
        for preferred_currency in ["PLN", "USD", "EUR"]:
            for et in emp_types:
                currency = (et.get("currency") or "").upper()
                if currency == preferred_currency and et.get("type") == "b2b" and not et.get("gross", True):
                    return Salary(
                        min=et.get("from"),
                        max=et.get("to"),
                        currency=currency,
                        type="B2B",
                        period=cls._detect_period(et),
                    )

        for et in emp_types:
            from_val = et.get("from")
            to_val = et.get("to")
            if from_val or to_val:
                return Salary(
                    min=from_val,
                    max=to_val,
                    currency=(et.get("currency") or "PLN").upper(),
                    type=et.get("type", "").upper() if et.get("type") else "",
                    period=cls._detect_period(et),
                )
        return None

    def _parse_jsonld(self, jsonld: dict, soup: BeautifulSoup, url: str) -> JobBase:
        title = jsonld.get("title", "")
        org = jsonld.get("hiringOrganization", {})
        company = org.get("name", "") if isinstance(org, dict) else ""

        locations = self._extract_locations_from_html(soup)
        if not locations:
            loc = jsonld.get("jobLocation", {})
            if isinstance(loc, dict):
                addr = loc.get("address", {})
                if isinstance(addr, dict):
                    city = addr.get("addressLocality", "")
                    if city:
                        locations.append(city)

        salary_data = jsonld.get("baseSalary", {})
        salary = None
        if isinstance(salary_data, dict):
            val = salary_data.get("value", {})
            if isinstance(val, dict):
                salary = Salary(
                    min=val.get("minValue"),
                    max=val.get("maxValue"),
                    currency=salary_data.get("currency", "PLN"),
                    type="",
                )

        emp_types = self._extract_employment_types_from_html(soup)
        if emp_types and salary:
            salary.type = emp_types[0]

        skills = self._extract_skills_from_html(soup)
        work_type_raw = jsonld.get("jobLocationType", "")
        seniority = self._extract_seniority_from_html(soup)
        category = self._extract_category_from_url(url)

        return JobBase(
            url=url,
            source="justjoin.it",
            title=title,
            company=company,
            location=locations,
            salary=salary,
            skills_required=skills,
            skills_nice_to_have=[],
            seniority=seniority,
            work_type=self._normalize_work_type(work_type_raw),
            employment_types=emp_types,
            description=jsonld.get("description", ""),
            category=category,
            date_published=jsonld.get("datePosted", "").split("T")[0] if jsonld.get("datePosted") else None,
            date_expires=jsonld.get("validThrough", "").split("T")[0] if jsonld.get("validThrough") else None,
        )

    @staticmethod
    def _extract_skills_from_html(soup: BeautifulSoup) -> list[str]:
        skills = []
        skip = {"Tech stack", "Office location", "Job description", "Apply", "Save"}
        for h4 in soup.find_all("h4"):
            name = h4.get_text(strip=True)
            if name and len(name) < 50 and name not in skip:
                skills.append(name)
        return skills

    @staticmethod
    def _extract_seniority_from_html(soup: BeautifulSoup) -> str | None:
        text = soup.get_text()
        for level in ["Senior", "Mid", "Junior", "Lead", "Expert", "C-level"]:
            if level in text:
                return level
        return None

    @staticmethod
    def _extract_employment_types_from_html(soup: BeautifulSoup) -> list[str]:
        text = soup.get_text()
        types = []
        if "B2B" in text:
            types.append("B2B")
        if "Permanent" in text or "UoP" in text:
            types.append("Permanent")
        return types

    @staticmethod
    def _extract_locations_from_html(soup: BeautifulSoup) -> list[str]:
        """Extract city names from the offer's own office location section."""
        CITIES = [
            "Warszawa", "Wrocław", "Kraków", "Gdańsk", "Poznań",
            "Łódź", "Katowice", "Lublin", "Szczecin", "Bydgoszcz",
            "Białystok", "Gdynia", "Rzeszów", "Toruń", "Kielce",
        ]
        locations = []
        # Look for "Office location" section or the offer's own multilocation links
        # Offer location links contain the same slug base with different city
        slug = ""
        canonical = soup.find("link", rel="canonical")
        if canonical:
            slug = (canonical.get("href", "") or "").rstrip("/").rsplit("/", 1)[-1]

        if slug:
            # Strip the city-category suffix to get a company+title prefix
            # e.g. "tooploox-ai-engineer-wroclaw-ai" -> "tooploox-ai-engineer"
            parts = slug.split("-")
            # Try progressively shorter prefixes to find multiple location links
            for trim in range(2, min(5, len(parts))):
                prefix = "-".join(parts[:-trim])
                if len(prefix) < 5:
                    continue
                for a in soup.find_all("a", href=True):
                    href = a.get("href", "")
                    if prefix in href and "job-offer/" in href:
                        link_text = a.get_text(strip=True)
                        for city in CITIES:
                            if city in link_text and city not in locations:
                                locations.append(city)
                if locations:
                    break

        if not locations:
            text = soup.get_text()
            for city in CITIES:
                if city in text:
                    locations.append(city)
                    if len(locations) >= 3:
                        break

        return locations

    def _parse_html(self, soup: BeautifulSoup, url: str) -> JobBase:
        """Last-resort fallback parser."""
        title = ""
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

        company = ""
        for a_tag in soup.find_all("a", href=True):
            if "/company/" in a_tag.get("href", ""):
                company = a_tag.get_text(strip=True)
                break

        skills = self._extract_skills_from_html(soup)

        return JobBase(
            url=url,
            source="justjoin.it",
            title=title,
            company=company,
            location=[],
            salary=None,
            skills_required=skills,
            skills_nice_to_have=[],
            seniority=None,
            work_type=None,
            employment_types=[],
            description="",
            category=self._extract_category_from_url(url),
        )

    @staticmethod
    def _extract_category_from_url(url: str) -> str | None:
        """Extract category from the JustJoin URL slug suffix (e.g. '-ai', '-backend')."""
        KNOWN = {
            "ai": "AI", "backend": "Backend", "frontend": "Frontend",
            "fullstack": "Fullstack", "devops": "DevOps", "data": "Data",
            "mobile": "Mobile", "testing": "Testing", "security": "Security",
            "embedded": "Embedded", "pm": "PM", "game": "Game",
            "analytics": "Analytics", "erp": "ERP", "support": "Support",
            "architecture": "Architecture", "other": "Other",
        }
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        last_part = slug.rsplit("-", 1)[-1].lower()
        return KNOWN.get(last_part)

    @staticmethod
    def _normalize_work_type(raw: str) -> str | None:
        raw_lower = (raw or "").lower()
        if "remote" in raw_lower or "telecommute" in raw_lower:
            return "Remote"
        if "hybrid" in raw_lower or "partly" in raw_lower:
            return "Hybrid"
        if "office" in raw_lower or "onsite" in raw_lower:
            return "Onsite"
        if raw:
            return raw.capitalize()
        return None
