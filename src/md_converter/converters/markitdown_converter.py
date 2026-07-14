from pathlib import Path

from markitdown import MarkItDown, StreamInfo

from md_converter.converters.base import BaseConverter
from md_converter.core.models import ConversionResult


class MarkItDownConverter(BaseConverter):
    # Extensions MarkItDown does not recognize, mapped to an equivalent
    # extension it does (e.g. .xlsm files are read the same way as .xlsx).
    extension_aliases: dict[str, str] = {}

    def convert(self, input_path: Path) -> ConversionResult:
        alias = self.extension_aliases.get(input_path.suffix.lower())
        stream_info = StreamInfo(extension=alias) if alias else None
        result = MarkItDown().convert(str(input_path), stream_info=stream_info)
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
