from pathlib import PurePosixPath


def build_mirror_path(
    mirror_root: str,
    source_rel_path: str,
    failed: bool = False,
) -> str:
    """Build the destination (drive-relative) path for a source file's Markdown mirror.

    This is the SharePoint/Graph analogue of ``core.paths.build_output_path``: it maps
    a source file to its ``.md`` destination while preserving the source's folder
    structure underneath a top-level ``mirror_root`` folder that identifies the source.

    Args:
        mirror_root: top folder(s) in the destination library under which the source
            tree is mirrored, e.g. ``"75010 Sunrise Wind"``. May be empty.
        source_rel_path: the source file's path relative to the scanned source root,
            using ``/`` separators, e.g. ``"Prosedyrer/rev A/file.docx"``.
        failed: append the ``_failed_to_convert`` marker to the stem.

    Returns:
        A POSIX-style, drive-relative path such as
        ``"75010 Sunrise Wind/Prosedyrer/rev A/file.md"``.
    """
    source = PurePosixPath(source_rel_path)
    suffix = "_failed_to_convert" if failed else ""
    filename = f"{source.stem}{suffix}.md"

    parts = [p for p in PurePosixPath(mirror_root).parts if p]
    parts.extend(source.parent.parts)
    parts.append(filename)
    return "/".join(parts)
