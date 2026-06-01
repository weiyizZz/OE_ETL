# OE_ETL

**Master's Thesis Project | University of Amsterdam & OpenEmbassy**

A Python ETL pipeline that extracts qualitative interview transcripts from Google Drive, transforms unstructured text into structured data via multi-task LLM API calls, and loads the results into a relational database — built to support research on Dutch civic integration (*inburgeringstrajecten*).

> `oedb_baseline.db`, `pipeline.log`, `token_usage_transformer_baseline.json`, `.env`, and `service_account_key.json` are excluded from this repository for privacy and GDPR compliance.

---

## Pipeline Overview

```
Google Drive (interview .docx files)
        │
        ▼
   [ Extract ]  oral_notes/s1_extract/
   doc_loader.py          — Google Drive Service Account authentication, file enumeration
   text_extractor.py      — python-docx + raw XML parsing
   startingIDs_loader.py  — idempotency: resolves starting IDs to avoid duplicate inserts
        │
        ▼
   [ Transform ]  oral_notes/s2_transform/
   prompt_combiner.py         — YAML-based prompt assembly (base + variants)
   text2json_llm_transformer.py — LLM extraction via UvA LLM Proxy (Azure-hosted)
                                  strict JSON schema validation on all outputs
        │
        ▼
   [ Load ]  oral_notes/s3_load/
   json2db_loader.py      — inserts structured JSON output into SQLite
        │
        ▼
   [ Evaluate ]  oral_notes/evaluate/
   result_json_evaluator.py — LLM-as-evaluator for extraction quality assessment
```

---

## Key Design Choices

- **YAML-driven schema and prompts** — field definitions, GDPR sensitivity flags, and prompt templates are declared in `data/`, separating configuration from code
- **LLM-as-extractor** — structured JSON extraction from interview transcripts using a UvA-proxied Azure LLM endpoint with strict schema validation
- **LLM-as-evaluator** *(in progress)* — a second LLM pass evaluates extraction quality and feeds into a refinement loop for iterative accuracy improvement
- **Idempotent pipeline** — safe to re-run; inserts are deduplicated via `startingIDs_loader.py`
- **GDPR-aware** — participant data fields are tagged with sensitivity levels in `schema.yaml`; database, credentials, and logs are excluded from version control

---

## Repository Structure

```
OE_ETL/
├── main.py                        # Pipeline entry point
│
├── oral_notes/                    # Core ETL modules
│   ├── s1_extract/
│   │   ├── doc_loader.py          # Google Drive loader (Service Account)
│   │   ├── text_extractor.py      # .docx text extraction with XML parsing
│   │   └── startingIDs_loader.py  # Idempotency utility
│   ├── s2_transform/
│   │   ├── prompt_combiner.py     # YAML prompt assembly
│   │   └── text2json_llm_transformer.py  # LLM-based extraction
│   ├── s3_load/
│   │   └── json2db_loader.py      # JSON-to-SQLite loader
│   └── evaluate/
│       └── result_json_evaluator.py  # LLM extraction evaluator
│
├── data/
│   ├── input_data/
│   │   └── notegroups.csv         # Interview grouping metadata
│   ├── metadata_DB/
│   │   └── schema.yaml            # Multi-table schema with GDPR sensitivity flags
│   └── prompt_templates/
│       ├── prompt_text2json.yaml  # Extraction prompt template
│       ├── prompt_1recordT.yaml   # Single-record prompt variant
│       └── prompt_evaluator.yaml  # Evaluator prompt template
│
├── DB/
│   ├── tables_creator.py          # Schema initialisation
│   ├── set_WAL.py                 # SQLite WAL mode setup
│   └── clear_all.py               # Database reset utility
│
├── utils/
│   ├── logger.py                  # Pipeline logging
│   ├── token_logger.py            # LLM token usage tracking
│   └── html_viewer.py             # Debug viewer for extracted content
│
├── config/
│   └── config.py                  # Environment and API configuration
│
├── logs/
│   └── cost_sum.ipynb             # Token cost analysis notebook
│
└── testing/                       # Unit and integration tests
```

---

## Tech Stack

Python 3.11 · SQLite · Google Drive API · PyYAML · Azure OpenAI (via UvA LLM Proxy)

---

## Status

Active development. Current focus: LLM evaluator and refinement operator for improving extraction accuracy on qualitative interview data.
