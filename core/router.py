"""Router to dispatch raw files to their designated parsing engine."""

from pathlib import Path
from typing import Dict, Optional

from configs.settings import settings
from engines.base import BaseEngine
from engines.docling_engine import DoclingEngine
from engines.xberg_engine import XbergEngine


class Router:
    """Dispatches files to the appropriate engine based on file extension."""

    def __init__(self) -> None:
        self.docling_engine = DoclingEngine()
        self.xberg_engine = XbergEngine()
        self._custom_engine_map: Dict[str, BaseEngine] = {}

    def register_engine(self, extension: str, engine: BaseEngine) -> None:
        """Register or override an engine for a specific file extension."""
        ext = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        self._custom_engine_map[ext] = engine

    def get_engine(self, file_path: Path) -> Optional[BaseEngine]:
        """Resolve engine for given file path based on extension."""
        ext = file_path.suffix.lower()

        # 1. Custom registered engine
        if ext in self._custom_engine_map:
            return self._custom_engine_map[ext]

        # 2. PDF -> Docling Engine
        if ext in settings.DOCLING_EXTENSIONS or self.docling_engine.supports(ext):
            return self.docling_engine

        # 3. Office / Txt / Code -> Xberg Engine
        if ext in settings.XBERG_EXTENSIONS or self.xberg_engine.supports(ext):
            return self.xberg_engine

        return None


router = Router()
