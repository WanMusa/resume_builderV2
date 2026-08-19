# Resume Builder V2

Automated job-application document generator. Drop a CSV of job links — get tailored resumes and cover letters uploaded to cloud storage, ready to send.

**Pipeline status: All 4 stages complete and running end-to-end.**

---

## How it works

```
incoming/*.csv  →  Stage 1  →  Stage 2  →  Stage 3  →  Stage 4
  (job links)     extract     tailored    cover       render +
                  job scope   resume      letter      upload .docx
```

1. Add a CSV file with a `job_link` column to `incoming/` and push to `main`.
2. GitHub Actions triggers automatically — all stages run in parallel per job.
3. Each job's tailored resume and cover letter are uploaded to Supabase Storage.
4. Download links (valid 7 days) are stored in the `jobs` table (`resume_url`, `cover_letter_url`).

> No generated files are committed back to the repo. Everything goes to Supabase.

---

## Pipeline stages

### Stage 1 — Extract job scope (`src/parse_csv.py` + `src/extract_job_scope.py`)
- Reads CSV, creates a `runs` row and `jobs` rows in Supabase
- Scrapes each job posting URL and calls the LLM to extract structured job scope JSON
- Output: `jobs.job_scope`, status → `extracted`
- Schema: `schemas/job_scope.schema.json`
- Prompt: `prompts/prompt1_extract_job_scope.txt`

### Stage 2 — Generate tailored resume (`src/generate_resume_partial.py`)
- Reads `job_scope` + `assets/base_resume.json` (your full resume)
- Calls the LLM to generate mutable resume sections tailored to the role:
  - `target_role_tags`, `career_profile`, `areas_of_expertise`, `professional_experience`
- Output: `jobs.resume_json`, status → `resume_generated`
- Schema: `schemas/resume_partial.schema.json`
- Prompt: `prompts/prompt2_generate_resume_partial.txt`

### Stage 3 — Generate cover letter (`src/generate_cover_letter.py`)
- Reads `job_scope` + `resume_json`
- Calls the LLM to write a tailored 1-page cover letter following Harvard Career Services guidelines
- Detects whether the posting is from a recruiter or direct employer and adjusts tone
- Output: `jobs.cover_letter_json`, status → `cover_letter_generated`
- Schema: `schemas/cover_letter.schema.json`
- Prompt: `prompts/prompt3_generate_cover_letter.txt`

### Stage 4 — Render and upload (`src/render_and_upload.py`)
- Renders `resume_json` + `cover_letter_json` into `.docx` files using python-docx
- Uploads to Supabase Storage bucket `generated-documents`
- Files are named: `{Name}-{Position}-{Organisation}-Resume.docx` / `Cover Letter.docx`
- All jobs from the same CSV batch share a timestamped folder (`YYYY-MM-DD_HH-MM/`)
- Output: `jobs.resume_url`, `jobs.cover_letter_url`, status → `completed`

---

## Triggering the pipeline

**Automatic:** Push a CSV file into `incoming/` — the pipeline starts immediately.

**Manual (single job):** Each stage has a `workflow_dispatch` trigger. Go to Actions → select the stage → Run workflow → enter a `job_id` UUID.

```
Actions available:
  pipeline.yml               ← full pipeline (triggered by CSV push)
  stage2_resume_partial.yml  ← manual Stage 2 only
  stage3_cover_letter.yml    ← manual Stage 3 only
  stage4_render_upload.yml   ← manual Stage 4 only
```

**Smoke test (Stage 2):** Enable the `smoke_test` checkbox when running Stage 2 manually to verify DB writes before running the full LLM generation.

---

## Setup

### 1. GitHub Secrets
Add the following secrets in your repo settings (`Settings → Secrets → Actions`):

| Secret | Description |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SECRET_KEY` | Service role key (not anon key) |
| `GITHUB_TOKEN` | Auto-provided by GitHub Actions |

### 2. Supabase database
Required tables:

**`runs`**
| Column | Type |
|---|---|
| `id` | uuid (PK) |
| `status` | text |
| `total_links` | int |
| `source_csv` | text |
| `created_at` | timestamptz |
| `finished_at` | timestamptz |

**`jobs`**
| Column | Type |
|---|---|
| `id` | uuid (PK) |
| `run_id` | uuid (FK → runs) |
| `link` | text |
| `status` | text (check: pending/extracted/resume_generated/cover_letter_generated/completed/failed) |
| `job_scope` | jsonb |
| `resume_json` | jsonb |
| `cover_letter_json` | jsonb |
| `resume_url` | text |
| `cover_letter_url` | text |
| `error_message` | text |
| `updated_at` | timestamptz |

### 3. Supabase Storage
Create a **private** bucket named `generated-documents`.

### 4. Base resume
Populate `assets/base_resume.json` with your full resume details. This is the LLM's source of truth — the richer the detail, the better the tailoring. Structure:

```json
{
  "identity": { "name", "email", "mobile", "location", "linkedin" },
  "fixed_sections": { "education", "certifications", "references" },
  "base_sections": { ... full work experience ... }
}
```

### 5. LLM config
Edit `config.json` to change the model per stage:

```json
{
  "extract":               { "backend": "copilot_cli", "model": "claude-sonnet-4.6" },
  "generate_resume":       { "backend": "copilot_cli", "model": "claude-opus-4.5" },
  "generate_cover_letter": { "backend": "copilot_cli", "model": "claude-opus-4.5" }
}
```

Currently uses GitHub Copilot CLI (`@github/copilot` npm package) via `GITHUB_TOKEN`. To switch to another provider (e.g. Groq), add a new backend class in `src/llm_backend.py`.

---

## Project structure

```
.github/workflows/
  pipeline.yml                  Full pipeline orchestrator
  stage2_resume_partial.yml     Stage 2 reusable workflow
  stage3_cover_letter.yml       Stage 3 reusable workflow
  stage4_render_upload.yml      Stage 4 reusable workflow
  copilot-ci-smoke.yml          Copilot CLI connectivity test

assets/
  base_resume.json              Your master resume (source of truth for LLM)
  templates/
    resume_template.docx        Word template (styles/margins reference)
    cover_letter_template.docx  Word template (styles/margins reference)

incoming/                       Drop CSVs here to trigger the pipeline

prompts/
  prompt1_extract_job_scope.txt
  prompt2_generate_resume_partial.txt
  prompt3_generate_cover_letter.txt

schemas/
  job_scope.schema.json
  resume_partial.schema.json
  cover_letter.schema.json

src/
  db.py                         Supabase DB helpers
  llm_backend.py                LLM abstraction (Copilot CLI backend)
  parse_csv.py                  Stage 1a: parse CSV, create run/jobs
  extract_job_scope.py          Stage 1b: scrape + extract job scope
  query_by_status.py            Helper: fetch job IDs by status
  generate_resume_partial.py    Stage 2: generate tailored resume JSON
  generate_cover_letter.py      Stage 3: generate cover letter JSON
  render_documents.py           Renderer: JSON → .docx (resume + cover letter)
  render_and_upload.py          Stage 4: render + upload to Supabase Storage

config.json                     LLM backend/model config per stage
requirements.txt                Python dependencies
```

---

## CSV format

```csv
job_link
https://www.linkedin.com/jobs/view/1234567890/
https://www.seek.co.nz/job/12345678
```

Column must be one of: `job_link`, `link`, `url`, `job_url`.

---

## Notes
- The pipeline uses GitHub Actions as free cloud compute — no server required.
- LLM calls use GitHub Copilot CLI which requires a Copilot license via `GITHUB_TOKEN`.
- Signed URLs expire after 7 days. Re-run Stage 4 for a fresh link if needed.
- To switch LLM providers, implement a new backend class in `src/llm_backend.py` and update `config.json`.
  Stage 1: fetches job page, calls LLM, validates JSON, writes result/status.

### Input
- `incoming/*.csv`  
  Trigger files. Must include a `job_link` column.

---

## Required GitHub Secrets

- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`

---

## Copilot in GitHub Actions

This workflow uses:
- job permission: `copilot-requests: write`
- step env: `GITHUB_TOKEN: ${{ github.token }}`

No PAT is required for this setup.

---

## Status model (current)

`pending` → `extracted`  
or  
`pending` → `failed` (with `error_message`)

---

## Next planned stages

- Stage 2: Generate tailored resume JSON
- Stage 3a: Build resume `.docx`
- Stage 3b: Generate cover letter JSON
- Stage 4: Build cover letter `.docx`

We will update this README as each stage is added.