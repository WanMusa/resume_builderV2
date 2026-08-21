"""
setup_supabase.py — One-time provisioning script for Supabase resources.

Creates:
  1. Storage bucket: "generated-documents" (private, 50MB file size limit)
  2. Database tables: runs, jobs (idempotent — skips if already exist)

Usage:
  python scripts/setup_supabase.py

Requires env vars:
  SUPABASE_URL        — e.g. https://xxxx.supabase.co
  SUPABASE_SECRET_KEY — service role key (Settings > API > service_role)
"""

import os
import sys

from supabase import create_client

BUCKET = "generated-documents"

CREATE_RUNS_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status        TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'completed', 'failed')),
    total_links   INTEGER NOT NULL DEFAULT 0,
    source_csv    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ
);
"""

CREATE_JOBS_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id           UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    link             TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    job_scope        JSONB,
    resume_json      JSONB,
    cover_letter_json JSONB,
    resume_url       TEXT,
    cover_letter_url TEXT,
    error_message    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def main():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SECRET_KEY")

    if not url or not key:
        print("ERROR: Set SUPABASE_URL and SUPABASE_SECRET_KEY environment variables.")
        sys.exit(1)

    sb = create_client(url, key)

    # ── 1. Storage bucket ────────────────────────────────────────────────────
    print(f"Creating storage bucket '{BUCKET}'...")
    try:
        sb.storage.create_bucket(
            BUCKET,
            options={
                "public": False,
                "file_size_limit": 52428800,  # 50 MB
                "allowed_mime_types": [
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ],
            },
        )
        print(f"  ✓ Bucket '{BUCKET}' created.")
    except Exception as e:
        msg = str(e).lower()
        if "already exists" in msg or "duplicate" in msg:
            print(f"  ✓ Bucket '{BUCKET}' already exists — skipped.")
        else:
            print(f"  ✗ Failed to create bucket: {e}")
            sys.exit(1)

    # ── 2. Database tables ────────────────────────────────────────────────────
    print("Creating database tables...")
    for name, sql in [("runs", CREATE_RUNS_SQL), ("jobs", CREATE_JOBS_SQL)]:
        try:
            sb.rpc("exec_sql", {"sql": sql}).execute()
            print(f"  ✓ Table '{name}' ready.")
        except Exception:
            # exec_sql RPC may not exist; fall back to a direct POST to /rest/v1/rpc
            # In that case the user should run the SQL manually in Supabase SQL Editor.
            print(
                f"  ! Could not auto-create table '{name}' via RPC.\n"
                f"    Run the following SQL in Supabase SQL Editor:\n\n{sql}"
            )

    print("\nSetup complete.")


if __name__ == "__main__":
    main()
