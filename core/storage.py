"""Storage manager for handling raw files, media assets, and processed JSON documents."""

import json
import shutil
from pathlib import Path
from typing import Optional, Union
from PIL import Image
import io

from configs.settings import settings
from schemas.document import ProcessedDocument


class Storage:
    """Manages file persistence across data/ subdirectories."""

    def __init__(self) -> None:
        self.raw_dir = settings.RAW_DIR
        self.media_dir = settings.MEDIA_DIR
        self.processed_dir = settings.PROCESSED_DIR
        self.setup()

    def setup(self) -> None:
        """Ensure storage directory structure exists."""
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def save_raw(self, source_path: Path, overwrite: bool = False) -> Path:
        """Copy incoming raw file into 01_raw directory if not already there."""
        destination = self.raw_dir / source_path.name
        if destination.resolve() == source_path.resolve():
            return destination
        if not destination.exists() or overwrite:
            shutil.copy2(source_path, destination)
        return destination

    def save_image(
        self,
        image_data: Union[bytes, Image.Image],
        image_name: str,
        subfolder: Optional[str] = None,
    ) -> Path:
        """Save extracted image to 02_media directory.

        Args:
            image_data: Either raw bytes or PIL Image.
            image_name: Destination filename (e.g. img_page1_0.png).
            subfolder: Optional subfolder inside 02_media (e.g. doc_id).

        Returns:
            Relative Path from BASE_DIR (e.g. 02_media/doc_id/image.png)
        """
        target_dir = self.media_dir / subfolder if subfolder else self.media_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        target_file = target_dir / image_name

        if isinstance(image_data, bytes):
            with open(target_file, "wb") as f:
                f.write(image_data)
        elif isinstance(image_data, Image.Image):
            image_data.save(target_file, format=settings.IMAGE_FORMAT.upper())

        try:
            return target_file.relative_to(settings.BASE_DIR)
        except ValueError:
            return target_file.relative_to(self.media_dir)

    def save_document(
        self,
        document: ProcessedDocument,
        filename: Optional[str] = None,
        indent: int = 2,
    ) -> Path:
        """Serialize and save ProcessedDocument to 03_processed as a JSON file.

        Args:
            document: ProcessedDocument instance.
            filename: Optional custom filename. Defaults to <source_stem>.json.
            indent: JSON indentation.

        Returns:
            Path to saved JSON file.
        """
        if not filename:
            stem = Path(document.metadata.source_file).stem
            filename = f"{stem}.json"

        target_path = self.processed_dir / filename
        data = document.model_dump()

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)

        return target_path

    def load_document(self, filename: str) -> Optional[ProcessedDocument]:
        """Load ProcessedDocument from 03_processed."""
        target_path = self.processed_dir / filename
        if not target_path.exists():
            return None
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return ProcessedDocument.model_validate(data)


storage = Storage()
