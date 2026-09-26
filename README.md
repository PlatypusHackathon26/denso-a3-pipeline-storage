# DENSO A3 Data Ingestion Pipeline for RAG

Hệ thống bóc tách, làm sạch và chuẩn hóa tài liệu thô đa định dạng (PDF, DOCX, XLSX, TXT, Code...) thành dữ liệu văn bản sạch & có cấu trúc (Clean Data) phục vụ nhúng (embedding) và truy vấn tri thức kỹ thuật (Multimodal RAG) cho nhà máy DENSO.

---

## 1. Bản đồ cấu trúc thư mục

```text
denso-a3-pipeline-storage/
│
├── configs/
│   ├── __init__.py
│   └── settings.py          # Bảng điều khiển: Đường dẫn data, GPU/CPU, cấu hình media và định dạng hỗ trợ
│
├── schemas/
│   ├── __init__.py
│   └── document.py          # Bản hợp đồng dữ liệu Pydantic: ProcessedDocument, TableItem, ExtractedImage, DocMetadata
│
├── engines/                 # Khu vực của các thợ bóc tách
│   ├── __init__.py
│   ├── base.py              # Interface luật chung: BaseEngine abstract class bắt buộc hàm parse() trả về ProcessedDocument
│   ├── docling_engine.py    # Thợ PDF: Hỗ trợ Docling, tự động fallback pdfplumber trích xuất Markdown table và media image
│   └── xberg_engine.py      # Thợ siêu tốc: Xử lý Word (.docx), Excel (.xlsx, .csv), Markdown, Code, txt
│
├── core/                    # Khu vực xử lý nghiệp vụ của hệ thống
│   ├── __init__.py
│   ├── hasher.py            # Chốt bảo vệ: Băm SHA256/MD5, sinh DocID chuẩn, chống trùng lặp dữ liệu (deduplicate)
│   ├── router.py            # Cảnh sát giao thông: Đọc đuôi file và điều phối tới Engine phù hợp
│   └── storage.py           # Thủ kho: Quản lý đọc/ghi raw ở 01_raw/, ảnh ở 02_media/, JSON ở 03_processed/
│
├── utils/                   # Tiện ích bổ trợ dùng chung
│   ├── __init__.py
│   ├── lang_detector.py     # Nhận diện ngôn ngữ tự động (vi, en, ja...)
│   ├── text_cleaner.py      # Chuẩn hóa Unicode NFC, xử lý ngắt dòng, khoảng trắng, ký tự rác
│   └── text_helpers.py      # Các hàm trợ giúp xử lý văn bản
│
├── data/                    # Nơi lưu trữ dữ liệu thực tế
│   ├── 01_raw/              # File gốc đưa vào bóc tách
│   ├── 02_media/            # Ảnh trích xuất từ tài liệu (máy móc, sơ đồ, lỗi HMI...)
│   └── 03_processed/        # File JSON sạch hoàn thiện chuẩn RAG
│
├── tests/
│   └── test_pipeline.py     # Bộ kiểm thử tự động (Unit tests) đảm bảo hệ thống hoạt động chính xác
│
├── pipeline.py              # Nhạc trưởng: File CLI duy nhất chạy toàn bộ quy trình
├── output_format.json       # Bản hợp đồng mẫu JSON đầu ra
├── requirements.txt         # Khai báo các thư viện phụ thuộc
└── README.md                # Tài liệu hướng dẫn sử dụng và kiến trúc
```

---

## 2. Bản hợp đồng dữ liệu đầu ra (`output_format.json`)

Mọi file sau khi xử lý đều được lưu vào `data/03_processed/<ten_file>.json` với schema sau:

```json
{
  "doc_id": "DENSO_A1B2C3D4",
  "metadata": {
    "factory_code": "DENSO_HN",
    "doc_type": "maintenance_manual",
    "source_file": "sop_bao_tri_may_dap_a12.pdf",
    "source_type": "pdf",
    "language": "vi",
    "access_level": 1,
    "created_at": "2026-09-23T09:48:28Z",
    "engine_used": "docling",
    "total_pages": 3,
    "file_size_kb": 245.5,
    "is_corrupted": false,
    "hash_value": "72c06d24b80a897713139f33369ad07b538b604a361c72e7811fe7880a14b729",
    "extra": {}
  },
  "cleaned_text": "--- [Trang 1] ---\nHƯỚNG DẪN KIỂM TRA VÀ XỬ LÝ SỰ CỐ MÁY DẬP STAMP-A12...",
  "tables": [
    {
      "table_id": "DENSO_A1B2C3D4_t1",
      "page": 2,
      "caption": "Bảng 1: Thông số áp suất và nhiệt độ an toàn máy dập A12",
      "total_rows": 4,
      "total_cols": 3,
      "markdown": "| Thông số | Ngưỡng an toàn | Ngưỡng nguy hiểm |\n|---|---|---|\n| Áp suất dầu cấp (P-102) | 0.40 - 0.60 MPa | < 0.35 MPa |"
    }
  ],
  "images": [
    {
      "image_id": "DENSO_A1B2C3D4_img1",
      "page": 1,
      "image_name": "DENSO_A1B2C3D4_img1.png",
      "saved_path": "data/02_media/DENSO_A1B2C3D4/DENSO_A1B2C3D4_img1.png",
      "native_caption": "Hình 1: Màn hình HMI báo lỗi ERR-305",
      "context_text": "Màn hình HMI hiển thị mã lỗi ERR-305. Đồng hồ đo áp suất dầu bôi trơn...",
      "vlm_caption": null
    }
  ]
}
```

> **Ghi chú 3 field dễ hiểu sai:**
> - **`saved_path`**: đường dẫn tương đối **tính từ gốc dự án** và **có kèm thư mục `<doc_id>`** → `data/02_media/<doc_id>/<image_name>`. Do `core/storage.py::save_image` trả về `target_file.relative_to(settings.BASE_DIR)` và engine truyền `subfolder=doc_id` khi lưu.
> - **`engine_used`**: máy có cài thư viện `docling` → `"docling"`; máy **chưa cài** `docling` (như môi trường hiện tại) → `"docling (pdfplumber fallback)"`.
> - **`hash_value`**: SHA256 của file nguồn, là cơ sở chống trùng lặp (`core/hasher.py`) — dedup đọc lại field này từ `data/03_processed/*.json`.

### Xử lý ảnh máy móc không có chữ (Mechanical & Hardware Images):
- **Ngữ cảnh lân cận (`context_text`):** Tự động bóc tách 250 ký tự văn bản xung quanh vị trí ảnh xuất hiện trong tài liệu. Khi kỹ thuật viên tìm kiếm *"đồng hồ P-102"*, Vector DB sẽ match đoạn context này để trả về ảnh chính xác.
- **Chú thích gốc (`native_caption`):** Với PDF, engine đọc toạ độ từ (`pdfplumber` words) để tìm dòng caption nằm ngay dưới ảnh (tối đa 80pt) và so khớp regex `Hình/Figure/Ảnh/Bảng/Table/Sơ đồ/Chart`. Nếu tài liệu không có caption thật (ảnh sơ đồ thuần túy), hệ thống tự sinh nhãn `Hình {n}: Trang {p}`.
- **Sẵn sàng cho AI thị giác (`vlm_caption`):** Đặt sẵn trường `null`, hỗ trợ cắm các mô hình Vision-Language (Gemini Flash, GPT-4o-mini, Florence-2) mô tả chi tiết thiết bị cơ khí mà không làm vỡ schema.

### Bộ lọc nhiễu (Noise Filtering) — chống ảo giác dữ liệu:
- **Ảnh:** Chỉ lưu ảnh mở được bằng PIL (bỏ qua color profile/mảnh vỡ stream) và có kích thước tối thiểu **50x50 px** — loại bỏ icon, logo, đường kẻ trang trí. Ảnh được ghi lại qua PIL (`image.save()`) để đảm bảo file PNG hợp lệ.
- **Bảng:** `pdfplumber` nhận diện cả đường kẻ layout thành "bảng", nên mỗi bảng phải qua hàm `_is_valid_table()` trước khi lưu:
  - Loại bảng có **0 ô có nội dung** (lưới layout rỗng).
  - Loại bảng có tổng nội dung **< 10 ký tự** (khung viền rỗng).
  - Loại bảng **chỉ 1 cột** — thực chất là khung cảnh báo (`PRECAUTIONS!`, `DISCLAIMER`).
  - Loại khung **1 ô (1x1)** và hàng đơn có ít hơn 2 ô có nội dung.
  - Văn bản trong các khung cảnh báo vẫn được giữ nguyên trong `cleaned_text`, không mất dữ liệu.



---

## 3. Luồng hoạt động (Workflow)

```text
               [Người dùng chạy: python pipeline.py]
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │ configs/settings.py   │  (Khởi tạo cấu hình & đường dẫn)
                     └───────────┬───────────┘
                                 │
                                 ▼
                         [Quét File Đầu Vào]
                     (data/01_raw hoặc đối số CLI)
                                 │
                                 ▼
                     ┌───────────────────────┐
                     │   core/hasher.py      │  (Băm SHA256 file nguồn)
                     └───────────┬───────────┘
                                 │
                 ┌───────────────┴───────────────┐
        [Hash đã có trong 03_processed?]         │
        (dùng --force để bỏ qua bước này)        │
               YES │                             │ NO
                   ▼                             ▼
                [BỎ QUA]             ┌───────────────────────┐
                                     │   core/router.py      │  (Đọc đuôi file)
                                     └───────────┬───────────┘
                                                 │
                      ┌──────────────────────────┴──────────────────────────┐
                      ▼                                                     ▼
           [Nếu là .pdf]                                        [Nếu là .docx, .xlsx, .txt...]
       ┌────────────────────────┐                             ┌────────────────────────┐
       │ engines/docling_engine │                             │  engines/xberg_engine  │
       └──────────┬─────────────┘                             └──────────┬─────────────┘
                  │                                                      │
                  └──────────────────────────┬───────────────────────────┘
                                             │
                                             ▼
                             [utils/text_cleaner & lang_detector]
                                             │
                                             ▼
                               ┌──────────────────────────┐
                               │  schemas/document.py     │  (Đóng gói ProcessedDocument)
                               └─────────────┬────────────┘
                                             │
                                             ▼
                               ┌──────────────────────────┐
                               │    core/storage.py       │  (Lưu trữ kết quả)
                               └─────────────┬────────────┘
                                             │
                      ┌──────────────────────┴──────────────────────┐
                      ▼                                             ▼
        [Lưu ảnh trích xuất]                           [Lưu file clean JSON]
          data/02_media/                                 data/03_processed/
```

---

## 4. Hướng dẫn sử dụng

### Cài đặt thư viện
```powershell
pip install -r requirements.txt
```

### Chạy kiểm thử tự động (Unit Tests)
```powershell
python -m pytest -v tests/
```

### Chạy Ingestion Pipeline

1. **Chạy toàn bộ tài liệu trong `data/01_raw/`:**
   ```powershell
   python pipeline.py
   ```

2. **Chạy chỉ định file hoặc thư mục cụ thể kèm phân quyền bảo mật (`--level`):**
   ```powershell
   python pipeline.py "duong_dan/tai_lieu.pdf" --level 2
   ```

3. **Bắt buộc xử lý lại (bỏ qua cơ chế lọc trùng lặp hash):**
   ```powershell
   python pipeline.py --force
   ```

### Kiểm thử lại & dọn kết quả

| Tình huống | Lệnh | Ghi chú |
|---|---|---|
| Sửa code engine rồi chạy lại | `python pipeline.py --force` | Ghi đè JSON cũ cùng tên, **không cần xóa gì** |
| Muốn kiểm tra đúng **số lượng ảnh** | `Remove-Item -Recurse -Force data\02_media\<doc_id>` rồi `python pipeline.py --force` | Ảnh cũ **không** tự bị dọn: nếu lần chạy mới ra ít ảnh hơn sẽ còn file rác `..._img{n}.png` |
| Đổi nội dung file nguồn | Xóa `<ten_file>.json` cũ + thư mục media cũ của `doc_id` cũ | Hash mới → `doc_id` mới, JSON cũ thành rác |
| Dọn sạch toàn bộ kết quả | `Remove-Item data\03_processed\*.json -Force` và `Get-ChildItem data\02_media -Directory \| Remove-Item -Recurse -Force` | Giữ lại `.gitkeep`; cả 2 thư mục đã được `.gitignore` |

Giải thích cơ chế: `core/hasher.py` nạp lại `metadata.hash_value` từ **tất cả** file trong `data/03_processed/` khi khởi động, nên chỉ cần JSON cũ còn tồn tại là pipeline sẽ in `[SKIP] Already processed` — trừ khi bạn truyền `--force` (`pipeline.py`).

> ⚠️ **Không bao giờ xóa `data/01_raw/`** — đó là file nguồn duy nhất của pipeline.

