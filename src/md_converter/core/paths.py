from pathlib import Path


def build_output_path(
    input_path: Path,
    output_dir: Path,
    input_root: Path | None = None,
    failed: bool = False,
) -> Path:
    suffix = "_failed_to_convert" if failed else ""
    filename = f"{input_path.stem}{suffix}.md"

    if input_root is not None:
        return output_dir / input_path.parent.relative_to(input_root) / filename

    return output_dir / filename
