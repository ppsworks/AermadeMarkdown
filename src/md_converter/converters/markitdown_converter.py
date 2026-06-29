from pathlib import Path

from markitdown import MarkItDown

from md_converter.converters.base import BaseConverter
from md_converter.core.models import ConversionResult


class MarkItDownConverter(BaseConverter):
    def convert(self, input_path: Path) -> ConversionResult:
        result = MarkItDown().convert(str(input_path))
        markdown = result.text_content or ""

        warnings = []
        if not markdown.strip():
            warnings.append("Conversion produced empty output.")

        return ConversionResult(
            source_path=input_path,
            output_path=None,
            markdown=markdown,
            converter_name=self.name,
            title=str(result.title) if result.title else None,
            warnings=warnings,
        )
