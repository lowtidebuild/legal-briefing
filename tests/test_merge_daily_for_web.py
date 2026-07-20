from __future__ import annotations

import json
from pathlib import Path

from pipeline.intelligence.dedup import DedupEntry, DedupIndex, url_hash
from pipeline.models import (
    BriefingNode,
    EventType,
    Jurisdiction,
    LegalEvent,
    RegulatoryPhase,
)
from pipeline.store.daily import load_daily, save_daily
from pipeline.store.dedup_index import load_dedup_index, save_dedup_index
from scripts.merge_daily_for_web import merge_daily_for_web


def _node(index: int, *, url: str | None = None, event_key: str | None = None) -> BriefingNode:
    return BriefingNode(
        title=f"Game privacy enforcement {index}",
        url=url or f"https://example.com/{index}",
        source=f"Source {index}",
        pub_date="2026-07-20",
        category="PRIVACY_SECURITY",
        summary_ko=[
            "게임 개인정보 관련 집행 절차가 진행됐습니다.",
            "사업자의 이용자 데이터 처리 기준에 영향을 줄 수 있습니다.",
            "관련 정책과 내부 통제 절차를 점검할 필요가 있습니다.",
        ],
        event=LegalEvent(
            jurisdiction=Jurisdiction.US,
            event_type=EventType.ENFORCEMENT,
            regulatory_phase=RegulatoryPhase.ENFORCED,
            actors=["FTC"],
            object=f"game privacy {index}",
            action="enforced",
            game_mechanic=None,
            time_hint="",
        ),
        event_key=event_key or f"event_{index}_2026q3",
        is_primary=False,
        title_ko=f"게임 개인정보 집행 {index}",
    )


def test_merge_daily_preserves_existing_and_adds_unique_nodes(tmp_path: Path):
    target = tmp_path / "target"
    source = tmp_path / "source"
    existing = [_node(0), _node(1), _node(2)]
    incoming = [
        _node(30, url=existing[0].url),
        _node(31, event_key=existing[1].event_key),
        *[_node(index) for index in range(3, 12)],
    ]
    save_daily(existing, "2026-07-20", data_dir=str(target / "data" / "daily"))
    save_daily(incoming, "2026-07-20", data_dir=str(source / "data" / "daily"))
    save_dedup_index(
        DedupIndex(
            entries=[
                DedupEntry(
                    event_key=node.event_key,
                    url_hash=url_hash(node.url),
                    date="2026-07-20",
                    event_fingerprint=f"fingerprint-{node.event_key}",
                )
                for node in incoming
            ]
        ),
        str(source / "data" / "dedup_index.json"),
    )

    result = merge_daily_for_web(
        date="2026-07-20",
        source_output_dir=str(source),
        target_output_dir=str(target),
        max_items=10,
    )

    merged = load_daily("2026-07-20", data_dir=str(target / "data" / "daily"))
    assert result.previous_count == 3
    assert result.added_count == 7
    assert result.final_count == 10
    assert [node.event_key for node in merged[:3]] == [node.event_key for node in existing]
    assert len({node.url for node in merged}) == 10
    assert len({node.event_key for node in merged}) == 10

    target_index = load_dedup_index(str(target / "data" / "dedup_index.json"))
    assert len(target_index.entries) == 7
    assert all(entry.event_fingerprint for entry in target_index.entries)

    audit = json.loads((target / "data" / "web_repairs" / "2026-07-20.json").read_text())
    assert audit["delivery"] == "not_run"
    assert audit["final_count"] == 10
