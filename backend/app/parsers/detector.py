from app.models.job import JobBase
from app.parsers.base import BaseParser
from app.parsers.justjoin import JustJoinParser
from app.parsers.nofluffjobs import NoFluffJobsParser

_parsers: list[BaseParser] = [
    JustJoinParser(),
    NoFluffJobsParser(),
]


def detect_and_parse(url: str) -> JobBase:
    """Route a URL to the appropriate parser and return parsed job data."""
    for parser in _parsers:
        if parser.can_handle(url):
            return parser.parse(url)
    raise ValueError(
        f"Unsupported URL: {url}. Supported sites: justjoin.it, nofluffjobs.com"
    )


def is_supported_url(url: str) -> bool:
    return any(p.can_handle(url) for p in _parsers)
