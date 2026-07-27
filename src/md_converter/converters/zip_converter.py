from md_converter.converters.markitdown_converter import MarkItDownConverter


class ZipConverter(MarkItDownConverter):
    # MarkItDown extracts the archive and converts each file it recognises,
    # concatenating the results into one Markdown document.
    supported_extensions = (".zip",)
    name = "zip_converter"
