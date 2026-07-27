"""Offline report over the conversion manifest.

Reads ``conversion_manifest.jsonl`` and summarises a run — no Graph calls, no
credentials, no waiting. Useful after a long run to review what failed, what was
skipped, and what converted to nothing.
"""

import json
from collections import Counter
from pathlib import Path

MANIFEST_NAME = "conversion_manifest.jsonl"


def _load(manifest_path: Path) -> list[dict]:
    entries = []
    with manifest_path.open(encoding="utf-8") as file:
        for number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"Warning: skipping malformed manifest line {number}.")
    return entries


def _latest_run(entries: list[dict]) -> tuple[list[dict], str]:
    """Return the entries belonging to the most recent run, and its id.

    Runs are identified by ``run_id``; entries written before that field existed
    have ``None`` and are treated as one legacy group.
    """
    if not entries:
        return [], ""
    latest = entries[-1].get("run_id")
    return [e for e in entries if e.get("run_id") == latest], latest or "(legacy run)"


def _section(title: str, rows: list[str], show_paths: bool, limit: int = 40) -> None:
    if not rows:
        return
    print(f"\n{title}")
    shown = rows if show_paths else rows[:limit]
    for row in shown:
        print(f"  {row}")
    if not show_paths and len(rows) > limit:
        print(f"  ... and {len(rows) - limit} more (use --list-* to show all)")


def report(args) -> None:
    log_dir = Path(args.log_dir)
    manifest_path = log_dir / MANIFEST_NAME
    if not manifest_path.exists():
        raise SystemExit(
            f"No manifest found at {manifest_path}. Run a conversion first, or pass "
            "--log-dir if the logs live elsewhere."
        )

    entries = _load(manifest_path)
    if not entries:
        raise SystemExit(f"{manifest_path} is empty.")

    scoped, run_id = (entries, "all runs") if args.all_runs else _latest_run(entries)

    by_status = Counter(e.get("status", "unknown") for e in scoped)
    succeeded = [e for e in scoped if e.get("status") == "success"]
    failed = [e for e in scoped if e.get("status") == "failed"]
    unsupported = [e for e in scoped if e.get("status") == "unsupported"]
    warned = [e for e in succeeded if e.get("warnings")]

    print(f"Manifest: {manifest_path}")
    print(f"Run:      {run_id}")
    print(f"Entries:  {len(scoped)}" + ("" if args.all_runs else f" of {len(entries)} total"))
    print()
    print(
        f"  {by_status.get('success', 0)} converted, "
        f"{by_status.get('failed', 0)} failed, "
        f"{by_status.get('unsupported', 0)} unsupported, "
        f"{len(warned)} with warnings"
    )

    if unsupported:
        breakdown = ", ".join(
            f"{ext or '(no ext)'}: {count}"
            for ext, count in Counter(
                e.get("source_extension", "") for e in unsupported
            ).most_common()
        )
        print(f"\nUnsupported by extension — {breakdown}")
        _section(
            "Unsupported files:",
            [e.get("source_path", "?") for e in unsupported],
            args.list_unsupported,
        )

    if failed:
        breakdown = ", ".join(
            f"{kind}: {count}"
            for kind, count in Counter(
                _error_kind(e.get("error")) for e in failed
            ).most_common()
        )
        print(f"\nFailures by error — {breakdown}")
        _section(
            "Failed files:",
            [f"{e.get('source_path', '?')}\n      {e.get('error', '')}" for e in failed],
            args.list_failed,
        )

    if warned:
        breakdown = ", ".join(
            f"{kind} ({count})"
            for kind, count in Counter(
                w for e in warned for w in e.get("warnings", [])
            ).most_common()
        )
        print(f"\nWarnings — {breakdown}")
        _section(
            "Files converted with warnings:",
            [
                f"{e.get('source_path', '?')}\n      {'; '.join(e.get('warnings', []))}"
                for e in warned
            ],
            args.list_warned,
        )

    converters = Counter(
        e.get("converter_name") for e in succeeded if e.get("converter_name")
    )
    if converters:
        print(
            "\nConverters used — "
            + ", ".join(f"{name}: {count}" for name, count in converters.most_common())
        )


def _error_kind(error: str | None) -> str:
    """Condense an error message to something groupable."""
    if not error:
        return "unknown"
    if "threw" in error:
        # "XlsxConverter threw BadZipFile with message: ..." -> "BadZipFile"
        after = error.split("threw", 1)[1].strip()
        return after.split(" with message", 1)[0].strip() or "unknown"
    if "Graph API" in error:
        for code in ("[400]", "[401]", "[403]", "[404]", "[429]", "[500]", "[503]"):
            if code in error:
                return f"Graph {code.strip('[]')}"
        return "Graph API error"
    return error.split(":", 1)[0].strip()[:60]
