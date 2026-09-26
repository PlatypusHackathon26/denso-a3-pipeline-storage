"""Configuration settings for ingestion pipeline."""

from pathlib import Path


class Settings:
    """Project-wide settings and directories configuration."""

    # Base directory
    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    # Data directories
    DATA_DIR: Path = BASE_DIR / "data"
    RAW_DIR: Path = DATA_DIR / "01_raw"
    MEDIA_DIR: Path = DATA_DIR / "02_media"
    PROCESSED_DIR: Path = DATA_DIR / "03_processed"

    # Runtime configuration
    DEVICE: str = "cuda"  # "cuda" or "cpu"
    HASH_ALGORITHM: str = "sha256"  # "sha256" or "md5"
    DEDUPLICATE: bool = True

    # Image / Media extraction
    EXTRACT_IMAGES: bool = True
    IMAGE_FORMAT: str = "png"

    # Supported file mappings
    DOCLING_EXTENSIONS: tuple[str, ...] = (".pdf",)
    XBERG_EXTENSIONS: tuple[str, ...] = (
        ".docx",
        ".doc",
        ".xlsx",
        ".xls",
        ".csv",
        ".txt",
        ".md",
        ".json",
        ".py",
        ".c",
        ".cpp",
        ".h",
    )
    AUDIO_EXTENSIONS: tuple[str, ...] = (".mp3", ".wav", ".m4a", ".flac", ".ogg")

    @classmethod
    def ensure_dirs(cls) -> None:
        """Create necessary data directories if they don't exist."""
        for path in (cls.DATA_DIR, cls.RAW_DIR, cls.MEDIA_DIR, cls.PROCESSED_DIR):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()

