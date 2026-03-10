"""Test data factories."""

import uuid

from app.models.tables import JobRow, UserRow


def create_job(
    db,
    url: str | None = None,
    source: str = "justjoin.it",
    title: str = "Test Job",
    company: str = "Test Co",
    **kwargs,
) -> JobRow:
    """Create a job for testing."""
    job = JobRow(
        url=url or f"https://example.com/job/{uuid.uuid4()}",
        source=source,
        title=title,
        company=company,
        location=kwargs.get("location", []),
        skills_required=kwargs.get("skills_required", []),
        skills_nice_to_have=kwargs.get("skills_nice_to_have", []),
        category=kwargs.get("category"),
        **{k: v for k, v in kwargs.items() if k not in ("location", "skills_required", "skills_nice_to_have", "category")},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def create_user(db, keycloak_id: str, email: str | None = None, username: str | None = None) -> UserRow:
    """Create a user for testing."""
    user = UserRow(keycloak_id=keycloak_id, email=email, username=username)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
