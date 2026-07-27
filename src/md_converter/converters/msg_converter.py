from md_converter.converters.markitdown_converter import MarkItDownConverter


class MsgConverter(MarkItDownConverter):
    supported_extensions = (".msg",)
    name = "msg_converter"
