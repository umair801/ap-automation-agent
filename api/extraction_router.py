# api/extraction_router.py

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agents.page_classifier import run_page_classifier
from agents.extraction_agent import extract_all_schedule_pages
from exports.excel_exporter import export_to_excel, ExportConfig
from core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/extract", tags=["Schedule Extraction"])

# Temporary storage for generated Excel files keyed by job_id.
# In production this would be Supabase Storage or S3.
_job_store: dict[str, str] = {}

UPLOAD_DIR = Path("tmp_uploads")
EXPORT_DIR = Path("tmp_exports")
UPLOAD_DIR.mkdir(exist_ok=True)
EXPORT_DIR.mkdir(exist_ok=True)


class ExtractionResponse(BaseModel):
    job_id: str
    total_pages: int
    schedule_pages: int
    total_items: int
    pages_skipped: int
    message: str


@router.post("/upload", response_model=ExtractionResponse)
async def upload_and_extract(file: UploadFile = File(...)):
    """
    Accept a PDF upload, classify pages, extract schedule data,
    and export to Excel. Returns a job_id for the download endpoint.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Save uploaded file
    job_id = str(uuid.uuid4())
    pdf_path = UPLOAD_DIR / f"{job_id}.pdf"
    pdf_bytes = await file.read()

    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    logger.info("PDF received", job_id=job_id, filename=file.filename, size=len(pdf_bytes))

    # Step 1: Classify pages
    classification = run_page_classifier(pdf_bytes)

    if not classification.success:
        raise HTTPException(status_code=422, detail=f"Page classification failed: {classification.error}")

    if not classification.has_schedules:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No schedule pages detected in this PDF. "
                f"Total pages scanned: {classification.total_pages}. "
                f"Ensure the PDF contains a window or door schedule table."
            ),
        )

    logger.info(
        "Classification complete",
        job_id=job_id,
        total_pages=classification.total_pages,
        schedule_pages=classification.schedule_pages,
    )

    # Step 2: Extract schedule data from identified pages
    results = extract_all_schedule_pages(pdf_bytes, classification.schedule_pages)

    # Step 3: Export to Excel
    export_path = EXPORT_DIR / f"{job_id}_schedule.xlsx"
    config = ExportConfig(output_path=str(export_path))
    export_result = export_to_excel(results, config)

    if not export_result.success:
        raise HTTPException(status_code=500, detail=f"Excel export failed: {export_result.error}")

    # Store job for download
    _job_store[job_id] = str(export_path)

    logger.info(
        "Extraction job complete",
        job_id=job_id,
        total_items=export_result.total_rows,
        pages_included=export_result.pages_included,
    )

    return ExtractionResponse(
        job_id=job_id,
        total_pages=classification.total_pages,
        schedule_pages=len(classification.schedule_pages),
        total_items=export_result.total_rows,
        pages_skipped=export_result.pages_skipped,
        message="Extraction complete. Use the job_id to download the Excel file.",
    )


@router.get("/download/{job_id}")
async def download_excel(job_id: str):
    """Download the generated Excel file for a completed extraction job."""
    if job_id not in _job_store:
        raise HTTPException(status_code=404, detail="Job not found or already expired.")

    file_path = Path(_job_store[job_id])

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Export file not found.")

    return FileResponse(
        path=str(file_path),
        filename="schedule_takeoff.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )