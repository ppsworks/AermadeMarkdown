from md_converter.converters.markitdown_converter import MarkItDownConverter


class MarkitdownPdfConverter(MarkItDownConverter):
    supported_extensions = (".pdf",)
    name = "pdf_markitdown"
