from unittest.mock import AsyncMock, MagicMock

import pytest
from tools import _runtime as rt
from tools.anchor.core import pulse
from tools.breath.catalog import surface_catalog
from tools.breath.importance import _select_importance_buckets


def records():
    return [
        {"id": "ordinary", "content": "Original event", "metadata": {"name": "KEEP_EVENT", "type": "dynamic", "importance": 7}},
        {"id": "old-i", "content": "Old identity", "metadata": {"name": "HIDE_IDENTITY", "type": "i", "importance": 10}},
        {"id": "candidate", "content": "Old candidate", "metadata": {"name": "HIDE_CANDIDATE", "type": "dynamic", "i_stage": "candidate", "importance": 10}},
    ]


def test_importance_audit_excludes_identity_before_limiting():
    selected = _select_importance_buckets(records(), 1, limit=1)
    assert [b["id"] for b in selected] == ["ordinary"]


@pytest.mark.asyncio
async def test_catalog_and_status_keep_events_without_identity_entries():
    rt.bucket_mgr = MagicMock()
    rt.bucket_mgr.list_all = AsyncMock(return_value=records())
    rt.bucket_mgr.get_stats = AsyncMock(return_value={"permanent_count": 0, "dynamic_count": 2, "archive_count": 0, "total_size_kb": 1})
    rt.bucket_mgr.embedding_outbox = None
    rt.bucket_mgr.footprint_snapshot.side_effect = RuntimeError("no footprint in fixture")
    rt.decay_engine = MagicMock()
    rt.decay_engine.ensure_started = AsyncMock()
    rt.decay_engine.calculate_score.return_value = 1
    rt.embedding_engine = None
    rt.logger = MagicMock()
    for output in (await surface_catalog(), await pulse()):
        assert "KEEP_EVENT" in output
        assert "HIDE_IDENTITY" not in output
        assert "HIDE_CANDIDATE" not in output
