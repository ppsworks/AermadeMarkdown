from collections.abc import Iterator
from urllib.parse import quote

import requests

from md_converter.sharepoint.auth import GraphAuth

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class GraphClient:
    """Thin Microsoft Graph REST wrapper for the file operations this tool needs:
    resolving sites/drives, walking files, downloading content, ensuring folders,
    and uploading small text files.
    """

    def __init__(self, auth: GraphAuth) -> None:
        self._auth = auth
        self._session = requests.Session()
        self._root_ids: dict[str, str] = {}

    # -- low-level helpers -------------------------------------------------

    def _headers(self, extra: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self._auth.token()}"}
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _check(response: requests.Response) -> requests.Response:
        if response.status_code >= 400:
            snippet = response.text[:500]
            raise RuntimeError(
                f"Graph API {response.request.method} {response.url} "
                f"failed [{response.status_code}]: {snippet}"
            )
        return response

    def _get(self, url: str, **kwargs) -> requests.Response:
        return self._check(self._session.get(url, headers=self._headers(), **kwargs))

    def _root_id(self, drive_id: str) -> str:
        if drive_id not in self._root_ids:
            self._root_ids[drive_id] = self._get(
                f"{GRAPH_BASE}/drives/{drive_id}/root"
            ).json()["id"]
        return self._root_ids[drive_id]

    # -- site / drive resolution ------------------------------------------

    def get_site(self, hostname: str, site_path: str) -> dict:
        """Resolve a site by hostname + server-relative path; returns the site object
        (including ``id`` and ``displayName``)."""
        path = site_path.strip("/")
        return self._get(f"{GRAPH_BASE}/sites/{hostname}:/{path}").json()

    def resolve_site(self, hostname: str, site_path: str) -> str:
        """Resolve a site to just its id."""
        return self.get_site(hostname, site_path)["id"]

    def list_drives(self, site_id: str) -> list[dict]:
        """List the document libraries (drives) of a site as ``{id, name}`` dicts."""
        drives = self._get(f"{GRAPH_BASE}/sites/{site_id}/drives").json()["value"]
        return [{"id": d["id"], "name": d["name"]} for d in drives]

    def default_drive_id(self, site_id: str) -> str:
        """Return the id of the site's default document library."""
        return self._get(f"{GRAPH_BASE}/sites/{site_id}/drive").json()["id"]

    def resolve_drive(self, site_id: str, library: str | None = None) -> str:
        """Return a drive (document library) id. Empty ``library`` = default library."""
        if not library:
            return self.default_drive_id(site_id)

        for drive in self.list_drives(site_id):
            if drive["name"].lower() == library.lower():
                return drive["id"]
        available = ", ".join(d["name"] for d in self.list_drives(site_id))
        raise ValueError(
            f"Document library '{library}' not found in site. Available: {available}"
        )

    # -- reading -----------------------------------------------------------

    def walk_files(self, drive_id: str, folder: str = "") -> Iterator[dict]:
        """Yield every file (recursively) under ``folder`` in the given drive.

        Each yielded dict has: ``id``, ``name``, ``rel_path`` (relative to ``folder``,
        using ``/``), ``last_modified``, ``etag`` and ``size``.
        """
        if folder:
            start_id = self._get(
                f"{GRAPH_BASE}/drives/{drive_id}/root:/{_encode(folder)}"
            ).json()["id"]
        else:
            start_id = self._root_id(drive_id)
        yield from self._walk(drive_id, start_id, "")

    def _walk(self, drive_id: str, item_id: str, rel: str) -> Iterator[dict]:
        url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/children?$top=200"
        while url:
            data = self._get(url).json()
            for item in data.get("value", []):
                name = item["name"]
                child_rel = f"{rel}/{name}" if rel else name
                if "folder" in item:
                    yield from self._walk(drive_id, item["id"], child_rel)
                elif "file" in item:
                    yield {
                        "id": item["id"],
                        "name": name,
                        "rel_path": child_rel,
                        "last_modified": item.get("lastModifiedDateTime"),
                        # cTag changes on content edits; eTag also changes on
                        # metadata-only edits. Use cTag for incremental skipping.
                        "ctag": item.get("cTag"),
                        "etag": item.get("eTag"),
                        "size": item.get("size", 0),
                    }
            url = data.get("@odata.nextLink")

    def download(self, drive_id: str, item_id: str) -> bytes:
        return self._get(
            f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"
        ).content

    # -- writing -----------------------------------------------------------

    def ensure_folder(self, drive_id: str, folder_path: str) -> str:
        """Create ``folder_path`` (nested, as needed); return the deepest folder's id."""
        parent_id = self._root_id(drive_id)
        for segment in [s for s in folder_path.split("/") if s]:
            parent_id = self._create_or_get_folder(drive_id, parent_id, segment)
        return parent_id

    def _create_or_get_folder(self, drive_id: str, parent_id: str, name: str) -> str:
        body = {
            "name": name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail",
        }
        response = self._session.post(
            f"{GRAPH_BASE}/drives/{drive_id}/items/{parent_id}/children",
            headers=self._headers({"Content-Type": "application/json"}),
            json=body,
        )
        if response.status_code == 409:  # already exists — fetch it by name
            existing = self._get(
                f"{GRAPH_BASE}/drives/{drive_id}/items/{parent_id}:/{_encode(name)}"
            )
            return existing.json()["id"]
        return self._check(response).json()["id"]

    def upload_text(self, drive_id: str, dest_path: str, text: str) -> dict:
        """Upload UTF-8 text to ``dest_path`` (drive-relative), overwriting if present.

        The parent folder must already exist — call :meth:`ensure_folder` first.
        Simple upload; suitable for small files such as Markdown (< 250 MB).
        """
        url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{_encode(dest_path)}:/content"
        response = self._session.put(
            url,
            headers=self._headers({"Content-Type": "text/markdown; charset=utf-8"}),
            data=text.encode("utf-8"),
        )
        return self._check(response).json()

    def delete_item(self, drive_id: str, item_id: str) -> None:
        """Delete an item by id (used to clean up the write-permission probe)."""
        self._check(
            self._session.delete(
                f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}",
                headers=self._headers(),
            )
        )


def _encode(path: str) -> str:
    # Percent-encode each segment (spaces, Norwegian characters, '#', '%', ...)
    # while keeping the '/' path separators intact.
    return quote(path, safe="/")
