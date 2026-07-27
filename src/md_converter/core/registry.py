from pathlib import Path

from md_converter.converters.base import BaseConverter
from md_converter.converters.docx_converter import DocxConverter
from md_converter.converters.eml_converter import EmlConverter
from md_converter.converters.html_converter import HtmlConverter
from md_converter.converters.msg_converter import MsgConverter
from md_converter.converters.pdf_converter import PdfConverter
from md_converter.converters.pptx_converter import PptxConverter
from md_converter.converters.xlsx_converter import XlsxConverter
from md_converter.converters.zip_converter import ZipConverter


class ConverterRegistry:
    def __init__(self) -> None:
        # To add a format: create converter, import it, add an instance here.
        self._converters: list[BaseConverter] = [
            DocxConverter(),
            EmlConverter(),
            HtmlConverter(),
            MsgConverter(),
            PdfConverter(),
            PptxConverter(),
            XlsxConverter(),
            ZipConverter(),
        ]

    def get_converter(self, file_path: Path) -> BaseConverter:
        for converter in self._converters:
            if converter.supports(file_path):
                return converter

        raise ValueError(
            f"No converter registered for '{file_path.suffix}'. "
            f"Supported: {', '.join(self.supported_extensions())}"
        )

    def supported_extensions(self) -> list[str]:
        exts = []
        for c in self._converters:
            exts.extend(c.supported_extensions)
        return sorted(set(exts))
