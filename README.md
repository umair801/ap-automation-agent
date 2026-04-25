# AP-AI: Enterprise Accounts Payable Automation Agent

**Built by [Datawebify](https://datawebify.com) | Live Demo: [ap.datawebify.com/docx-ui](https://ap.datawebify.com/docx-ui)**

---

## What This System Does

AP-AI is a fully autonomous accounts payable agent that eliminates manual invoice processing. It ingests invoices from email, PDF upload, or EDI feeds, extracts all fields using GPT-4o vision, validates against business rules, runs three-way matching against purchase orders and goods receipts, routes for approval, schedules payments, and syncs every transaction to QuickBooks, Xero, SAP, or NetSuite — with zero manual data entry and a complete audit trail.

The system also includes a DOCX Document Standardization module that automatically normalizes unstructured Word documents to a master 10-section structure using OpenAI, rebuilds them with consistent professional formatting, and processes entire folders in batch with per-file confidence scoring and audit logging.

---

## Business Outcomes

| Metric | Manual AP Team | With AP-AI | Change |
|---|---|---|---|
| Invoice processing time | 5 to 15 days | Under 24 hours | 95% faster |
| Cost per invoice | $15 to $40 (labor) | Under $2 (compute) | 90%+ reduction |
| Three-way match accuracy | 70 to 80% (human error) | 98%+ (automated) | Full coverage |
| Exception rate | 20 to 30% | Under 5% | 6x reduction |
| On-time payment rate | 60 to 75% | 95%+ | Eliminate late fees |
| Audit trail completeness | Inconsistent, manual | 100% automated | Full coverage |
| Staff time on AP processing | 40 to 60 hrs/week | Near zero | 90%+ reduction |
| Document standardization time | 2 to 4 hrs per doc (manual) | Under 60 seconds | 99% faster |

---

## Live Demos

| Feature | Live URL |
|---|---|
| Document Standardizer UI | [ap.datawebify.com/docx-ui](https://ap.datawebify.com/docx-ui) |
| Order Extraction Demo | [ap.datawebify.com/orders/demo](https://ap.datawebify.com/orders/demo) |
| Schedule Extractor UI | [ap.datawebify.com/upload](https://ap.datawebify.com/upload) |
| Interactive API Docs | [ap.datawebify.com/docs](https://ap.datawebify.com/docs) |
| System Health | [ap.datawebify.com/metrics/health](https://ap.datawebify.com/metrics/health) |
| Real-time AP Metrics | [ap.datawebify.com/metrics](https://ap.datawebify.com/metrics) |

---

## Live Endpoints

### AP Automation

| Endpoint | Description |
|---|---|
| `GET /metrics/health` | System health check |
| `GET /metrics` | Real-time AP KPIs |
| `POST /ingest/pdf` | Upload invoice PDF |
| `POST /ingest/email-webhook` | Email webhook receiver |
| `POST /ingest/edi` | EDI 810 invoice upload |
| `GET /approval/decide` | One-click approve or reject |
| `GET /approval/status/{invoice_number}` | Approval status query |

### Schedule Extraction

| Endpoint | Description |
|---|---|
| `GET /upload` | Upload UI for architectural PDFs |
| `POST /extract/upload` | Upload PDF, extract schedule data |
| `GET /extract/download/{job_id}` | Download Excel takeoff file |

### DOCX Document Standardization

| Endpoint | Description |
|---|---|
| `GET /docx-ui` | Non-technical client UI |
| `POST /docx/upload` | Upload a .docx file to the queue |
| `POST /docx/batch` | Process all queued files |
| `GET /docx/download/{file_name}` | Download standardized .docx |
| `DELETE /docx/clear-input` | Clear the input queue |

---

## System Architecture

### AP Automation Pipeline

```
Invoice Received (Email / Upload / EDI)
           |
   Ingestion Agent
           |
   Extraction Agent (GPT-4o Vision)
           |
   Validation Agent
           |
   Three-Way Match Agent
           |
      Match          No Match
        |                |
  Approval Router   Exception Handler
        |                |
  Auto-approve or   Human Review Queue
  Route to Approver  + Vendor Communication
        |
  Payment Scheduler
        |
  ERP Sync Agent (QuickBooks / Xero / SAP / NetSuite)
        |
  Audit Logger + Notification Agent
```

### DOCX Standardization Pipeline

```
.docx File Uploaded
           |
   DocX Extractor Agent
   (headings, sections, tables, metadata)
           |
   OpenAI Normalization Agent
   (maps to 10-section master structure)
   (confidence scoring per section)
           |
   Confidence >= 70%?
        |         |
      Yes         No
        |         |
   DocX Builder  Human Review Queue
   (rebuild with master template)
   (Word styles, headers, footers, page numbers)
        |
   Standardized .docx Output
        |
   Batch Report (JSON)
   (success / failed / partial per file)
```

---

## Agent Responsibilities

**Ingestion Agent** — Monitors Gmail and Outlook for invoices, accepts PDF uploads, and parses EDI 810 feeds.

**Extraction Agent** — Uses GPT-4o vision to extract all invoice fields including vendor, invoice number, dates, line items, quantities, unit prices, totals, PO number, and payment terms.

**Validation Agent** — Checks required fields, amount tolerances, due dates, vendor master, duplicate invoices, and currency matching.

**Three-Way Match Agent** — Compares invoice against purchase order and goods receipt within a configurable tolerance (default 2%).

**Approval Router Agent** — Applies a configurable approval matrix. Routes to designated approvers by email and SMS with one-click approve or reject links.

**Exception Handler Agent** — Creates exception records, drafts vendor communications via GPT-4o, and queues for human review.

**Payment Scheduler Agent** — Prioritizes by due date, groups payments for batch processing, and triggers ERP payment entry.

**ERP Sync Agent** — Writes approved invoices and payments to QuickBooks, Xero, SAP, or NetSuite with field mapping per ERP schema.

**Audit Logger Agent** — Writes a complete audit trail entry for every state transition. Sends notifications and generates daily summary reports.

**DocX Extractor Agent** — Reads raw .docx files using python-docx. Extracts heading hierarchy, paragraph content, table structure, and document metadata.

**DocX Normalizer Agent** — Sends extracted content to OpenAI GPT-4o with a strict JSON schema prompt. Maps content to master 10-section structure. Returns confidence scores per section. Routes low-confidence documents to human review.

**DocX Builder Agent** — Rebuilds clean .docx output from normalized JSON using python-docx. Python controls all Word formatting programmatically. OpenAI never controls styling.

**DocX Batch Processor** — Processes entire input folders in batch. Logs each file as successful, failed, or partially processed. Includes retry logic for OpenAI failures. Generates a JSON summary report after each batch run.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent Framework | LangGraph |
| AI Models | GPT-4o (vision + text), Claude API (page classification) |
| Document Processing | GPT-4o Vision, PyMuPDF, pytesseract, python-docx |
| Email Ingestion | Gmail API / Microsoft Graph API |
| EDI Ingestion | Custom EDI 810 parser |
| ERP Integration | QuickBooks, Xero, SAP, NetSuite |
| Backend API | FastAPI + Uvicorn |
| Database | Supabase (PostgreSQL) |
| Task Queue | Celery + Redis |
| Notifications | Twilio SMS + SendGrid Email |
| Export | openpyxl (Excel), python-docx (Word) |
| Deployment | Docker + Railway |
| Language | Python 3.12 |

---

## Project Structure

```
AgAI_10_AP_Automation_Agent/
├── agents/
│   ├── extraction_agent.py
│   ├── page_classifier.py
│   ├── validation_agent.py
│   ├── three_way_match_agent.py
│   ├── approval_router_agent.py
│   ├── exception_handler_agent.py
│   ├── payment_scheduler_agent.py
│   ├── erp_sync_agent.py
│   ├── audit_logger_agent.py
│   ├── order_extraction_agent.py
│   ├── order_erp_sync_agent.py
│   ├── docx_extractor.py
│   ├── docx_normalizer.py
│   ├── docx_builder.py
│   └── docx_batch_processor.py
├── api/
│   ├── main.py
│   ├── ingestion_router.py
│   ├── approval_router.py
│   ├── metrics_router.py
│   ├── extraction_router.py
│   ├── order_router.py
│   └── docx_router.py
├── exports/
│   └── excel_exporter.py
├── templates/
│   ├── upload.html
│   ├── order_demo.html
│   └── docx_ui.html
├── core/
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   └── logger.py
├── docx_input/
├── docx_output/
├── Dockerfile
├── railway.json
├── requirements.txt
└── .env.example
```

---

## Setup and Deployment

### Prerequisites

- Python 3.12
- Docker
- Redis
- Supabase account
- OpenAI API key
- Anthropic API key

### Local Setup

```bash
git clone https://github.com/umair801/ap-automation-agent.git
cd ap-automation-agent
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
cp .env.example .env
# Fill in your credentials in .env
uvicorn api.main:app --reload --env-file .env
```

### Environment Variables

```
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
SENDGRID_API_KEY=
SENDGRID_FROM_EMAIL=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
AP_MANAGER_EMAIL=
AP_MANAGER_PHONE=
REDIS_URL=
```

### Docker

```bash
docker build -t ap-ai-agent .
docker run -p 8000:8000 --env-file .env ap-ai-agent
```

---

## Supported ERP Systems

- QuickBooks Online (OAuth2, bill creation, payment entry)
- Xero (OAuth2, ACCPAY invoices, payment sync)
- SAP (RFC/REST, field mapping ready)
- NetSuite (REST API, field mapping ready)

---

## Target Clients

Finance directors, CFOs, and AP managers at mid-to-large companies processing 500+ invoices per month. Document automation clients include compliance teams, legal departments, and operations managers standardizing SOPs, policies, and regulatory documents at scale.

---

## About Datawebify

Datawebify builds enterprise-grade agentic AI systems for organizations that require production-ready automation at scale.

Website: [datawebify.com](https://datawebify.com)
GitHub: [github.com/umair801](https://github.com/umair801)
Document Standardizer: [ap.datawebify.com/docx-ui](https://ap.datawebify.com/docx-ui)
API Docs: [ap.datawebify.com/docs](https://ap.datawebify.com/docs)
