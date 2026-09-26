"""File hashing and duplicate checking utility."""

import hashlib
from pathlib import Path
from typing import Optional, Set
from configs.settings import settings


class Hasher:
    """Manages file hashing and tracking processed documents to avoid duplicate work."""

    def __init__(self, algorithm: Optional[str] = None) -> None:
        self.algorithm = algorithm or settings.HASH_ALGORITHM
        self._processed_hashes: Set[str] = set()
        self._load_existing_hashes()

    def _load_existing_hashes(self) -> None:
        """Scan processed directory to index existing hashes if available."""
        if not settings.PROCESSED_DIR.exists():
            return

        import json

        for json_file in settings.PROCESSED_DIR.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    h = data.get("metadata", {}).get("hash_value")
                    if h:
                        self._processed_hashes.add(h)
            except Exception:
                continue

    def compute_hash(self, file_path: Path) -> str:
        """Compute checksum (SHA-256 or MD5) of a file."""
        hasher = hashlib.sha256() if self.algorithm == "sha256" else hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def generate_doc_id(self, file_path: Path, file_hash: Optional[str] = None) -> str:
        """Generate a short unique document ID using prefix and hash."""
        h = file_hash or self.compute_hash(file_path)
        return f"DENSO_{h[:8].upper()}"

    def is_processed(self, file_hash: str) -> bool:
        """Check if file hash has already been processed."""
        return file_hash in self._processed_hashes

    def register_hash(self, file_hash: str) -> None:
        """Register newly processed hash."""
        self._processed_hashes.add(file_hash)


hasher = Hasher()
