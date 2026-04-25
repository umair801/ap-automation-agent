"""
Gap Step 30: OpenAI Normalization Agent
Sends extracted .docx content to OpenAI and normalizes it against
a master document structure. Returns validated JSON with confidence
scores. Routes low-confidence documents to a human review queue.
"""

import json
import os
from typing import Optional
from openai import OpenAI
from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# Master structure — canonical section order for all standardized documents
# ---------------------------------------------------------------------------
MASTER_SECTIONS = [
    "Title",
    "Document Control",
    "Purpose",
    "Scope",
    "Definitions",
    "Responsibilities",
    "Procedure",
    "Records",
    "References",
    "Revision History",
]

# Confidence threshold below which a document is flagged for human review
REVIEW_THRESHOLD = 0.70


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class NormalizedSection(BaseModel):
    model_config = {"validate_assignment": True}

    section_name: str          # One of MASTER_SECTIONS
    content: str               # Normalized plain-text content for the section
    confidence: float          # 0.0 – 1.0: how well the source mapped to this section
    source_heading: str        # Original heading from the document (or "" if inferred)
    present_in_source: bool    # True if section existed; False if inferred/empty


class NormalizedDocument(BaseModel):
    model_config = {"validate_assignment": True}

    file_name: str
    overall_confidence: float
    requires_human_review: bool
    review_reason: Optional[str]
    sections: list[NormalizedSection]

    @field_validator("overall_confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return round(max(0.0, min(1.0, v)), 4)


# ---------------------------------------------------------------------------
# Normalization agent
# ---------------------------------------------------------------------------

def normalize_document(extracted: dict) -> NormalizedDocument:
    """
    Normalize a docx_extractor output dict against the master section structure.

    Args:
        extracted: Dict returned by docx_extractor.extract_docx()

    Returns:
        NormalizedDocument with per-section confidence scores.
    """
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    prompt = _build_prompt(extracted)

    response = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": prompt},
        ],
    )

    raw_json = response.choices[0].message.content
    parsed = _parse_and_validate(raw_json, extracted["file_name"])
    return parsed


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _system_prompt() -> str:
    return (
        "You are a document standardization engine. "
        "Your job is to map the content of a business document to a master section structure "
        "and return strictly valid JSON. "
        "Do not invent content. If a section is missing from the source, mark it as absent "
        "and leave its content empty. "
        "Never include markdown, code fences, or commentary — return JSON only."
    )


def _build_prompt(extracted: dict) -> str:
    master_list = json.dumps(MASTER_SECTIONS, indent=2)

    # Condense sections for the prompt
    sections_summary = []
    for sec in extracted.get("sections", []):
        sections_summary.append({
            "heading": sec["heading"],
            "heading_level": sec["heading_level"],
            "content_preview": " ".join(sec["content"])[:500],
        })

    tables_summary = []
    for t in extracted.get("tables", []):
        tables_summary.append({
            "table_index": t["table_index"],
            "rows": t["rows"][:5],  # first 5 rows only to stay within token budget
        })

    payload = {
        "file_name": extracted["file_name"],
        "metadata": extracted["metadata"],
        "sections": sections_summary,
        "tables": tables_summary,
    }

    return f"""
You must map the following document to the master section structure below.

MASTER SECTIONS (in order):
{master_list}

DOCUMENT CONTENT:
{json.dumps(payload, indent=2, default=str)}

Return a JSON object with this exact schema:
{{
  "overall_confidence": <float 0.0-1.0>,
  "sections": [
    {{
      "section_name": "<one of the master section names>",
      "content": "<normalized plain-text content>",
      "confidence": <float 0.0-1.0>,
      "source_heading": "<original heading or empty string>",
      "present_in_source": <true|false>
    }}
  ]
}}

Rules:
- Every master section must appear exactly once in your output, in order.
- confidence = 1.0 means a clear, direct match. 0.0 means the section is entirely absent.
- overall_confidence = average of all section confidence scores.
- Do not add sections beyond the master list.
- Content must be plain text only — no markdown, no bullet symbols.
"""


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_and_validate(raw_json: str, file_name: str) -> NormalizedDocument:
    """Parse OpenAI JSON response and build a NormalizedDocument."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"OpenAI returned invalid JSON: {e}\nRaw: {raw_json[:300]}")

    sections = []
    for item in data.get("sections", []):
        sections.append(NormalizedSection(
            section_name=item["section_name"],
            content=item.get("content", ""),
            confidence=float(item.get("confidence", 0.0)),
            source_heading=item.get("source_heading", ""),
            present_in_source=bool(item.get("present_in_source", False)),
        ))

    overall = float(data.get("overall_confidence", 0.0))
    requires_review = overall < REVIEW_THRESHOLD
    review_reason = None

    if requires_review:
        low_sections = [s.section_name for s in sections if s.confidence < REVIEW_THRESHOLD]
        review_reason = (
            f"Overall confidence {overall:.2f} below threshold {REVIEW_THRESHOLD}. "
            f"Low-confidence sections: {', '.join(low_sections) if low_sections else 'none listed'}."
        )

    return NormalizedDocument(
        file_name=file_name,
        overall_confidence=overall,
        requires_human_review=requires_review,
        review_reason=review_reason,
        sections=sections,
    )


# ---------------------------------------------------------------------------
# CLI test entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from agents.docx_extractor import extract_docx

    if len(sys.argv) < 2:
        print("Usage: python docx_normalizer.py <path_to_docx>")
        sys.exit(1)

    extracted = extract_docx(sys.argv[1])
    result = normalize_document(extracted)
    print(json.dumps(result.model_dump(), indent=2))
