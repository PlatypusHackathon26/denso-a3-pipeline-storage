"""Abstract base class for document parsing engines."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from schemas.document import ProcessedDocument


class BaseEngine(ABC):
    """Abstract interface that all parsing engines must fulfill."""

    def __init__(self, name: str = "BaseEngine") -> None:
        self.name = name

    @abstractmethod
    def parse(
        self,
        file_path: Path,
        access_level: int = 1,
        doc_id: Optional[str] = None,
        file_hash: Optional[str] = None,
    ) -> ProcessedDocument:
        """Parse raw document into standardized ProcessedDocument.

        Args:
            file_path: Path to the raw input file.
            access_level: Access/security clearance level (1, 2, 3).
            doc_id: Optional precomputed document ID.
            file_hash: Optional precomputed hash.

        Returns:
            ProcessedDocument complying with schemas/document.py
        """
        pass

    def supports(self, extension: str) -> bool:
        """Check if engine supports the given extension (case-insensitive, with dot)."""
        return False
