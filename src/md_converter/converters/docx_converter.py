from md_converter.converters.markitdown_converter import MarkItDownConverter


class DocxConverter(MarkItDownConverter):
    supported_extensions = (".docx",)
    name = "docx_converter"
