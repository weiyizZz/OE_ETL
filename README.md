# OE_ETL

**Master's Thesis Project | University of Amsterdam & OpenEmbassy**

A Python ETL pipeline that extracts qualitative interview transcripts from Google Drive, transforms unstructured text into structured data via multi-task LLM API calls, and loads the results into a relational database.

> `oedb_baseline.db`, `pipeline.log`, `token_usage_transformer_baseline.json`, `.env`, and `service_account_key.json` are excluded from this repository for privacy.

---

## Pipeline Overview

```
Google Drive (interview .docx files)
        │
        ▼
   [ Extract ]  oral_notes/s1_extract/
   doc_loader.py                    — Google Drive file loading, with metadata extraction
   text_extractor.py                — docx + spreadsheets parsing
   startingIDs_loader.py            — resolves starting IDs
        │
        ▼
   [ Transform ]  
   -- oral_notes/
   prompt_combiner_v3.py            — YAML-based prompt assembly 
                                    (base + variants, placeholders filled)
   -- oral_notes/s2_transform/
   participant_llm_reducer.py       — filters to only involved participants (LLM based)
   text2json_llm_transformer_v3.py  — LLM extraction, including self-refining loop
        │
        ▼
   [ Load ]  oral_notes/s3_load/
   json2db_loader.py                — inserts/updates structured JSON output into SQLite
```

---

## Key Design Choices

- **Database Schema** — designed according to six competency questions, and further optimized according to input data characteristics
- **Document Parsing** — spreadsheets (CSV, XLSX) are converted into Markdown tables; word-processing documents (DOC, DOCX) are extracted with the paragraphs and tables (converted into text) in their original orders
- **Redundant Data Removal** — participant filtering (leaving only the participants who joined the session), non-response participants and questions removing
- **Structured JSON Extraction** — the input text contents are extracted into several tables (the extraction of each table is decomposed into a separate task), following the pre-defined database schema and specific extraction rules
- **Self-refinement** — a self-refinement step that iterates on the whole outputs of selected LLM-drievn tasks (the ones that are proven to be effective with this applied when trying on the training set), with error patterns being informed (which were observed when manually analyzing the errors that the LLM extractor made on the training set)

---

## Repository Structure

```
OE_ETL/
├── ETL_main.py                        # Pipeline entry point
│
├── oral_notes/                    # Core ETL modules
│   ├── s1_extract/
│   │   ├── doc_loader.py          # Google Drive loader (Service Account)
│   │   ├── text_extractor.py      # .docx or spreadsheets text extraction with XML parsing for tables
│   │   └── startingIDs_loader.py
│   ├── s2_transform/
│   │   ├── participant_llm_reducer.py      # LLM-based participant filter (participants who joined the session)
│   │   └── text2json_llm_transformer.py  # LLM-based extraction
│   ├── s3_load/
│   │   └── json2db_loader.py      # JSON-to-SQLite loader
│   └── prompt_combiner.py     # YAML prompt assembly
│
├── data/
│   ├── input_data/
│   │   └── notegroups.csv         # Interview notes grouping, storing Google Drive urls
│   ├── metadata_DB/
│   │   └── schema_v3.yaml            # Multi-table schema
│   └── prompt_templates/
│       ├── prompt_text2json_v3.yaml  # Extraction prompt template
│       ├── prompt_1recordT.yaml   # Single-record prompt variant, extrating information in the table "notegroups"
│       ├── prompt_ParReducer.yaml  # Participant filter prompt template
│       └──refiner/                 # Prompts for LLM refinement of each LLM function
│           ├── prompt_refiner_1recordT.yaml
│           ├── prompt_refiner_ParReducer.yaml  
│           └── prompt_refiner_pqa.yaml
│
├── DB/
│   ├── tables_creator.py          # Schema initialisation
│   ├── set_WAL.py                 # SQLite WAL mode setup
│   └── clear_all.py               # Database reset utility
│
├── utils/
│   ├── logger.py                  # Pipeline logging
│   ├── token_logger.py            # LLM token usage tracking
│   └── html_viewer.py             # Viewer for extracted content
│
├── config/
│   └── config.py                  # Environment and API configuration
│
├── logs/
│
└── testing/                       # Unit tests
```

---

## Tech Stack

Python 3.11 · SQLite · Google Drive API · PyYAML · Azure OpenAI

---

## Status

Development for the thesis is finished. Further optimization may be applied before put into practice.
