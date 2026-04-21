# agents/page_classifier.py

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import anthropic
import fitz  # PyMuPDF

from core.config import get_settings
from core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Valid page type labels
PAGE_TYPES = {"schedule", "floor_plan", "elevation", "cover", "notes"}

CLASSIFICATION_PROMPT = """You are analyzing a single page from a technical construction or architectural PDF.

Classify this page into exactly one of the following categories:
- schedule: A table or grid listing windows, doors, or other building components with columns for type, size, quantity, location, finish, or similar fields.
- floor_plan: A top-down architectural drawing showing room layouts, walls, and spatial arrangements.
- elevation: A side-view architectural drawing showing the external or internal face of a building or wall.
- cover: A title page, cover sheet, project information page, or table of contents.
- notes: Specification text, written notes, legends, general conditions, or any page that is primarily written text without tabular data.

Rules:
- Return only the single word label. Nothing else.
- If the page could be multiple types, choose the most dominant one.
- If unsure, return notes."""


@dataclass
class PageClassification:
    """Result for a single page classification."""
    page_number: int          # 0-indexed
    page_type: str            # one of PAGE_TYPES
    confidence: str           # "high", "medium", "low" — set by heuristic
    error: Optional[str] = None

    @property
    def is_schedule(self) -> bool:
        return self.page_type == "schedule"


@dataclass
class ClassificationResult:
    """Full result for a multi-page PDF classification run."""
    total_pages: int
    classifications: list[PageClassification] = field(default_factory=list)
    schedule_pages: list[int] = field(default_factory=list)   # 0-indexed page numbers
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and len(self.classifications) > 0

    @property
    def has_schedules(self) -> bool:
        return len(self.schedule_pages) > 0


def _render_page_to_base64(doc: fitz.Document, page_num: int, dpi: int = 150) -> str:
    """
    Render a single PDF page to a base64-encoded PNG.
    150 DPI is sufficient for classification — keeps token usage low.
    """
    page = doc[page_num]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    return base64.standard_b64encode(img_bytes).decode("utf-8")


def _classify_page_with_claude(
    client: anthropic.Anthropic,
    image_b64: str,
    page_num: int,
) -> PageClassification:
    """
    Send a single page image to Claude and return its classification.
    """
    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=10,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": CLASSIFICATION_PROMPT,
                        },
                    ],
                }
            ],
        )

        raw = response.content[0].text.strip().lower()

        # Validate the response is a known page type
        page_type = raw if raw in PAGE_TYPES else "notes"

        logger.info(
            "Page classified",
            page=page_num,
            raw_response=raw,
            assigned_type=page_type,
        )

        return PageClassification(
            page_number=page_num,
            page_type=page_type,
            confidence="high" if raw in PAGE_TYPES else "low",
        )

    except Exception as e:
        logger.error("Claude classification failed", page=page_num, error=str(e))
        return PageClassification(
            page_number=page_num,
            page_type="notes",
            confidence="low",
            error=str(e),
        )


def run_page_classifier(source: str | bytes | Path) -> ClassificationResult:
    """
    Main entry point for the Page Classifier agent.

    Accepts a file path or raw PDF bytes.
    Classifies every page and returns a ClassificationResult.
    Schedule page numbers are available at result.schedule_pages.
    """
    # Normalise input to bytes
    if isinstance(source, (str, Path)):
        file_path = str(source)
        try:
            with open(file_path, "rb") as f:
                pdf_bytes = f.read()
        except FileNotFoundError as e:
            logger.error("PDF not found", path=file_path, error=str(e))
            return ClassificationResult(total_pages=0, error=f"File not found: {file_path}")
    else:
        pdf_bytes = source

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        logger.error("Failed to open PDF", error=str(e))
        return ClassificationResult(total_pages=0, error=f"Could not open PDF: {e}")

    total_pages = len(doc)
    logger.info("Starting page classification", total_pages=total_pages)

    anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    classifications: list[PageClassification] = []
    schedule_pages: list[int] = []

    for page_num in range(total_pages):
        image_b64 = _render_page_to_base64(doc, page_num)
        classification = _classify_page_with_claude(anthropic_client, image_b64, page_num)
        classifications.append(classification)
        if classification.is_schedule:
            schedule_pages.append(page_num)

    doc.close()

    logger.info(
        "Classification complete",
        total_pages=total_pages,
        schedule_pages=schedule_pages,
    )

    return ClassificationResult(
        total_pages=total_pages,
        classifications=classifications,
        schedule_pages=schedule_pages,
    )