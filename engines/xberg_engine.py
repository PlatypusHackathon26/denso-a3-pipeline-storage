"""High-speed parsing engine for Office documents (Word, Excel), text, and code files."""

import re
from pathlib import Path
from typing import List, Optional
import pandas as pd

from configs.settings import settings
from core.hasher import hasher
from core.storage import storage
from engines.base import BaseEngine
from schemas.document import DocMetadata, ExtractedImage, ProcessedDocument, TableItem
from utils.lang_detector import detect_language
from utils.text_cleaner import clean_text

CAPTION_PATTERN = re.compile(
    r"^(hình|hình ảnh|ảnh|figure|fig\.|bảng|table|sơ đồ|chart)\s*[\d\.\-_:]+.*",
    re.IGNORECASE,
)


class XbergEngine(BaseEngine):
    """Engine for parsing Office formats (.docx, .xlsx, .csv) and plain text/code."""

    def __init__(self) -> None:
        super().__init__(name="xberg")

    def supports(self, extension: str) -> bool:
        return extension.lower() in settings.XBERG_EXTENSIONS

    def _infer_factory_and_type(self, file_path: Path) -> tuple[str, str]:
        """Infer factory_code and doc_type from filename."""
        name = file_path.name.upper()
        factory_code = "DENSO_UNKNOWN"
        for code in ("DENSO_HN", "DENSO_HCM", "DENSO_DN", "DENSO"):
            if code in name:
                factory_code = code if code != "DENSO" else "DENSO_CORP"
                break

        doc_type = "technical_document"
        lower_name = file_path.name.lower()
        if any(k in lower_name for k in ("sop", "huong_dan", "quy_trinh", "manual")):
            doc_type = "maintenance_manual"
        elif any(k in lower_name for k in ("bao_cao", "report", "nhat_ky")):
            doc_type = "inspection_report"
        elif any(k in lower_name for k in ("phu_tung", "linh_kien", "inventory", "stock")):
            doc_type = "parts_inventory"

        return factory_code, doc_type

    def parse(
        self,
        file_path: Path,
        access_level: int = 1,
        doc_id: Optional[str] = None,
        file_hash: Optional[str] = None,
    ) -> ProcessedDocument:
        ext = file_path.suffix.lower()
        computed_hash = file_hash or hasher.compute_hash(file_path)
        resolved_doc_id = doc_id or hasher.generate_doc_id(file_path, computed_hash)
        file_size_kb = round(file_path.stat().st_size / 1024, 2)
        factory_code, doc_type = self._infer_factory_and_type(file_path)

        if ext in (".docx", ".doc"):
            return self._parse_docx(
                file_path,
                access_level,
                resolved_doc_id,
                computed_hash,
                file_size_kb,
                factory_code,
                doc_type,
            )
        elif ext in (".xlsx", ".xls", ".csv"):
            return self._parse_tabular(
                file_path,
                access_level,
                resolved_doc_id,
                computed_hash,
                file_size_kb,
                factory_code,
                doc_type,
            )
        else:
            return self._parse_text(
                file_path,
                access_level,
                resolved_doc_id,
                computed_hash,
                file_size_kb,
                factory_code,
                doc_type,
            )


    def _parse_docx(
        self,
        file_path: Path,
        access_level: int,
        doc_id: str,
        file_hash: str,
        file_size_kb: float,
        factory_code: str,
        doc_type: str,
    ) -> ProcessedDocument:
        import docx

        doc = docx.Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        cleaned_text = clean_text("\n\n".join(paragraphs))

        tables: List[TableItem] = []
        for i, table in enumerate(doc.tables, start=1):
            rows_data: List[List[str]] = []
            for row in table.rows:
                row_cells = [clean_text(cell.text) for cell in row.cells]
                rows_data.append(row_cells)

            if rows_data:
                headers = rows_data[0]
                col_count = len(headers)
                row_count = len(rows_data)
                md_lines = [
                    "| " + " | ".join(headers) + " |",
                    "| " + " | ".join(["---"] * col_count) + " |",
                ]
                for r in rows_data[1:]:
                    padded_r = r + [""] * (col_count - len(r))
                    md_lines.append("| " + " | ".join(padded_r[:col_count]) + " |")

                caption = f"Bảng {i}: Dữ liệu trích xuất từ {file_path.name}"
                tables.append(
                    TableItem(
                        table_id=f"{doc_id}_t{i}",
                        page=i,
                        caption=caption,
                        total_rows=row_count,
                        total_cols=col_count,
                        markdown="\n".join(md_lines),
                    )
                )

        images: List[ExtractedImage] = []
        if settings.EXTRACT_IMAGES:
            try:
                img_idx = 1
                for rel in doc.part.related_parts.values():
                    if "image" in rel.content_type:
                        img_filename = f"{doc_id}_img{img_idx}.png"
                        rel_path = storage.save_image(
                            image_data=rel.blob,
                            image_name=img_filename,
                            subfolder=doc_id,
                        )

                        # Extract surrounding context text from paragraphs
                        context = ""
                        native_caption = f"Hình {img_idx}: Ảnh minh họa thiết bị"
                        if paragraphs:
                            idx = min(img_idx - 1, len(paragraphs) - 1)
                            context = paragraphs[idx][:250]
                            # Check if paragraph matches caption regex
                            if CAPTION_PATTERN.match(paragraphs[idx]):
                                native_caption = paragraphs[idx]

                        images.append(
                            ExtractedImage(
                                image_id=f"{doc_id}_img{img_idx}",
                                page=None,
                                image_name=img_filename,
                                saved_path=str(rel_path).replace("\\", "/"),
                                native_caption=native_caption,
                                context_text=context,
                                vlm_caption=None,
                            )
                        )
                        img_idx += 1
            except Exception:
                pass

        return ProcessedDocument(
            doc_id=doc_id,
            metadata=DocMetadata(
                factory_code=factory_code,
                doc_type=doc_type,
                source_file=file_path.name,
                source_type=file_path.suffix.lstrip(".").lower(),
                language=detect_language(cleaned_text),
                access_level=access_level,
                engine_used=self.name,
                total_pages=len(doc.paragraphs),
                file_size_kb=file_size_kb,
                is_corrupted=False,
                hash_value=file_hash,
            ),
            cleaned_text=cleaned_text,
            tables=tables,
            images=images,
        )


    def _parse_tabular(
        self,
        file_path: Path,
        access_level: int,
        doc_id: str,
        file_hash: str,
        file_size_kb: float,
        factory_code: str,
        doc_type: str,
    ) -> ProcessedDocument:
        ext = file_path.suffix.lower()
        tables: List[TableItem] = []
        text_summaries: List[str] = []

        if ext == ".csv":
            df = pd.read_csv(file_path)
            md_tbl = df.to_markdown(index=False)
            tables.append(
                TableItem(
                    table_id=f"{doc_id}_t1",
                    page=1,
                    caption=f"Bảng dữ liệu: {file_path.name}",
                    total_rows=len(df),
                    total_cols=len(df.columns),
                    markdown=md_tbl,
                )
            )
            text_summaries.append(f"Sheet: default\n{md_tbl}")
            total_sheets = 1
        else:
            excel_file = pd.ExcelFile(file_path)
            total_sheets = len(excel_file.sheet_names)
            for idx, sheet_name in enumerate(excel_file.sheet_names, start=1):
                df = pd.read_excel(excel_file, sheet_name=sheet_name)
                md_tbl = df.to_markdown(index=False)
                tables.append(
                    TableItem(
                        table_id=f"{doc_id}_t{idx}",
                        page=idx,
                        caption=f"Bảng: {sheet_name}",
                        total_rows=len(df),
                        total_cols=len(df.columns),
                        markdown=md_tbl,
                    )
                )
                text_summaries.append(f"Sheet: {sheet_name}\n{md_tbl}")

        combined_text = clean_text("\n\n".join(text_summaries))
        return ProcessedDocument(
            doc_id=doc_id,
            metadata=DocMetadata(
                factory_code=factory_code,
                doc_type=doc_type,
                source_file=file_path.name,
                source_type=file_path.suffix.lstrip(".").lower(),
                language=detect_language(combined_text),
                access_level=access_level,
                engine_used=self.name,
                total_pages=total_sheets,
                file_size_kb=file_size_kb,
                is_corrupted=False,
                hash_value=file_hash,
            ),
            cleaned_text=combined_text,
            tables=tables,
            images=[],
        )

    def _parse_text(
        self,
        file_path: Path,
        access_level: int,
        doc_id: str,
        file_hash: str,
        file_size_kb: float,
        factory_code: str,
        doc_type: str,
    ) -> ProcessedDocument:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            raw_text = f.read()

        cleaned = clean_text(raw_text)
        return ProcessedDocument(
            doc_id=doc_id,
            metadata=DocMetadata(
                factory_code=factory_code,
                doc_type=doc_type,
                source_file=file_path.name,
                source_type=file_path.suffix.lstrip(".").lower(),
                language=detect_language(cleaned),
                access_level=access_level,
                engine_used=self.name,
                total_pages=1,
                file_size_kb=file_size_kb,
                is_corrupted=False,
                hash_value=file_hash,
            ),
            cleaned_text=cleaned,
            tables=[],
            images=[],
        )


