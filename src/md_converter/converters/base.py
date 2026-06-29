from abc import ABC, abstractmethod
from pathlib import Path

from md_converter.core.models import ConversionResult


class BaseConverter(ABC):
    supported_extensions: tuple[str, ...] = ()

    @property
    @abstractmethod
    def name(self) -> str: ...

    def supports(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.supported_extensions

    @abstractmethod
    def convert(self, input_path: Path) -> ConversionResult: ...
