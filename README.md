# Resume Builder V2

Resume Builder V2 turns job links into tailored application documents.

Given one or more job URLs, it:
- scrapes and cleans the job posting text,
- extracts structured job scope with an LLM,
- generates a tailored resume section,
- generates a tailored cover letter,
- renders both to `.docx`, and
- uploads outputs to Supabase Storage with signed download URLs.

## Ingestion modes

This repo supports two ways to start the pipeline:

1. **CSV ingestion in GitHub Actions** (default)
   - Add/push a CSV to `incoming/`.
   - Workflow: `.github/workflows/pipeline.yml`

2. **Manual scrape on your local machine** (for sites that block cloud runner IPs)
   - Run `python -m manual_scrape.scrape_locally` locally.
   - Commit/push the generated JSON in `incoming_manual/`.
   - Workflow: `.github/workflows/manual_scrape_pipeline.yml`

## End-to-end flow

### A) CSV-driven flow

`incoming/*.csv`  
→ `src.parse_csv` creates `runs` + `jobs` (`pending`)  
→ `src.scrape_job_page` fetches + cleans pages (`scraped`)  
→ `src.extract_job_scope` writes `job_scope` (`extracted`)  
→ `src.generate_resume_partial` writes `resume_json` (`resume_generated`)  
→ `src.generate_cover_letter` writes `cover_letter_json` (`cover_letter_generated`)  
→ `src.render_and_upload` uploads `.docx` and writes URLs (`completed`)

### B) Manual-local-scrape flow

`manual_scrape/links.csv`  
→ run locally: `python -m manual_scrape.scrape_locally`  
→ output JSON in `incoming_manual/export_<timestamp>.json`  
→ commit + push JSON file  
→ `src.ingest_manual_scrape` inserts jobs as `scraped`  
→ pipeline continues from extraction onward (same Stage 1b → Stage 4 path)

## Manual scrape (local) instructions

Use this when a target site blocks GitHub Actions IP ranges.

1. Put URLs into `manual_scrape/links.csv` (header can be `job_link`, `link`, `url`, or `job_url`).
2. Run locally from repo root:
   - `python -m manual_scrape.scrape_locally`
3. Confirm it writes `incoming_manual/export_YYYYMMDDTHHMMSSZ.json`.
4. Commit and push that JSON file.
5. GitHub Actions auto-runs `manual_scrape_pipeline.yml` and continues full generation.

Safe dry-run mode (no pipeline trigger):
- `python -m manual_scrape.scrape_locally --test`
- Writes to `manual_scrape/test_runs/` (not watched by workflows).

## Required configuration

### Python dependencies
Install with:
```bash
pip install -r requirements.txt
```

### GitHub Actions secrets
- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`
- provider keys used by `config.json` stage/provider settings (for example `GROQ_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, etc.)

### Supabase
You need:
- a private storage bucket named `generated-documents`
- `runs` and `jobs` tables

Current pipeline expects the `jobs` table to include at least:
- `status` values covering `pending`, `scraped`, `extracted`, `resume_generated`, `cover_letter_generated`, `completed`, `failed`
- `cleaned_text`, `job_scope`, `resume_json`, `cover_letter_json`, `resume_url`, `cover_letter_url`, `error_message`

Reference setup/migration notes are in `Supabase setup and config.txt`.

## Workflows in this repo

- **`.github/workflows/pipeline.yml`**: CSV-triggered entry workflow (`incoming/**/*.csv`), runs parse + scrape, then calls Stage 1b reusable workflow.
- **`.github/workflows/manual_scrape_pipeline.yml`**: manual-scrape JSON trigger (`incoming_manual/**/*.json`), ingests local scrape exports, then calls Stage 1b reusable workflow.
- **`.github/workflows/stage1_extract_job_scope.yml`**: Stage 1b extraction from `scraped` jobs, then fans into Stage 2 → 3 → 4 reusable workflows.
- **`.github/workflows/stage2_resume_partial.yml`**: resume JSON generation per `job_id`.
- **`.github/workflows/stage3_cover_letter.yml`**: cover letter JSON generation per `job_id`.
- **`.github/workflows/stage4_render_upload.yml`**: `.docx` rendering and Supabase upload per `job_id`.
- **`.github/workflows/copilot-ci-smoke.yml`**: validates Copilot CLI setup in Actions.
- **`.github/workflows/test-supabase-db.yml`**: runs DB smoke test from `test/db_smoke_test.py`.

## File-by-file guide

### Root files

| File | Purpose |
|---|---|
| `README.md` | Repository documentation and operating guide. |
| `Supabase setup and config.txt` | Manual Supabase SQL setup and migration notes. |
| `config.json` | LLM provider + model selection per stage. |
| `requirements.txt` | Python package dependencies. |
| `llm_backend.patch` | Historical patch/diff snapshot for backend updates. |
| `prompt2.patch` | Historical patch/diff snapshot for prompt updates. |
| `scrape_job_page_v2.patch` | Historical patch/diff snapshot for scraping logic updates. |

### GitHub workflows

| File | Purpose |
|---|---|
| `.github/workflows/copilot-ci-smoke.yml` | Manual Copilot CLI smoke test workflow. |
| `.github/workflows/manual_scrape_pipeline.yml` | Triggered by `incoming_manual/**/*.json`; ingests local scrape exports and continues pipeline. |
| `.github/workflows/pipeline.yml` | Triggered by `incoming/**/*.csv`; default entry pipeline. |
| `.github/workflows/stage1_extract_job_scope.yml` | Reusable run-level workflow: extract job scope, then call Stages 2–4. |
| `.github/workflows/stage2_resume_partial.yml` | Reusable job-level Stage 2 workflow. |
| `.github/workflows/stage3_cover_letter.yml` | Reusable job-level Stage 3 workflow. |
| `.github/workflows/stage4_render_upload.yml` | Reusable job-level Stage 4 workflow. |
| `.github/workflows/test-supabase-db.yml` | Manual database smoke test workflow. |

### Source code (`src/`)

| File | Purpose |
|---|---|
| `src/__init__.py` | Package marker for `src` module imports. |
| `src/db.py` | Supabase DB helpers: create/get/update runs/jobs and status queries. |
| `src/parse_csv.py` | Reads latest/selected CSV from `incoming/`, creates run + pending jobs. |
| `src/query_by_status.py` | Returns job IDs for a given `run_id` + status (for workflow fan-out). |
| `src/scrape_job_page.py` | Fetches and cleans job pages, then stores `cleaned_text` and marks jobs `scraped`. |
| `src/extract_job_scope.py` | LLM extraction of structured `job_scope` from `cleaned_text`. |
| `src/generate_resume_partial.py` | LLM generation of tailored resume JSON sections. |
| `src/generate_cover_letter.py` | LLM generation of tailored cover letter JSON. |
| `src/render_documents.py` | Converts resume/cover-letter JSON into `.docx` documents (formatting/template logic). |
| `src/render_and_upload.py` | Renders docs in-memory, uploads to Supabase Storage, saves signed URLs. |
| `src/ingest_manual_scrape.py` | Ingests local scrape export JSON into DB as `scraped` jobs. |
| `src/llm_backend.py` | Multi-provider LLM backend factory + provider implementations + schema validation. |
| `src/__pycache__/__init__.cpython-313.pyc` | Tracked Python bytecode cache artifact. |
| `src/__pycache__/db.cpython-313.pyc` | Tracked Python bytecode cache artifact. |
| `src/__pycache__/llm_backend.cpython-313.pyc` | Tracked Python bytecode cache artifact. |
| `src/__pycache__/render_documents.cpython-313.pyc` | Tracked Python bytecode cache artifact. |
| `src/__pycache__/scrape_job_page.cpython-313.pyc` | Tracked Python bytecode cache artifact. |

### Local manual scraping package (`manual_scrape/`)

| File | Purpose |
|---|---|
| `manual_scrape/__init__.py` | Package marker for local scraping module. |
| `manual_scrape/links.csv` | Input links for local manual scraping runs. |
| `manual_scrape/scrape_locally.py` | Local-only scraper that writes cleaned exports to `incoming_manual/` (or `manual_scrape/test_runs/` in `--test` mode). |
| `manual_scrape/__pycache__/__init__.cpython-313.pyc` | Tracked Python bytecode cache artifact. |
| `manual_scrape/__pycache__/scrape_locally.cpython-313.pyc` | Tracked Python bytecode cache artifact. |

### Prompt templates (`prompts/`)

| File | Purpose |
|---|---|
| `prompts/prompt1_extract_job_scope.txt` | Prompt template for job scope extraction. |
| `prompts/prompt2_generate_resume_partial.txt` | Current prompt template for tailored resume partial generation. |
| `prompts/prompt2_generate_resume_partial_OLD.txt` | Older prompt version kept for comparison/reference. |
| `prompts/prompt3_generate_cover_letter.txt` | Prompt template for cover letter generation. |

### JSON schemas (`schemas/`)

| File | Purpose |
|---|---|
| `schemas/job_scope.schema.json` | Validation schema for Stage 1 extracted job scope JSON. |
| `schemas/resume_partial.schema.json` | Validation schema for Stage 2 resume partial JSON. |
| `schemas/cover_letter.schema.json` | Validation schema for Stage 3 cover letter JSON. |

### Assets and templates (`assets/`)

| File | Purpose |
|---|---|
| `assets/base_resume.json` | Master resume source data used to tailor outputs. |
| `assets/templates/resume_template.docx` | Resume formatting template. |
| `assets/templates/cover_letter_template.docx` | Cover letter formatting template. |
| `assets/test_resume.json` | Sample resume JSON for rendering checks. |
| `assets/test_cover_letter.json` | Sample cover letter JSON for rendering checks. |

### Inputs and output samples

| File | Purpose |
|---|---|
| `incoming/jobs linkedinN20 25082026.csv` | Example CSV input watched by default pipeline. |
| `incoming_manual/export_20260828T102818Z.json` | Example local manual-scrape export consumed by manual ingestion pipeline. |
| `output/pipelineOLD.yml` | Legacy/archived workflow draft kept as reference. |

### Scripts and tests

| File | Purpose |
|---|---|
| `scripts/setup_supabase.py` | One-time helper script for Supabase provisioning. |
| `test/db_smoke_test.py` | DB connectivity + CRUD smoke test for `runs`/`jobs`. |

## Notes

- Stage execution is status-driven via the `jobs.status` field.
- Stage scripts mark failed items with `status = failed` and `error_message`.
- Stage 4 writes signed URLs that currently expire after 7 days.
