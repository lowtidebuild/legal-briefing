from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone


class RunManifestError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    briefing_date: str
    item_count: int
    daily_data_path: str
    content_sha256: str
    generation_status: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "briefing_date": self.briefing_date,
            "item_count": self.item_count,
            "daily_data_path": self.daily_data_path,
            "content_sha256": self.content_sha256,
            "generation_status": self.generation_status,
            "created_at": self.created_at,
        }


def _daily_path(output_dir: str, date: str) -> str:
    return os.path.join(output_dir, "data", "daily", f"{date}.json")


def manifest_path(output_dir: str, date: str) -> str:
    return os.path.join(output_dir, "data", "run_manifests", f"{date}.json")


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_run_manifest(
    *,
    date: str,
    run_id: str,
    item_count: int,
    output_dir: str,
) -> RunManifest:
    daily_path = _daily_path(output_dir, date)
    if not os.path.isfile(daily_path):
        raise RunManifestError(f"Daily data is missing for {date}")

    output_name = os.path.basename(os.path.normpath(output_dir)) or "output"
    manifest = RunManifest(
        run_id=run_id,
        briefing_date=date,
        item_count=item_count,
        daily_data_path=f"{output_name}/data/daily/{date}.json",
        content_sha256=_sha256(daily_path),
        generation_status="ready",
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    path = manifest_path(output_dir, date)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest.to_dict(), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return manifest


def load_run_manifest(output_dir: str, date: str) -> RunManifest:
    path = manifest_path(output_dir, date)
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RunManifestError(f"Run manifest is unavailable for {date}") from exc

    if payload.get("schema_version") != 1:
        raise RunManifestError("Unsupported run manifest schema")
    try:
        return RunManifest(
            run_id=str(payload["run_id"]),
            briefing_date=str(payload["briefing_date"]),
            item_count=int(payload["item_count"]),
            daily_data_path=str(payload["daily_data_path"]),
            content_sha256=str(payload["content_sha256"]),
            generation_status=str(payload["generation_status"]),
            created_at=str(payload["created_at"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RunManifestError("Run manifest is incomplete") from exc


def verify_run_manifest(
    *,
    output_dir: str,
    date: str,
    expected_run_id: str | None = None,
) -> RunManifest:
    manifest = load_run_manifest(output_dir, date)
    if manifest.briefing_date != date:
        raise RunManifestError("Run manifest date does not match requested date")
    if expected_run_id is not None and manifest.run_id != expected_run_id:
        raise RunManifestError("Run ID does not match generated content")
    if manifest.generation_status != "ready":
        raise RunManifestError("Generated content is not ready for delivery")

    daily_path = _daily_path(output_dir, date)
    if not os.path.isfile(daily_path) or _sha256(daily_path) != manifest.content_sha256:
        raise RunManifestError("Daily content hash does not match run manifest")
    try:
        with open(daily_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RunManifestError("Daily content is unreadable") from exc
    if not isinstance(payload, list) or len(payload) != manifest.item_count:
        raise RunManifestError("Daily item count does not match run manifest")
    return manifest
