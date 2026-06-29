import json
from datetime import datetime, timezone
from pathlib import Path


def append_manifest_entry(
    output_dir: Path,
    source_path: Path,
    output_path: Path | None,
    status: str,
    converter_name: str | None = None,
    error: str | None = None,
    warnings: list[str] | None = None,
) -> None:
    manifest_path = output_dir / "conversion_manifest.jsonl"

    entry = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_path": str(source_path),
        "source_name": source_path.name,
        "source_extension": source_path.suffix.lower(),
        "output_path": str(output_path) if output_path else None,
        "status": status,
        "converter_name": converter_name,
        "warnings": warnings or [],
        "error": error,
    }

    with manifest_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")
