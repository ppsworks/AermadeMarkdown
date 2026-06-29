from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConversionResult:
    source_path: Path
    output_path: Path | None
    markdown: str
    converter_name: str
    title: str | None = None
    warnings: list[str] = field(default_factory=list)
