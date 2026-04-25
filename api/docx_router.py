# api/docx_router.py

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from agents.docx_batch_processor import run_batch, BatchReport, FileStatus
from core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/docx", tags=["DOCX Standardization"])

UPLOAD_DIR = Path("docx_input")
OUTPUT_DIR = Path("docx_output")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


@router.post("/batch", response_model=BatchReport)
async def batch_standardize():
    """
    Process all .docx files currently in the docx_input/ folder.
    Runs the full pipeline: extract -> normalize -> rebuild.
    Returns a batch report with per-file status and summary stats.
    """
    logger.info("docx_batch_endpoint_called")

    files = list(UPLOAD_DIR.glob("*.docx"))
    if not files:
        raise HTTPException(
            status_code=422,
            detail="No .docx files found in the input folder. Upload files first via POST /docx/upload.",
        )

    report = run_batch(input_dir=str(UPLOAD_DIR), output_dir=str(OUTPUT_DIR))
    return report


@router.post("/upload")
async def upload_docx(file: UploadFile = File(...)):
    """
    Upload a single .docx file to the input queue.
    Call POST /docx/batch to process all queued files.
    """
    if not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files are accepted.")

    dest = UPLOAD_DIR / file.filename
    content = await file.read()

    with open(dest, "wb") as f:
        f.write(content)

    logger.info("docx_uploaded", filename=file.filename, size=len(content))

    return {
        "message": f"File '{file.filename}' uploaded successfully.",
        "queued_files": len(list(UPLOAD_DIR.glob("*.docx"))),
        "next_step": "POST /docx/batch to process all queued files.",
    }


@router.get("/download/{file_name}")
async def download_standardized(file_name: str):
    """
    Download a standardized .docx file from the output folder.
    Use the output file name returned in the batch report.
    """
    file_path = OUTPUT_DIR / file_name

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{file_name}' not found in output folder.")

    return FileResponse(
        path=str(file_path),
        filename=file_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.delete("/clear-input")
async def clear_input_queue():
    """Remove all .docx files from the input queue."""
    files = list(UPLOAD_DIR.glob("*.docx"))
    for f in files:
        f.unlink()
    return {"message": f"Cleared {len(files)} file(s) from the input queue."}
