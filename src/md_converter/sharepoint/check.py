# Connection diagnostic for the SharePoint integration. Tests credentials, per-site
# read access, and destination write access separately, so a failure points at one
# cause (usually a missing Sites.Selected grant rather than bad credentials).

from md_converter.sharepoint.auth import GraphAuth
from md_converter.sharepoint.config import SharePointConfig, build_config
from md_converter.sharepoint.graph_client import GraphClient

PROBE_NAME = "_md-convert-sp-write-test.md"

OK = "  OK   "
FAIL = " FAIL  "


def _hint(error: Exception) -> str:
    """Turn a Graph error into the most likely cause."""
    text = str(error)
    if "403" in text:
        return (
            "403 Forbidden: the app authenticated but has no access to this site. "
            "This is the per-site Sites.Selected grant; ask IT to grant the app "
            "read (source) / write (destination) on this specific site."
        )
    if "404" in text:
        return (
            "404 Not Found: the site path is probably wrong. Open the site in a "
            "browser and copy the part of the URL after the hostname "
            "(e.g. https://contoso.sharepoint.com/sites/AERMADE -> /sites/AERMADE)."
        )
    if "401" in text:
        return "401 Unauthorized: check the tenant id, client id and secret."
    return text


def _check_source(client: GraphClient, config: SharePointConfig, source) -> bool:
    from md_converter.sharepoint.sync import _select_drives

    site_path = source.site_path
    try:
        site = client.get_site(config.hostname, site_path)
    except Exception as error:  # noqa: BLE001 (diagnostic wants the reason, not a trace)
        print(f"[{FAIL}] read  {site_path}")
        print(f"          {_hint(error)}")
        return False

    name = site.get("displayName") or site.get("name") or site_path
    try:
        all_drives = client.list_drives(site["id"])
        selected = _select_drives(client, site["id"], source)
    except SystemExit:
        raise
    except Exception as error:  # noqa: BLE001
        print(f"[{FAIL}] read  {site_path} (resolved '{name}', but cannot list libraries)")
        print(f"          {_hint(error)}")
        return False

    chosen = {d["name"] for d in selected}
    print(
        f"[{OK}] read  {site_path}  ->  '{name}': "
        f"{len(selected)} of {len(all_drives)} librar(ies) selected"
    )
    for drive in all_drives:
        mark = "+" if drive["name"] in chosen else "-"
        print(f"             {mark} {drive['name']}")
    return True


def _check_destination(client: GraphClient, config: SharePointConfig) -> bool:
    site_path = config.dest_site_path
    try:
        site = client.get_site(config.hostname, site_path)
        drive_id = client.resolve_drive(site["id"], config.dest_library or None)
    except Exception as error:  # noqa: BLE001
        print(f"[{FAIL}] write {site_path}")
        print(f"          {_hint(error)}")
        return False

    name = site.get("displayName") or site.get("name") or site_path
    # Only a real write proves write access. Upload a small probe, then delete it.
    try:
        item = client.upload_text(drive_id, PROBE_NAME, "write test\n")
        client.delete_item(drive_id, item["id"])
    except Exception as error:  # noqa: BLE001
        print(f"[{FAIL}] write {site_path} (resolved '{name}', but cannot write)")
        print(f"          {_hint(error)}")
        return False

    print(f"[{OK}] write {site_path}  ->  '{name}' (uploaded and deleted {PROBE_NAME})")
    return True


def check(args) -> None:
    credentials, config = build_config(args)

    print("Checking SharePoint connection\n")
    print(f"Hostname: {config.hostname}")
    print(f"Tenant:   {credentials.tenant_id}")
    print(f"Client:   {credentials.client_id}\n")

    auth = GraphAuth(
        credentials.tenant_id, credentials.client_id, credentials.client_secret
    )
    try:
        auth.token()
        print(f"[{OK}] credentials, token acquired\n")
    except Exception as error:  # noqa: BLE001
        print(f"[{FAIL}] credentials, could not acquire a token")
        print(f"          {error}\n")
        raise SystemExit(1)

    client = GraphClient(auth)
    print("Libraries marked '+' will be mirrored, '-' will be skipped.\n")
    results = [_check_source(client, config, s) for s in config.sources]
    print()
    results.append(_check_destination(client, config))

    print()
    if all(results):
        print("All checks passed. Next: md-convert-sp --dry-run")
    else:
        print(
            "Some checks failed. If credentials worked but sites returned 403, the "
            "app registration exists but is missing its per-site Sites.Selected "
            "grants; that's a separate step from creating the app."
        )
        raise SystemExit(1)
