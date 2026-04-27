import os
import tempfile

from pipeline.intelligence.dedup import DedupEntry, DedupIndex
from pipeline.store.dedup_index import load_dedup_index, prune_old_entries, save_dedup_index


def test_save_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "dedup_index.json")
        index = DedupIndex(
            entries=[
                DedupEntry(
                    event_key="key1",
                    url_hash="hash1",
                    date="2026-03-23",
                    event_fingerprint="fp1",
                )
            ]
        )
        save_dedup_index(index, path)
        loaded = load_dedup_index(path)
        assert len(loaded.entries) == 1
        assert loaded.entries[0].event_key == "key1"
        assert loaded.entries[0].event_fingerprint == "fp1"
        assert loaded.schema_version == 2


def test_load_v1_index_without_event_fingerprint():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "dedup_index.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(
                '{"schema_version": 1, "retention_days": 30, '
                '"entries": [{"event_key": "key1", "url_hash": "hash1", "date": "2026-03-23"}]}'
            )
        loaded = load_dedup_index(path)
        assert loaded.schema_version == 2
        assert loaded.entries[0].event_fingerprint == ""


def test_load_missing_returns_empty():
    loaded = load_dedup_index("/nonexistent/path.json")
    assert loaded.entries == []


def test_prune_old_entries():
    index = DedupIndex(
        entries=[
            DedupEntry(event_key="old", url_hash="h1", date="2026-01-01"),
            DedupEntry(event_key="recent", url_hash="h2", date="2026-03-20"),
        ],
        retention_days=30,
    )
    pruned = prune_old_entries(index, today="2026-03-28")
    assert len(pruned.entries) == 1
    assert pruned.entries[0].event_key == "recent"
