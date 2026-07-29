import io
from email import policy
from email.parser import BytesParser
from pathlib import Path

from markitdown import MarkItDown, StreamInfo

from md_converter.converters.base import BaseConverter
from md_converter.core.models import ConversionResult

# Headers written to the top of the output, in this order.
HEADERS = ("From", "To", "Cc", "Date", "Subject")


class EmlConverter(BaseConverter):
    """Converts RFC-822 email files (.eml) to Markdown.

    MarkItDown handles .msg but not .eml, whose ``message/rfc822`` type falls
    outside the types it accepts. The standard library parses it directly.
    """

    supported_extensions = (".eml",)
    name = "eml_converter"

    def convert(self, input_path: Path) -> ConversionResult:
        with input_path.open("rb") as file:
            message = BytesParser(policy=policy.default).parse(file)

        warnings: list[str] = []
        lines = [
            f"**{header}:** {value}"
            for header in HEADERS
            if (value := message.get(header))
        ]

        body, body_warning = self._body(message)
        if body_warning:
            warnings.append(body_warning)

        attachments = [
            name for part in message.walk() if (name := part.get_filename())
        ]
        if attachments:
            lines.append("")
            lines.append("**Attachments:** " + ", ".join(attachments))

        if lines:
            lines.append("")
            lines.append("---")
            lines.append("")
        lines.append(body)

        markdown = "\n".join(lines).strip() + "\n"
        if not body.strip():
            warnings.append("Email had no readable body.")

        subject = message.get("Subject")
        return ConversionResult(
            source_path=input_path,
            output_path=None,
            markdown=markdown,
            converter_name=self.name,
            title=str(subject) if subject else None,
            warnings=warnings,
        )

    def _body(self, message) -> tuple[str, str | None]:
        """Return the message body as Markdown, preferring the plain-text part."""
        plain = message.get_body(preferencelist=("plain",))
        if plain is not None:
            return self._content(plain), None

        html = message.get_body(preferencelist=("html",))
        if html is None:
            return "", None

        # HTML-only email: reuse MarkItDown rather than stripping tags by hand.
        raw = self._content(html)
        try:
            result = MarkItDown().convert_stream(
                io.BytesIO(raw.encode("utf-8")),
                stream_info=StreamInfo(extension=".html"),
            )
            return result.text_content or "", None
        except Exception as error:  # noqa: BLE001 (fall back to the raw HTML)
            return raw, f"Could not convert HTML body ({error}); kept raw HTML."

    @staticmethod
    def _content(part) -> str:
        try:
            return part.get_content()
        except (LookupError, UnicodeDecodeError):
            # Unknown or mislabelled charset, so decode leniently rather than fail.
            payload = part.get_payload(decode=True) or b""
            return payload.decode("utf-8", errors="replace")
