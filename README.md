# Resume Builder V2 Pipeline (WIP)

This project automates job-application content from a CSV of job links.

Current build status: **Stage 0 + Stage 1 implemented**
- Stage 0 = read CSV + create DB run/jobs rows
- Stage 1 = extract job info from each link using Copilot CLI + save JSON to Supabase

---

## What this does (simple flow)

1. You add a CSV file to `incoming/` (with a `job_link` column).
2. GitHub Actions starts automatically (or you run it manually).
3. Pipeline creates a `runs` record and `jobs` records in Supabase.
4. For each job link, Copilot extracts job scope into structured JSON.
5. JSON is saved in Supabase `jobs.job_scope`.
6. Each job row is marked `extracted` or `failed` with error details.
7. Run row is finalized as `completed` or `failed`.

> No output files are committed back to GitHub after a run.

---

## File guide (brief)

### Workflow
- `.github/workflows/pipeline.yml`  
  Orchestrates Stage 0 and Stage 1 in GitHub Actions.

### Config
- `config.json`  
  Chooses LLM backend/model per stage (easy to change later).

### Prompts & schema
- `prompts/prompt1_extract_job_scope.txt`  
  Prompt template for extracting job scope from posting content.
- `schemas/job_scope.schema.json`  
  JSON structure required for extraction output.

### Python source
- `src/db.py`  
  Supabase DB helper functions (create run, insert/update jobs, finish run).
- `src/llm_backend.py`  
  LLM abstraction layer (currently Copilot CLI backend).
- `src/parse_csv.py`  
  Stage 0: reads CSV, creates run, inserts pending jobs.
- `src/query_by_status.py`  
  Helper to fetch job IDs by status for matrix jobs.
- `src/extract_job_scope.py`  
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