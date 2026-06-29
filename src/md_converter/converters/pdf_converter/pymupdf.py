from pathlib import Path

import pymupdf4llm

from md_converter.converters.base import BaseConverter
from md_converter.core.models import ConversionResult


class PyMuPdfConverter(BaseConverter):
    supported_extensions = (".pdf",)
    name = "pdf_pymupdf4llm"

    def convert(self, input_path: Path) -> ConversionResult:
        markdown = pymupdf4llm.to_markdown(str(input_path))

        warnings = []
        if not markdown.strip():
            warnings.append("Conversion produced empty output.")

        return ConversionResult(
            source_path=input_path,
            output_path=None,
            markdown=markdown,
            converter_name=self.name,
            warnings=warnings,
        )
