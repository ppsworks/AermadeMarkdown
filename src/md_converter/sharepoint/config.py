import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Credentials:
    tenant_id: str
    client_id: str
    client_secret: str


@dataclass
class Source:
    site_path: str
    # library: "" = the site's default document library; "*" = every library;
    # or an exact library name.
    library: str = ""
    # libraries: an explicit allowlist of library names. Takes precedence over
    # `library` when non-empty. Preferred for sites holding mixed content, since
    # libraries added later are excluded by default rather than swept in.
    libraries: list[str] = field(default_factory=list)
    # exclude: library names to skip, applied after the above selection.
    exclude: list[str] = field(default_factory=list)
    # folder: optional subfolder within the library to limit the scan.
    folder: str = ""
    # mirror_name: top folder used for this source in the destination.
    # "" = derive from the site's display name.
    mirror_name: str = ""


@dataclass
class SharePointConfig:
    hostname: str
    sources: list[Source]
    dest_site_path: str
    dest_library: str  # "" = default library
    root_folder: str  # optional prefix under which all mirrors live; may be ""


def load_credentials(env_file: Path | None = None) -> Credentials:
    """Load AZURE_* secrets from the environment (a .env file is loaded if present)."""
    load_dotenv(env_file)
    try:
        return Credentials(
            tenant_id=os.environ["AZURE_TENANT_ID"],
            client_id=os.environ["AZURE_CLIENT_ID"],
            client_secret=os.environ["AZURE_CLIENT_SECRET"],
        )
    except KeyError as missing:
        raise SystemExit(
            f"Missing required credential {missing}. Set AZURE_TENANT_ID, "
            "AZURE_CLIENT_ID and AZURE_CLIENT_SECRET (e.g. in a .env file)."
        ) from None


def _pick(cli_value, section: dict, key: str, default=None):
    """CLI value wins; then the TOML value; then the default. Blanks count as unset."""
    if cli_value not in (None, ""):
        return cli_value
    value = section.get(key)
    return value if value not in (None, "") else default


def _sources_from_config(args, data: dict) -> list[Source]:
    """A single --source-site on the CLI defines a one-off source and overrides the
    config's [[source]] list; otherwise the [[source]] entries are used."""
    if args.source_site:
        return [
            Source(
                site_path=args.source_site,
                library=args.source_library or "",
                folder=args.source_folder or "",
                mirror_name=args.mirror_name or "",
            )
        ]

    sources: list[Source] = []
    for entry in data.get("source", []):
        site_path = entry.get("site_path", "")
        if not site_path:
            raise SystemExit("Each [[source]] in the config needs a 'site_path'.")
        sources.append(
            Source(
                site_path=site_path,
                library=entry.get("library", "") or "",
                libraries=entry.get("libraries", []) or [],
                exclude=entry.get("exclude", []) or [],
                folder=entry.get("folder", "") or "",
                mirror_name=entry.get("mirror_name", "") or "",
            )
        )
    return sources


def build_config(args) -> tuple[Credentials, SharePointConfig]:
    """Merge the TOML config file with CLI overrides and load credentials."""
    credentials = load_credentials(getattr(args, "env_file", None))

    data: dict = {}
    config_path = getattr(args, "config", None)
    if config_path and Path(config_path).exists():
        with Path(config_path).open("rb") as file:
            data = tomllib.load(file)

    graph = data.get("graph", {})
    dest = data.get("destination", {})

    hostname = _pick(args.hostname, graph, "hostname")
    dest_site_path = _pick(args.dest_site, dest, "site_path")
    dest_library = _pick(args.dest_library, dest, "library", "") or ""
    root_folder = _pick(args.root_folder, dest, "root_folder", "") or ""

    sources = _sources_from_config(args, data)

    missing = [
        name
        for name, value in (
            ("graph.hostname", hostname),
            ("destination.site_path", dest_site_path),
            ("at least one source", sources),
        )
        if not value
    ]
    if missing:
        raise SystemExit(
            "Missing required configuration: "
            + ", ".join(missing)
            + f". Provide it in {config_path} or via CLI flags."
        )

    config = SharePointConfig(
        hostname=hostname,
        sources=sources,
        dest_site_path=dest_site_path,
        dest_library=dest_library,
        root_folder=root_folder,
    )
    return credentials, config
