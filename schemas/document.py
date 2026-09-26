"""Document schema specifications adhering to updated output_format.json."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TableItem(BaseModel):
    """Schema representing an extracted table."""

    table_id: str = Field(..., description="Unique identifier for the table (e.g. DOC_t1)")
    page: Optional[int] = Field(
        default=None,
        description="Page number or sheet index where the table was found",
    )
    caption: Optional[str] = Field(
        default="",
        description="Caption or title of the table if detected",
    )
    total_rows: int = Field(default=0, description="Total number of rows in the table")
    total_cols: int = Field(default=0, description="Total number of columns in the table")
    markdown: str = Field(
        ...,
        description="Markdown representation of the table",
    )


class ExtractedImage(BaseModel):
    """Schema representing an extracted image with rich contextual metadata."""

    image_id: str = Field(..., description="Unique ID of the image (e.g. DOC_img1)")
    page: Optional[int] = Field(default=None, description="Page number where the image appears")
    image_name: str = Field(..., description="Filename of the saved image")
    saved_path: str = Field(..., description="Path relative to base (e.g. 02_media/doc/img.png)")
    native_caption: Optional[str] = Field(
        default="",
        description="Original caption text found near the image in the document",
    )
    context_text: Optional[str] = Field(
        default="",
        description="Surrounding text context providing semantic meaning for unlabelled images",
    )
    vlm_caption: Optional[str] = Field(
        default=None,
        description="Generated detailed mechanical/visual description from a Vision-Language Model",
    )


class DocMetadata(BaseModel):
    """Metadata about document origin, categorization, and processing details."""

    factory_code: str = Field(default="DENSO_UNKNOWN", description="Factory code (e.g. DENSO_HN)")
    doc_type: str = Field(
        default="technical_document",
        description="Document type (e.g. maintenance_manual, sop, report)",
    )
    source_file: str = Field(..., description="Original filename with extension")
    source_type: str = Field(..., description="File extension without dot (pdf, docx, etc.)")
    language: str = Field(default="vi", description="Language code detected (e.g. vi, en, ja)")
    access_level: int = Field(default=1, description="Security/access level (1, 2, 3)")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp of processing",
    )
    engine_used: Optional[str] = Field(
        default=None,
        description="Engine used to parse this document (e.g. docling, xberg)",
    )
    total_pages: Optional[int] = Field(
        default=None,
        description="Total pages or sheet count in original file",
    )
    file_size_kb: float = Field(
        default=0.0,
        description="File size in kilobytes",
    )
    is_corrupted: bool = Field(
        default=False,
        description="Whether file had extraction corruption or missing sections",
    )
    hash_value: Optional[str] = Field(
        default=None,
        description="MD5 or SHA256 checksum of the source file",
    )
    extra: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom additional metadata attributes",
    )


class ProcessedDocument(BaseModel):
    """Master document schema for RAG pipeline ingestion."""

    doc_id: str = Field(..., description="Unique document ID (e.g. DENSO_<hash>)")
    metadata: DocMetadata = Field(
        ...,
        description="Document metadata and access classification",
    )
    cleaned_text: str = Field(..., description="Normalized clean text for LLM/RAG embedding")
    tables: List[TableItem] = Field(
        default_factory=list,
        description="List of structured tables in Markdown format",
    )
    images: List[ExtractedImage] = Field(
        default_factory=list,
        description="Extracted images with surrounding context and optional VLM summary",
    )

