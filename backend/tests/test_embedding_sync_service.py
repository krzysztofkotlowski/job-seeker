from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.tables import EmbeddingSyncRunRow, JobRow
from app.services.embedding_sync_service import (
    get_status,
    resolve_active_recommendation_source,
    run_sync_task,
)


def _job() -> JobRow:
    return JobRow(
        id=uuid4(),
        url=f"https://example.com/job/{uuid4()}",
        source="test",
        title="Backend Engineer",
        company="Acme",
        skills_required=["Python"],
        skills_nice_to_have=[],
        date_added="2024-01-01",
    )


def _run(
    *,
    status: str,
    mode: str,
    embed_model: str = "bge-base-en:v1.5",
    embed_dims: int = 768,
    indexed: int = 0,
    failed: int = 0,
    target_total: int = 1,
    physical_index_name: str = "jobseeker_jobs_run_test",
    activated: bool = False,
) -> EmbeddingSyncRunRow:
    now = datetime.now(timezone.utc)
    return EmbeddingSyncRunRow(
        id=uuid4(),
        status=status,
        mode=mode,
        unique_only=False,
        embed_source="ollama",
        embed_model=embed_model,
        embed_dims=embed_dims,
        db_total_snapshot=1,
        selection_total=1,
        target_total=target_total,
        processed=indexed + failed,
        indexed=indexed,
        failed=failed,
        index_alias="jobseeker_jobs_active",
        physical_index_name=physical_index_name,
        started_at=now,
        finished_at=now if status in {"completed", "failed"} else None,
        updated_at=now,
        activated_at=now if activated else None,
    )


def test_run_sync_task_failed_full_rebuild_preserves_previous_active_run(db):
    """A broken full rebuild must fail without stealing activation from the previous good run."""
    good_run = _run(
        status="completed",
        mode="full",
        indexed=1,
        failed=0,
        target_total=1,
        physical_index_name="jobseeker_jobs_run_good",
        activated=True,
    )
    new_run = _run(
        status="queued",
        mode="full",
        indexed=0,
        failed=0,
        target_total=1,
        physical_index_name="jobseeker_jobs_run_broken",
        activated=False,
    )
    db.add(_job())
    db.add_all([good_run, new_run])
    db.commit()

    test_session_local = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False)

    with (
        patch("app.services.embedding_sync_service.SessionLocal", test_session_local),
        patch("app.services.elasticsearch_service._get_client", return_value=object()),
        patch("app.services.elasticsearch_service.ensure_index", return_value=True),
        patch(
            "app.services.elasticsearch_service.iter_index_job_batches",
            return_value=iter([{"processed": 1, "indexed": 0, "failed": 1, "total": 1, "index_name": new_run.physical_index_name}]),
        ),
        patch("app.services.embedding_sync_service.activate_alias") as activate_alias,
        patch("app.services.elasticsearch_service.clear_index") as clear_index,
    ):
        with pytest.raises(RuntimeError, match="Embedding sync incomplete"):
            run_sync_task(str(new_run.id))

    db.refresh(good_run)
    db.refresh(new_run)
    assert activate_alias.called is False
    clear_index.assert_called_once_with(index_name="jobseeker_jobs_run_broken")
    assert good_run.activated_at is not None
    assert new_run.status == "failed"
    assert new_run.activated_at is None


def test_resolve_active_recommendation_source_rejects_empty_active_run(db):
    """A zero-document active run should force reindex_required instead of pretending it is healthy."""
    broken_run = _run(
        status="completed",
        mode="full",
        indexed=0,
        failed=11783,
        target_total=11783,
        physical_index_name="jobseeker_jobs_run_broken",
        activated=True,
    )
    db.add(broken_run)
    db.commit()

    with (
        patch("app.services.embedding_sync_service.es_available", return_value=True),
        patch("app.services.embedding_sync_service.count_documents", return_value=0),
    ):
        resolved = resolve_active_recommendation_source(db)

    assert resolved["status"] == "reindex_required"
    assert "incomplete or empty" in resolved["message"]


def test_status_and_recommendation_source_report_unqueryable_stale_active_model(db):
    """A legacy nomic index should force rebuild when the selected profile changes."""
    stale_run = _run(
        status="completed",
        mode="full",
        embed_model="nomic-embed-text",
        embed_dims=768,
        indexed=11783,
        failed=0,
        target_total=11783,
        physical_index_name="jobseeker_jobs_run_stale",
        activated=True,
    )
    db.add(stale_run)
    db.commit()

    with (
        patch("app.services.embedding_sync_service.es_available", return_value=True),
        patch("app.services.embedding_sync_service.count_documents", return_value=11783),
        patch(
            "app.services.embedding_sync_service.get_ai_config",
            return_value={
                "embed_source": "ollama",
                "embed_model": "nomic-embed-text",
                "embed_dims": 768,
                "embed_profile": "nomic-search-v1",
            },
        ),
    ):
        status = get_status(db)
        resolved = resolve_active_recommendation_source(db)

    assert status["recommendations"]["status"] == "reindex_required"
    assert "legacy raw-text nomic profile" in status["recommendations"]["message"]
    assert status["recommendations"]["active_query_model_ready"] is False
    assert status["recommendations"]["active_embed_profile"] == "nomic-legacy-v1"
    assert status["recommendations"]["selected_embed_profile"] == "nomic-search-v1"

    assert resolved["status"] == "reindex_required"
    assert resolved["message"] == status["recommendations"]["message"]
