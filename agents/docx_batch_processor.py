"""
Gap Step 32: Batch Processing + Logging Layer
Processes all .docx files from an input folder in batch.
Logs each file as successful, failed, or partially processed.
Includes retry logic for OpenAI API failures.
Generates a final summary report after batch completion.
Wired to FastAPI via /docx endpoints.
"""

import os
import time
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from agents.docx_extractor import extract_docx
from agents.docx_normalizer import normalize_document, REVIEW_THRESHOLD
from agents.docx_builder import rebuild_document
from core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

INPUT_DIR = Path("docx_input")
OUTPUT_DIR = Path("docx_output")
REPORT_DIR = Path("docx_output")
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5


# ---------------------------------------------------------------------------
# Enums and models
# ---------------------------------------------------------------------------

class FileStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class FileResult(BaseModel):
    model_config = {"validate_assignment": True}

    file_name: str
    status: FileStatus
    output_path: Optional[str] = None
    overall_confidence: Optional[float] = None
    requires_human_review: bool = False
    error: Optional[str] = None
    attempts: int = 1
    processing_time_seconds: float = 0.0


class BatchReport(BaseModel):
    model_config = {"validate_assignment": True}

    batch_id: str
    started_at: str
    completed_at: str
    total_files: int
    successful: int
    failed: int
    partial: int
    requires_review: int
    results: list[FileResult]
    report_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Core batch processor
# ---------------------------------------------------------------------------

def run_batch(input_dir: str = None, output_dir: str = None) -> BatchReport:
    """
    Process all .docx files in input_dir through the full pipeline:
    extract -> normalize -> rebuild.

    Args:
        input_dir: Folder containing .docx files. Defaults to docx_input/.
        output_dir: Folder for standardized outputs. Defaults to docx_output/.

    Returns:
        BatchReport with per-file results and summary stats.
    """
    input_path = Path(input_dir) if input_dir else INPUT_DIR
    output_path = Path(output_dir) if output_dir else OUTPUT_DIR

    input_path.mkdir(parents=True, exist_ok=True)
    output_path.mkdir(parents=True, exist_ok=True)

    batch_id = str(uuid.uuid4())[:8]
    started_at = datetime.utcnow().isoformat() + "Z"

    docx_files = sorted(input_path.glob("*.docx"))

    logger.info("batch_started", batch_id=batch_id, total_files=len(docx_files))

    results: list[FileResult] = []

    for docx_file in docx_files:
        result = _process_single_file(docx_file, output_path)
        results.append(result)
        logger.info(
            "file_processed",
            batch_id=batch_id,
            file=result.file_name,
            status=result.status,
            confidence=result.overall_confidence,
            attempts=result.attempts,
        )

    completed_at = datetime.utcnow().isoformat() + "Z"

    report = BatchReport(
        batch_id=batch_id,
        started_at=started_at,
        completed_at=completed_at,
        total_files=len(results),
        successful=sum(1 for r in results if r.status == FileStatus.SUCCESS),
        failed=sum(1 for r in results if r.status == FileStatus.FAILED),
        partial=sum(1 for r in results if r.status == FileStatus.PARTIAL),
        requires_review=sum(1 for r in results if r.requires_human_review),
        results=results,
    )

    report_path = _save_report(report, output_path)
    report.report_path = report_path

    logger.info(
        "batch_complete",
        batch_id=batch_id,
        successful=report.successful,
        failed=report.failed,
        partial=report.partial,
        requires_review=report.requires_review,
    )

    return report


# ---------------------------------------------------------------------------
# Single file processor with retry
# ---------------------------------------------------------------------------

def _process_single_file(docx_file: Path, output_dir: Path) -> FileResult:
    """Run one file through the full pipeline with retry on OpenAI failures."""
    start = time.time()
    attempts = 0
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        attempts = attempt
        try:
            # Step 1: Extract
            extracted = extract_docx(str(docx_file))

            # Step 2: Normalize via OpenAI
            normalized = normalize_document(extracted)

            # Step 3: Rebuild
            out_path = str(output_dir / f"{docx_file.stem}_standardized.docx")
            rebuild_document(normalized, output_path=out_path)

            elapsed = round(time.time() - start, 2)

            # Partial = succeeded but low confidence
            status = (
                FileStatus.PARTIAL
                if normalized.requires_human_review
                else FileStatus.SUCCESS
            )

            return FileResult(
                file_name=docx_file.name,
                status=status,
                output_path=out_path,
                overall_confidence=normalized.overall_confidence,
                requires_human_review=normalized.requires_human_review,
                attempts=attempts,
                processing_time_seconds=elapsed,
            )

        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES:
                logger.warning(
                    "file_retry",
                    file=docx_file.name,
                    attempt=attempt,
                    error=last_error,
                )
                time.sleep(RETRY_DELAY_SECONDS)
            continue

    elapsed = round(time.time() - start, 2)
    return FileResult(
        file_name=docx_file.name,
        status=FileStatus.FAILED,
        error=last_error,
        attempts=attempts,
        processing_time_seconds=elapsed,
    )


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _save_report(report: BatchReport, output_dir: Path) -> str:
    """Save batch report as JSON to the output folder."""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"batch_report_{report.batch_id}_{timestamp}.json"

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2)

    return str(report_path)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    report = run_batch()
    print(json.dumps(report.model_dump(), indent=2))
