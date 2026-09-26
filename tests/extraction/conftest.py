from __future__ import annotations

import pytest

from dsfs.models.source_evidence import SourceEvidence, SourceType


def make_evidence(
    source_id: str,
    text: str,
    *,
    entity_mentions: list[str] | None = None,
    authored_at: str = "2026-01-05T09:00:00",
    available_at: str = "2026-01-05T09:10:00",
) -> SourceEvidence:
    return SourceEvidence(
        source_id=source_id,
        source_type=SourceType.ACCOUNT_NOTE,
        source_record_id=source_id,
        source_revision="r1",
        authored_at=authored_at,
        available_at=available_at,
        raw_text=text,
        content_hash="sha256:test",
        entity_mentions_raw=entity_mentions or ["CUST-0001"],
    )


@pytest.fixture
def known_entities() -> set[str]:
    return {"CUST-0001", "CUST-0002"}
