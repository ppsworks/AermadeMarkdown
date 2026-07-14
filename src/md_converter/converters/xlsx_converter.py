from md_converter.converters.markitdown_converter import MarkItDownConverter


class XlsxConverter(MarkItDownConverter):
    supported_extensions = (".xlsx", ".xlsm", ".xls")
    name = "xlsx_converter"
    extension_aliases = {".xlsm": ".xlsx"}
