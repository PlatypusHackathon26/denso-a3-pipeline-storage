"""Document parsing engine for PDF files using Docling or robust fallbacks."""

import io
import re
from pathlib import Path
from typing import List, Optional
from PIL import Image

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


class DoclingEngine(BaseEngine):
    """PDF parsing engine.

    Uses `docling` if installed and supported; otherwise gracefully falls back to
    `pdfplumber` which provides high-fidelity text, markdown tables, and image extraction.
    """

    def __init__(self) -> None:
        super().__init__(name="docling")
        self._docling_available = self._check_docling()

    def _check_docling(self) -> bool:
        try:
            import docling  # type: ignore # noqa: F401
            return True
        except ImportError:
            return False

    def supports(self, extension: str) -> bool:
        return extension.lower() in settings.DOCLING_EXTENSIONS

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
        computed_hash = file_hash or hasher.compute_hash(file_path)
        resolved_doc_id = doc_id or hasher.generate_doc_id(file_path, computed_hash)
        file_size_kb = round(file_path.stat().st_size / 1024, 2)
        factory_code, doc_type = self._infer_factory_and_type(file_path)

        if self._docling_available:
            return self._parse_with_docling(
                file_path=file_path,
                access_level=access_level,
                doc_id=resolved_doc_id,
                file_hash=computed_hash,
                file_size_kb=file_size_kb,
                factory_code=factory_code,
                doc_type=doc_type,
            )

        return self._parse_with_fallback(
            file_path=file_path,
            access_level=access_level,
            doc_id=resolved_doc_id,
            file_hash=computed_hash,
            file_size_kb=file_size_kb,
            factory_code=factory_code,
            doc_type=doc_type,
        )


    def _parse_with_docling(
        self,
        file_path: Path,
        access_level: int,
        doc_id: str,
        file_hash: str,
        file_size_kb: float,
        factory_code: str,
        doc_type: str,
    ) -> ProcessedDocument:
        from docling.document_converter import DocumentConverter  # type: ignore

        converter = DocumentConverter()
        result = converter.convert(str(file_path))
        doc = result.document

        md_text = doc.export_to_markdown()
        cleaned = clean_text(md_text)
        detected_lang = detect_language(cleaned)

        tables: List[TableItem] = []
        for i, tbl in enumerate(getattr(doc, "tables", []), start=1):
            tbl_md = tbl.export_to_markdown() if hasattr(tbl, "export_to_markdown") else str(tbl)
            page_no = getattr(tbl, "page_no", None) or i
            tables.append(
                TableItem(
                    table_id=f"{doc_id}_t{i}",
                    page=page_no,
                    caption=f"Bảng {i}: Trích xuất từ {file_path.name}",
                    total_rows=len(getattr(tbl, "rows", [])) or 1,
                    total_cols=len(getattr(tbl, "cols", [])) or 1,
                    markdown=tbl_md,
                )
            )

        return ProcessedDocument(
            doc_id=doc_id,
            metadata=DocMetadata(
                factory_code=factory_code,
                doc_type=doc_type,
                source_file=file_path.name,
                source_type=file_path.suffix.lstrip(".").lower(),
                language=detected_lang,
                access_level=access_level,
                engine_used=self.name,
                total_pages=getattr(doc, "num_pages", None),
                file_size_kb=file_size_kb,
                is_corrupted=False,
                hash_value=file_hash,
            ),
            cleaned_text=cleaned,
            tables=tables,
            images=[],
        )


    def _parse_with_fallback(
        self,
        file_path: Path,
        access_level: int,
        doc_id: str,
        file_hash: str,
        file_size_kb: float,
        factory_code: str,
        doc_type: str,
    ) -> ProcessedDocument:
        import pdfplumber

        page_texts: List[str] = []
        tables: List[TableItem] = []
        images: List[ExtractedImage] = []
        is_corrupted = False
        img_counter = 1
        table_counter = 1

        try:
            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                for page_idx, page in enumerate(pdf.pages, start=1):
                    raw_text = page.extract_text() or ""
                    cleaned_page_text = clean_text(raw_text)
                    if cleaned_page_text:
                        page_texts.append(f"--- [Trang {page_idx}] ---\n{cleaned_page_text}")

                    # 1. Bóc tách bảng biểu và lọc bỏ bảng rác
                    try:
                        extracted_tables = page.extract_tables()
                        for tbl in extracted_tables:
                            if not self._is_valid_table(tbl):
                                continue
                            md_table = self._format_markdown_table(tbl)
                            if md_table:
                                non_empty_rows = [r for r in tbl if any(c and str(c).strip() for c in r)]
                                tables.append(
                                    TableItem(
                                        table_id=f"{doc_id}_t{table_counter}",
                                        page=page_idx,
                                        caption=f"Bảng {table_counter}: Trang {page_idx}",
                                        total_rows=len(non_empty_rows),
                                        total_cols=len(tbl[0]) if tbl else 0,
                                        markdown=md_table,
                                    )
                                )
                                table_counter += 1
                    except Exception:
                        pass

                    # 2. Bóc tách ảnh máy móc / sơ đồ
                    if settings.EXTRACT_IMAGES and hasattr(page, "images"):
                        try:
                            page_words = page.extract_words() if hasattr(page, "extract_words") else []
                        except Exception:
                            page_words = []

                        try:
                            for img_info in page.images:
                                stream = img_info.get("stream")
                                if not stream:
                                    continue

                                # Lấy dữ liệu ảnh bằng get_data()
                                try:
                                    raw_data = stream.get_data()
                                except Exception:
                                    continue

                                try:
                                    im = Image.open(io.BytesIO(raw_data))
                                    width, height = im.size
                                    # Bỏ qua icon hoặc đường kẻ quá nhỏ
                                    if width < 50 or height < 50:
                                        continue

                                    img_filename = f"{doc_id}_img{img_counter}.png"
                                    # Chuyển mode không hỗ trợ sang RGB trước khi lưu PNG
                                    if im.mode in ("CMYK", "P"):
                                        im = im.convert("RGB")

                                    rel_path = storage.save_image(
                                        image_data=im,
                                        image_name=img_filename,
                                        subfolder=doc_id,
                                    )
                                except Exception:
                                    continue

                                context = cleaned_page_text[:250] if cleaned_page_text else ""
                                native_caption = self._find_native_caption(page_words, img_info) or (
                                    f"Hình {img_counter}: Trang {page_idx}"
                                )

                                images.append(
                                    ExtractedImage(
                                        image_id=f"{doc_id}_img{img_counter}",
                                        page=page_idx,
                                        image_name=img_filename,
                                        saved_path=str(rel_path).replace("\\", "/"),
                                        native_caption=native_caption,
                                        context_text=context,
                                        vlm_caption=None,
                                    )
                                )
                                img_counter += 1
                        except Exception:
                            pass
        except Exception as e:
            is_corrupted = True
            page_texts.append(f"[Error reading PDF: {e}]")
            total_pages = 0

        combined_text = "\n\n".join(page_texts).strip()
        detected_lang = detect_language(combined_text)

        return ProcessedDocument(
            doc_id=doc_id,
            metadata=DocMetadata(
                factory_code=factory_code,
                doc_type=doc_type,
                source_file=file_path.name,
                source_type=file_path.suffix.lstrip(".").lower(),
                language=detected_lang,
                access_level=access_level,
                engine_used=f"{self.name} (pdfplumber fallback)",
                total_pages=total_pages,
                file_size_kb=file_size_kb,
                is_corrupted=is_corrupted,
                hash_value=file_hash,
            ),
            cleaned_text=combined_text,
            tables=tables,
            images=images,
        )


    @staticmethod
    def _format_markdown_table(rows: List[List[Optional[str]]]) -> str:
        if not rows:
            return ""
        cleaned_rows: List[List[str]] = []
        for row in rows:
            cleaned_rows.append([clean_text(str(c)) if c is not None else "" for c in row])

        if not cleaned_rows:
            return ""

        headers = cleaned_rows[0]
        if not any(headers):
            headers = [f"Col {i+1}" for i in range(len(headers))]

        col_count = len(headers)
        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * col_count) + " |",
        ]

        for row in cleaned_rows[1:]:
            padded_row = row + [""] * (col_count - len(row))
            lines.append("| " + " | ".join(padded_row[:col_count]) + " |")

        return "\n".join(lines)

    @staticmethod
    def _find_native_caption(words: List[dict], img_info: dict, max_gap: float = 80.0) -> str:
        """Tìm dòng caption (Hình/Figure/Bảng...) nằm ngay dưới ảnh dựa vào toạ độ từ.

        Trả về chuỗi rỗng nếu ảnh không có caption thật trong tài liệu.
        """
        try:
            image_bottom = float(img_info.get("bottom") or 0)
            if not words or image_bottom <= 0:
                return ""

            # Các từ nằm trong khoảng max_gap điểm ngay dưới ảnh
            below = [
                w
                for w in words
                if image_bottom <= float(w.get("top", 0)) <= image_bottom + max_gap
            ]
            if not below:
                return ""

            # Gom các từ thuộc dòng đầu tiên bên dưới ảnh
            first_top = min(float(w.get("top", 0)) for w in below)
            line_words = [
                w for w in below if abs(float(w.get("top", 0)) - first_top) <= 3.0
            ]
            line_words.sort(key=lambda w: float(w.get("x0", 0)))
            line = " ".join(str(w.get("text", "")).strip() for w in line_words).strip()

            return line if CAPTION_PATTERN.match(line) else ""
        except Exception:
            return ""

    @staticmethod
    def _is_valid_table(rows: Optional[List[List[Optional[str]]]]) -> bool:
        """Kiểm tra xem bảng có chứa dữ liệu thực sự hay chỉ là đường kẻ trang trí/khung viền."""
        if not rows or len(rows) < 1:
            return False

        non_empty_cells = 0
        total_text_len = 0
        max_cols = 0
        for row in rows:
            if not row:
                continue
            max_cols = max(max_cols, len(row))
            for cell in row:
                if cell is not None:
                    txt = str(cell).strip()
                    if txt:
                        total_text_len += len(txt)
                        non_empty_cells += 1

        # Nếu không có chữ hoặc tổng chữ quá ít (< 10 ký tự)
        if non_empty_cells == 0 or total_text_len < 10:
            return False

        # Bảng chỉ có 1 cột: thực chất là khung cảnh báo/khung viền, không phải bảng dữ liệu
        if max_cols < 2:
            return False

        # Khung viền 1 ô (1x1) hoặc 1 hàng có ít hơn 2 ô có nội dung
        if len(rows) == 1 and non_empty_cells < 2:
            return False

        return True

