# AP-AI: Enterprise Accounts Payable Automation Agent

**Built by [Datawebify](https://datawebify.com) | Live at [ap.datawebify.com](https://ap.datawebify.com)**

---

## What This System Does

AP-AI is a fully autonomous accounts payable agent that eliminates manual invoice processing. It ingests invoices from email, PDF upload, or EDI feeds, extracts all fields using GPT-4o vision, validates against business rules, runs three-way matching against purchase orders and goods receipts, routes for approval, schedules payments, and syncs every transaction to QuickBooks, Xero, SAP, or NetSuite — with zero manual data entry and a complete audit trail.

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

---

## Live Endpoints

| Endpoint | Description |
|---|---|
| `GET /metrics/health` | System health check |
| `GET /metrics` | Real-time AP KPIs |
| `POST /ingest/pdf` | Upload invoice PDF |
| `POST /ingest/email-webhook` | Email webhook receiver |
| `POST /ingest/edi` | EDI 810 invoice upload |
| `GET /approval/decide` | One-click approve or reject |
| `GET /approval/status/{invoice_number}` | Approval status query |
| `GET /docs` | Interactive API documentation |

---

## System Architecture

The system uses a LangGraph-orchestrated multi-agent pipeline. GPT-4o handles document intelligence. The graph handles workflow routing. All approval logic is rule-based and configurable per client.

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

### Agent Responsibilities

**Ingestion Agent** — Monitors Gmail and Outlook for invoices, accepts PDF uploads, and parses EDI 810 feeds. Classifies documents and stores raw files with metadata.

**Extraction Agent** — Uses GPT-4o vision to extract all invoice fields: vendor, invoice number, dates, line items, quantities, unit prices, totals, PO number, and payment terms. Falls back to pytesseract OCR for scanned documents.

**Validation Agent** — Checks required fields, amount tolerances, due dates, vendor master, duplicate invoices, and currency matching. Flags exceptions with specific error codes.

**Three-Way Match Agent** — Compares invoice against purchase order and goods receipt within a configurable tolerance (default 2%). Returns full match, partial match, or mismatch.

**Approval Router Agent** — Applies a configurable approval matrix. Invoices below threshold auto-approve. Above threshold routes to the designated approver by email and SMS with one-click approve or reject link. Escalates after configurable timeout.

**Exception Handler Agent** — Creates exception records, drafts vendor communications via GPT-4o, and queues for human review with full context.

**Payment Scheduler Agent** — Prioritizes by due date, groups payments for batch processing, and triggers ERP payment entry.

**ERP Sync Agent** — Writes approved invoices and payments to QuickBooks, Xero, SAP, or NetSuite. Handles field mapping per ERP schema. Retries on transient failures.

**Audit Logger Agent** — Writes a complete audit trail entry for every state transition. Sends notifications via email and SMS. Generates daily summary reports.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent Framework | LangGraph |
| AI Model | GPT-4o (vision + text) |
| Document Processing | GPT-4o Vision + PyMuPDF + pytesseract |
| Email Ingestion | Gmail API / Microsoft Graph API |
| EDI Ingestion | Custom EDI 810 parser |
| ERP Integration | QuickBooks, Xero, SAP, NetSuite |
| Backend API | FastAPI + Uvicorn |
| Database | Supabase (PostgreSQL) |
| Task Queue | Celery + Redis |
| Notifications | Twilio SMS + SendGrid Email |
| Deployment | Docker + Railway |
| Language | Python 3.12 |

---

## Project Structure

```
AgAI_10_AP_Automation_Agent/
├── agents/
│   ├── ingestion_agent.py
│   ├── extraction_agent.py
│   ├── validation_agent.py
│   ├── three_way_match_agent.py
│   ├── approval_router_agent.py
│   ├── exception_handler_agent.py
│   ├── payment_scheduler_agent.py
│   ├── erp_sync_agent.py
│   └── audit_logger_agent.py
├── core/
│   ├── orchestrator.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   └── logger.py
├── api/
│   ├── main.py
│   ├── ingestion_router.py
│   ├── approval_router.py
│   └── metrics_router.py
├── integrations/
│   ├── gmail_client.py
│   ├── quickbooks_client.py
│   └── xero_client.py
├── parsers/
│   ├── pdf_parser.py
│   └── edi_parser.py
├── notifications/
│   ├── email_sender.py
│   └── sms_sender.py
├── tests/
│   ├── test_extraction.py
│   ├── test_three_way_match.py
│   ├── test_approval_routing.py
│   ├── test_erp_sync.py
│   └── test_exception_handling.py
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

### Local Setup

```bash
git clone https://github.com/umair801/ap_automation_agent.git
cd ap_automation_agent
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
cp .env.example .env
# Fill in your credentials in .env
uvicorn api.main:app --reload
```

### Environment Variables

```
OPENAI_API_KEY=
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

### Run Tests

```bash
python -m tests.test_extraction
python -m tests.test_three_way_match
python -m tests.test_approval_routing
python -m tests.test_erp_sync
python -m tests.test_exception_handling
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

Finance directors, CFOs, and AP managers at mid-to-large companies processing 500+ invoices per month. Vertical fit includes manufacturing, logistics, professional services, and healthcare administration.

---

## About Datawebify

Datawebify builds enterprise-grade agentic AI systems for organizations that require production-ready automation at scale.

Website: [datawebify.com](https://datawebify.com)
GitHub: [github.com/umair801](https://github.com/umair801)
Live Demo: [ap.datawebify.com](https://ap.datawebify.com)
