from md_converter.converters.markitdown_converter import MarkItDownConverter


class DocxConverter(MarkItDownConverter):
    supported_extensions = (".docx", ".dotx", ".docm")
    name = "docx_converter"
    extension_aliases = {".dotx": ".docx", ".docm": ".docx"}
