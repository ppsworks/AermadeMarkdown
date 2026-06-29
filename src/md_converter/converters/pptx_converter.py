from md_converter.converters.markitdown_converter import MarkItDownConverter


class PptxConverter(MarkItDownConverter):
    supported_extensions = (".pptx",)
    name = "pptx_converter"
