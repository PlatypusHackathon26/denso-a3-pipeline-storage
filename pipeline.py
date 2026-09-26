"""Main ingestion pipeline runner.

Orchestrates: Hasher (deduplication) -> Router -> Engine -> Storage (JSON & Media)
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from configs.settings import settings
from core.hasher import hasher
from core.router import router
from core.storage import storage
from schemas.document import ProcessedDocument


def process_file(
    file_path: Path,
    access_level: int = 1,
    force: bool = False,
) -> Optional[ProcessedDocument]:
    """Process a single file through the ingestion pipeline.

    Args:
        file_path: Path to the input file.
        access_level: Security level (1, 2, or 3).
        force: If True, bypass deduplication check and reprocess.

    Returns:
        ProcessedDocument if successful, None otherwise.
    """
    if not file_path.exists() or not file_path.is_file():
        print(f"[WARN] File does not exist: {file_path}")
        return None

    # 1. Compute Hash
    file_hash = hasher.compute_hash(file_path)

    # 2. Duplicate Detection
    if not force and settings.DEDUPLICATE and hasher.is_processed(file_hash):
        print(f"[SKIP] Already processed (Hash: {file_hash[:8]}...): {file_path.name}")
        return None

    # 3. Router selection
    engine = router.get_engine(file_path)
    if not engine:
        print(f"[SKIP] No engine available for file type '{file_path.suffix}': {file_path.name}")
        return None

    # 4. Copy raw file to 01_raw (if not already there)
    storage.save_raw(file_path)

    # 5. Execute parsing
    doc_id = hasher.generate_doc_id(file_path, file_hash)
    print(f"[PROCESS] Engine '{engine.name}' -> {file_path.name} (DocID: {doc_id})")

    try:
        doc = engine.parse(
            file_path=file_path,
            access_level=access_level,
            doc_id=doc_id,
            file_hash=file_hash,
        )

        # 6. Save processed document to 03_processed
        saved_path = storage.save_document(doc)
        hasher.register_hash(file_hash)
        print(f"[SUCCESS] Saved clean document to: {saved_path}")
        return doc

    except Exception as e:
        print(f"[ERROR] Failed to process {file_path.name}: {e}")
        return None


def run_pipeline(
    input_paths: Optional[List[Path]] = None,
    access_level: int = 1,
    force: bool = False,
) -> List[ProcessedDocument]:
    """Run pipeline across multiple files or scan default 01_raw directory."""
    settings.ensure_dirs()
    targets: List[Path] = []

    if input_paths:
        for p in input_paths:
            path_obj = Path(p)
            if path_obj.is_dir():
                targets.extend([f for f in path_obj.rglob("*") if f.is_file()])
            elif path_obj.is_file():
                targets.append(path_obj)
    else:
        # Scan data/01_raw
        targets = [f for f in settings.RAW_DIR.rglob("*") if f.is_file()]

    print(f"=== Starting Ingestion Pipeline ({len(targets)} candidate files) ===")

    processed_docs: List[ProcessedDocument] = []
    for file_path in targets:
        doc = process_file(file_path, access_level=access_level, force=force)
        if doc:
            processed_docs.append(doc)

    print(f"=== Completed: {len(processed_docs)}/{len(targets)} files processed successfully ===")
    return processed_docs


def main() -> None:
    parser = argparse.ArgumentParser(description="Denso RAG Ingestion Pipeline")
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="Path(s) to input files or directories to process. Defaults to data/01_raw/",
    )
    parser.add_argument(
        "--level",
        type=int,
        default=1,
        choices=[1, 2, 3],
        help="Access level for the documents (default: 1)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reprocessing even if file hash matches existing document",
    )

    args = parser.parse_args()
    run_pipeline(input_paths=args.inputs or None, access_level=args.level, force=args.force)


if __name__ == "__main__":
    main()
