import argparse
from collections import Counter
from pathlib import Path

from md_converter.core.frontmatter import inject_frontmatter
from md_converter.core.manifest import append_manifest_entry
from md_converter.core.paths import build_output_path
from md_converter.core.registry import ConverterRegistry


def _write_failed(
    input_path: Path,
    output_dir: Path,
    error: Exception,
    input_root: Path | None = None,
) -> None:
    output_path = build_output_path(input_path, output_dir, input_root, failed=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("", encoding="utf-8")

    succeeded_path = build_output_path(input_path, output_dir, input_root, failed=False)
    succeeded_path.unlink(missing_ok=True)

    append_manifest_entry(
        output_dir=output_dir,
        source_path=input_path,
        output_path=output_path,
        status="failed",
        error=str(error),
    )

    print(f"Failed:    {input_path.name}")
    print(f"Output:    {output_path}")
    print(f"Reason:    {error}")


def convert_file(
    input_path: Path,
    output_dir: Path,
    input_root: Path | None = None,
    frontmatter: bool = True,
) -> Path:
    input_path = input_path.resolve()
    output_dir = output_dir.resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")
    if not input_path.is_file():
        raise ValueError(f"Input path is not a file: {input_path}")

    registry = ConverterRegistry()
    converter = registry.get_converter(input_path)
    result = converter.convert(input_path)

    output_path = build_output_path(input_path, output_dir, input_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    markdown = inject_frontmatter(result) if frontmatter else result.markdown
    output_path.write_text(markdown, encoding="utf-8")

    result.output_path = output_path

    failed_path = build_output_path(input_path, output_dir, input_root, failed=True)
    failed_path.unlink(missing_ok=True)

    append_manifest_entry(
        output_dir=output_dir,
        source_path=input_path,
        output_path=output_path,
        status="success",
        converter_name=result.converter_name,
        warnings=result.warnings,
    )

    print(f"Converted: {input_path.name}")
    print(f"Converter: {result.converter_name}")
    print(f"Output:    {output_path}")

    if result.warnings:
        print("Warnings:")
        for w in result.warnings:
            print(f"  - {w}")

    return output_path


def convert_directory(
    input_dir: Path,
    output_dir: Path,
    input_root: Path | None = None,
    fail_soft: bool = True,
    frontmatter: bool = True,
) -> None:
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()

    if input_root is None:
        input_root = input_dir

    registry = ConverterRegistry()
    supported = set(registry.supported_extensions())

    all_files = [f for f in input_dir.rglob("*") if f.is_file()]
    files = sorted(f for f in all_files if f.suffix.lower() in supported)
    skipped_exts = Counter(
        f.suffix.lower() for f in all_files if f.suffix.lower() not in supported
    )

    if not files:
        print(f"No supported files found in {input_dir}")
        print(f"Supported extensions: {', '.join(sorted(supported))}")
        return

    print(f"Found {len(files)} file(s) to convert.")
    if skipped_exts:
        breakdown = ", ".join(
            f"{ext or '(no ext)'}: {count}" for ext, count in sorted(skipped_exts.items())
        )
        print(f"Skipped {sum(skipped_exts.values())} file(s) with unsupported extensions ({breakdown}).")
    print()

    succeeded = 0
    failed = 0

    for file_path in files:
        try:
            convert_file(file_path, output_dir, input_root, frontmatter)
            succeeded += 1
        except Exception as error:
            if not fail_soft:
                raise
            _write_failed(file_path, output_dir, error, input_root)
            failed += 1
        print()

    print(f"Done. {succeeded} converted, {failed} failed.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert supported files to Markdown.")

    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        default=None,
        help="Path to a file or directory to convert. Defaults to ./input",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory where Markdown files should be written. Defaults to ./output",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Raise errors instead of creating failed-conversion placeholders.",
    )
    parser.add_argument(
        "--no-frontmatter",
        dest="frontmatter",
        action="store_false",
        help="Skip injecting YAML frontmatter (source, converter, timestamp) into output files.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # No arg: flat output from ./input. With arg: top-level folder name is preserved in output.
    staging_mode = args.input is None
    input_path = (Path("input") if staging_mode else args.input).resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    if input_path.is_dir():
        input_root = input_path if staging_mode else input_path.parent
        convert_directory(
            input_dir=input_path,
            output_dir=args.output_dir,
            input_root=input_root,
            fail_soft=not args.strict,
            frontmatter=args.frontmatter,
        )
    else:
        try:
            convert_file(
                input_path=input_path,
                output_dir=args.output_dir,
                frontmatter=args.frontmatter,
            )
        except Exception as error:
            if args.strict:
                raise
            _write_failed(input_path=input_path, output_dir=args.output_dir, error=error)


if __name__ == "__main__":
    main()
