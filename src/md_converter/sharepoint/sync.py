from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from md_converter.core.manifest import append_manifest_entry
from md_converter.sharepoint.auth import GraphAuth
from md_converter.sharepoint.config import SharePointConfig, Source, build_config
from md_converter.sharepoint.graph_client import GraphClient
from md_converter.sharepoint.paths import build_mirror_path

if TYPE_CHECKING:  # heavy imports — loaded lazily inside sync()
    from md_converter.core.registry import ConverterRegistry


@dataclass
class Totals:
    converted: int = 0
    unchanged: int = 0
    failed: int = 0
    unsupported: int = 0
    # Per-extension tally of skipped files, and their paths when listing is on.
    unsupported_exts: Counter = field(default_factory=Counter)
    unsupported_paths: list[str] = field(default_factory=list)
    # Failures are rare and each one is worth keeping, so always collected:
    # (path, error type, error message) plus a tally by error type.
    failed_types: Counter = field(default_factory=Counter)
    failed_items: list[tuple[str, str, str]] = field(default_factory=list)
    # Files that converted but raised a warning (e.g. empty output) — these
    # succeed silently otherwise, so they are worth surfacing separately.
    warning_kinds: Counter = field(default_factory=Counter)
    warned_items: list[tuple[str, list[str]]] = field(default_factory=list)


@dataclass
class RunContext:
    client: GraphClient
    registry: ConverterRegistry
    supported: set[str]
    dest_drive: str
    root_folder: str
    log_dir: Path
    state: dict = field(default_factory=dict)
    ensured_folders: set[str] = field(default_factory=set)
    frontmatter: bool = True
    force: bool = False
    dry_run: bool = False
    limit: int | None = None
    list_unsupported: bool = False
    # Identifies this run's entries in the shared manifest, so --report can
    # isolate the most recent run.
    run_id: str = ""


def _load_state(state_file: Path) -> dict:
    if state_file.exists():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            print(f"Warning: could not read state file {state_file}; treating as empty.")
    return {}


def _save_state(state_file: Path, state: dict) -> None:
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _join(*parts: str) -> str:
    return "/".join(p.strip("/") for p in parts if p)


def _convert_item(
    ctx: RunContext, source_drive: str, item: dict
) -> tuple[str, str, list[str]]:
    """Download one source file and convert it locally.

    Returns the Markdown text, the converter's name, and any warnings it raised.
    The file is written to a temp path (preserving its name/extension) because the
    converters read from the local filesystem; the temp copy is removed afterwards.
    """
    content = ctx.client.download(source_drive, item["id"])
    with tempfile.TemporaryDirectory() as tmp:
        temp_path = Path(tmp) / item["name"]
        temp_path.write_bytes(content)

        from md_converter.core.frontmatter import inject_frontmatter

        converter = ctx.registry.get_converter(temp_path)
        result = converter.convert(temp_path)

        # Show the SharePoint source (not the throwaway temp path) in any frontmatter.
        result.source_path = PurePosixPath(item["rel_path"])
        markdown = inject_frontmatter(result) if ctx.frontmatter else result.markdown
        return markdown, result.converter_name, result.warnings


def _select_drives(client: GraphClient, site_id: str, source: Source) -> list[dict]:
    """Resolve a source's library selection to a list of ``{id, name}`` drives.

    ``libraries`` (an explicit allowlist) wins when set; otherwise ``library`` is
    used: "" = default document library, "*" = every library, else an exact name.
    Any name in ``exclude`` is then removed from the result.
    """
    drives = client.list_drives(site_id)

    if source.libraries:
        wanted = {name.lower() for name in source.libraries}
        selected = [d for d in drives if d["name"].lower() in wanted]
        missing = wanted - {d["name"].lower() for d in drives}
        if missing:
            raise SystemExit(
                "These libraries are listed in 'libraries' but do not exist in the "
                f"site: {', '.join(sorted(missing))}"
            )
    elif source.library == "*":
        selected = list(drives)
    elif source.library == "":
        default_id = client.default_drive_id(site_id)
        selected = [d for d in drives if d["id"] == default_id] or [
            {"id": default_id, "name": "Documents"}
        ]
    else:
        selected = [d for d in drives if d["name"].lower() == source.library.lower()]
        if not selected:
            available = ", ".join(d["name"] for d in drives)
            raise SystemExit(
                f"Library '{source.library}' not found in site. Available: {available}"
            )

    if source.exclude:
        skip = {name.lower() for name in source.exclude}
        selected = [d for d in selected if d["name"].lower() not in skip]

    return selected


def _limit_reached(ctx: RunContext, totals: Totals) -> bool:
    return ctx.limit is not None and (
        totals.converted + totals.unchanged + totals.failed
    ) >= ctx.limit


def _process_drive(
    ctx: RunContext, source_drive: str, folder: str, mirror_top: str, totals: Totals
) -> bool:
    """Convert every supported file in one drive. Returns True if --limit was hit
    (so the caller can stop without enumerating the remaining drives/sources)."""
    for item in ctx.client.walk_files(source_drive, folder):
        if _limit_reached(ctx, totals):
            return True
        suffix = Path(item["name"]).suffix.lower()
        if suffix not in ctx.supported:
            totals.unsupported += 1
            totals.unsupported_exts[suffix] += 1
            totals.unsupported_paths.append(f"{mirror_top}/{item['rel_path']}")
            if not ctx.dry_run:
                append_manifest_entry(
                    output_dir=ctx.log_dir,
                    source_path=PurePosixPath(item["rel_path"]),
                    output_path=None,
                    status="unsupported",
                    run_id=ctx.run_id,
                )
            continue

        rel_path = item["rel_path"]
        dest_path = build_mirror_path(mirror_top, rel_path)

        if ctx.dry_run:
            print(f"[dry-run] {dest_path}")
            totals.converted += 1  # counts "would convert" in dry-run
            continue

        version = item.get("ctag") or item.get("etag")
        if not ctx.force and ctx.state.get(item["id"]) == version:
            totals.unchanged += 1
            continue

        try:
            markdown, converter_name, warnings = _convert_item(ctx, source_drive, item)

            parent = dest_path.rsplit("/", 1)[0] if "/" in dest_path else ""
            if parent and parent not in ctx.ensured_folders:
                ctx.client.ensure_folder(ctx.dest_drive, parent)
                ctx.ensured_folders.add(parent)
            ctx.client.upload_text(ctx.dest_drive, dest_path, markdown)

            ctx.state[item["id"]] = version
            totals.converted += 1
            if warnings:
                totals.warned_items.append((f"{mirror_top}/{rel_path}", warnings))
                for warning in warnings:
                    totals.warning_kinds[warning] += 1
            append_manifest_entry(
                output_dir=ctx.log_dir,
                source_path=PurePosixPath(rel_path),
                output_path=PurePosixPath(dest_path),
                status="success",
                converter_name=converter_name,
                warnings=warnings,
                run_id=ctx.run_id,
            )
            print(f"Converted: {dest_path}")
            for warning in warnings:
                print(f"           warning: {warning}")
        except Exception as error:  # noqa: BLE001 — one bad file must not stop the run
            totals.failed += 1
            totals.failed_types[type(error).__name__] += 1
            totals.failed_items.append(
                (f"{mirror_top}/{rel_path}", type(error).__name__, str(error))
            )
            append_manifest_entry(
                output_dir=ctx.log_dir,
                source_path=PurePosixPath(rel_path),
                output_path=None,
                status="failed",
                error=str(error),
                run_id=ctx.run_id,
            )
            print(f"FAILED:    {rel_path}\n      {error}")
    return False


def _process_source(
    ctx: RunContext, config: SharePointConfig, source: Source, totals: Totals
) -> bool:
    """Convert every selected library of one source. Returns True if --limit was hit."""
    site = ctx.client.get_site(config.hostname, source.site_path)
    site_name = (
        source.mirror_name
        or site.get("displayName")
        or site.get("name")
        or source.site_path.rstrip("/").split("/")[-1]
    )
    drives = _select_drives(ctx.client, site["id"], source)

    for drive in drives:
        if _limit_reached(ctx, totals):
            return True
        mirror_top = _join(ctx.root_folder, site_name, drive["name"], source.folder)
        print(f"\n== {source.site_path} :: {drive['name']}  ->  {mirror_top}")
        if _process_drive(ctx, drive["id"], source.folder, mirror_top, totals):
            return True
    return False


def _report_warned(totals: Totals, list_paths: bool) -> None:
    """Surface files that converted but raised a warning (e.g. produced no text)."""
    if not totals.warned_items:
        return

    breakdown = ", ".join(
        f"{kind} ({count})" for kind, count in totals.warning_kinds.most_common()
    )
    print(f"{len(totals.warned_items)} file(s) converted with warnings — {breakdown}")

    if list_paths:
        print()
        for path, warnings in totals.warned_items:
            print(f"[warned] {path}")
            for warning in warnings:
                print(f"         {warning}")
    else:
        print("Re-run with --list-warned to see which files.")


def _report_failed(totals: Totals, list_paths: bool) -> None:
    """Summarise conversions that failed, grouped by error type."""
    if not totals.failed_items:
        return

    breakdown = ", ".join(
        f"{name}: {count}" for name, count in totals.failed_types.most_common()
    )
    print(f"Failures by error — {breakdown}")

    if list_paths:
        print()
        for path, error_type, message in totals.failed_items:
            print(f"[failed] {path}")
            print(f"         {error_type}: {message}")
    else:
        print("Re-run with --list-failed to see each failed file and its error.")


def _report_unsupported(totals: Totals, list_paths: bool) -> None:
    """Break the skipped files down by extension, most common first."""
    if not totals.unsupported_exts:
        return

    breakdown = ", ".join(
        f"{ext or '(no ext)'}: {count}"
        for ext, count in totals.unsupported_exts.most_common()
    )
    print(f"Unsupported by extension — {breakdown}")

    if list_paths:
        print()
        for path in totals.unsupported_paths:
            print(f"[unsupported] {path}")
    else:
        print("Re-run with --list-unsupported to see the individual file paths.")


def sync(args: argparse.Namespace) -> None:
    # Deferred: pulls in markitdown/pymupdf, which is slow to import and not
    # needed by --report or --check.
    from md_converter.core.registry import ConverterRegistry

    credentials, config = build_config(args)
    client = GraphClient(
        GraphAuth(credentials.tenant_id, credentials.client_id, credentials.client_secret)
    )

    print("Resolving destination...")
    dest_site_id = client.resolve_site(config.hostname, config.dest_site_path)
    dest_drive = client.resolve_drive(dest_site_id, config.dest_library or None)

    log_dir = Path(args.log_dir)
    state_file = Path(args.state_file)
    if not args.dry_run:
        log_dir.mkdir(parents=True, exist_ok=True)

    registry = ConverterRegistry()
    ctx = RunContext(
        client=client,
        registry=registry,
        supported=set(registry.supported_extensions()),
        dest_drive=dest_drive,
        root_folder=config.root_folder,
        log_dir=log_dir,
        state={} if args.force else _load_state(state_file),
        frontmatter=args.frontmatter,
        force=args.force,
        dry_run=args.dry_run,
        limit=args.limit,
        list_unsupported=args.list_unsupported,
        run_id=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    print(
        f"Destination: {config.dest_site_path} :: "
        f"{config.dest_library or '(default library)'}"
        + (f" / {config.root_folder}" if config.root_folder else "")
    )
    print(f"Sources: {len(config.sources)}")

    totals = Totals()
    for source in config.sources:
        if _process_source(ctx, config, source, totals):
            break

    if args.dry_run:
        print(f"\nDry run complete. {totals.converted} file(s) would be converted, "
              f"{totals.unsupported} unsupported skipped.")
        _report_unsupported(totals, args.list_unsupported)
        return

    _save_state(state_file, ctx.state)
    print(
        f"\nDone. {totals.converted} converted, {totals.unchanged} unchanged (skipped), "
        f"{totals.failed} failed, {totals.unsupported} unsupported."
    )
    _report_unsupported(totals, args.list_unsupported)
    _report_warned(totals, args.list_warned)
    _report_failed(totals, args.list_failed)
    print(f"State: {state_file}    Log: {log_dir / 'conversion_manifest.jsonl'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="md-convert-sp",
        description=(
            "Convert files from SharePoint libraries into Markdown mirrors in another "
            "SharePoint site, via Microsoft Graph (app-only authentication)."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("sharepoint.toml"),
        help="Path to the SharePoint TOML config. Default: ./sharepoint.toml",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Path to a .env file holding AZURE_* credentials. Default: ./.env",
    )

    # A single --source-site defines a one-off source, overriding the config's sources.
    parser.add_argument("--hostname", help="SharePoint hostname, e.g. contoso.sharepoint.com")
    parser.add_argument("--source-site", help="One-off source site path, e.g. /sites/AERMADE")
    parser.add_argument(
        "--source-library",
        help="Library selector for the one-off source: a name, '' (default library), or '*' (all).",
    )
    parser.add_argument("--source-folder", help="Subfolder within the one-off source library")
    parser.add_argument("--mirror-name", help="Top mirror folder name for the one-off source")
    parser.add_argument("--dest-site", help="Destination (aermade AI) site path")
    parser.add_argument("--dest-library", help="Destination document library name")
    parser.add_argument("--root-folder", help="Optional prefix folder in the destination")

    parser.add_argument(
        "--no-frontmatter",
        dest="frontmatter",
        action="store_false",
        help="Skip injecting YAML frontmatter (source, converter, timestamp) into each file.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help=(
            "Summarise the last run from the local manifest and exit. Reads no "
            "network and needs no credentials, so it returns immediately."
        ),
    )
    parser.add_argument(
        "--all-runs",
        action="store_true",
        help="With --report, cover every run in the manifest instead of just the last.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Test credentials and per-site access, then exit. Writes and deletes a "
            "small probe file in the destination to verify write access."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List source files and their destination paths; do not convert or upload.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N files total (useful for a first test run).",
    )
    parser.add_argument(
        "--list-unsupported",
        action="store_true",
        help="Print the path of every file skipped for having an unsupported extension.",
    )
    parser.add_argument(
        "--list-failed",
        action="store_true",
        help="Print every file whose conversion failed, with its error.",
    )
    parser.add_argument(
        "--list-warned",
        action="store_true",
        help=(
            "Print every file that converted but raised a warning, such as "
            "producing empty output."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-convert every file, ignoring the incremental state cache.",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path("sharepoint_state.json"),
        help="Local JSON cache of converted item versions, for incremental runs.",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("sharepoint_logs"),
        help="Local directory for the conversion manifest log.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    # --report reads only the local manifest, so it runs before anything that
    # would need credentials or a network call.
    if args.report:
        from md_converter.sharepoint.report import report

        report(args)
        return
    if args.check:
        from md_converter.sharepoint.check import check

        check(args)
        return
    sync(args)


if __name__ == "__main__":
    main()
