from pathlib import PurePosixPath


def build_mirror_path(
    mirror_root: str,
    source_rel_path: str,
    failed: bool = False,
) -> str:
    # SharePoint/Graph version of core.paths.build_output_path: maps a source
    # file to its .md destination, keeping the folder structure under mirror_root.
    # e.g. mirror_root="75010 Sunrise Wind", source_rel_path="Prosedyrer/rev A/file.docx"
    # -> "75010 Sunrise Wind/Prosedyrer/rev A/file.md"
    source = PurePosixPath(source_rel_path)
    suffix = "_failed_to_convert" if failed else ""
    filename = f"{source.stem}{suffix}.md"

    parts = [p for p in PurePosixPath(mirror_root).parts if p]
    parts.extend(source.parent.parts)
    parts.append(filename)
    return "/".join(parts)
