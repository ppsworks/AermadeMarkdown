from pathlib import Path

import fitz

from md_converter.converters.base import BaseConverter
from md_converter.converters.pdf_converter.markitdown import MarkitdownPdfConverter
from md_converter.converters.pdf_converter.pymupdf import PyMuPdfConverter
from md_converter.core.models import ConversionResult

# short/image-heavy files use MarkItDown, long text-only ones use PyMuPDF
_TEXT_HEAVY_MIN_PAGES = 15


def _is_text_heavy(path: Path) -> bool:
    with fitz.open(str(path)) as doc:
        if len(doc) < _TEXT_HEAVY_MIN_PAGES:
            return False
        return not any(page.get_images() for page in doc)


class PdfConverter(BaseConverter):
    supported_extensions = (".pdf",)
    name = "pdf_converter"

    def __init__(self) -> None:
        self._pymupdf = PyMuPdfConverter()
        self._markitdown = MarkitdownPdfConverter()

    def convert(self, input_path: Path) -> ConversionResult:
        backend = self._pymupdf if _is_text_heavy(input_path) else self._markitdown
        return backend.convert(input_path)
