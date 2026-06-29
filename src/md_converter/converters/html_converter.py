from md_converter.converters.markitdown_converter import MarkItDownConverter


class HtmlConverter(MarkItDownConverter):
    supported_extensions = (".html", ".htm")
    name = "html_converter"
