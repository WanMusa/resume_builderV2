import os
import sys
from datetime import datetime, timezone

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")


def fail(msg: str, code: int = 1):
    print(f"[FAIL] {msg}")
    sys.exit(code)


def ok(msg: str):
    print(f"[OK] {msg}")


def main():
    if not SUPABASE_URL:
        fail("Missing SUPABASE_URL environment variable.")
    if not SUPABASE_SECRET_KEY:
        fail("Missing SUPABASE_SECRET_KEY environment variable.")

    ok("Environment variables found.")

    try:
        sb = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
        ok("Supabase client created.")
    except Exception as e:
        fail(f"Could not create Supabase client: {e}")

    # 1) Insert into runs
    source_csv = f"test/smoke-{datetime.now(timezone.utc).isoformat()}.csv"
    run_payload = {
        "status": "running",
        "total_links": 1,
        "source_csv": source_csv,
    }

    try:
        run_resp = sb.table("runs").insert(run_payload).execute()
        run_rows = run_resp.data or []
        if not run_rows:
            fail("Insert into runs returned no data.")
        run_id = run_rows[0]["id"]
        ok(f"Inserted runs row: {run_id}")
    except Exception as e:
        fail(f"Failed inserting runs row: {e}")

    # 2) Insert into jobs
    job_payload = {
        "run_id": run_id,
        "link": "https://example.com/job/smoke-test",
        "status": "pending",
    }

    try:
        job_resp = sb.table("jobs").insert(job_payload).execute()
        job_rows = job_resp.data or []
        if not job_rows:
            fail("Insert into jobs returned no data.")
        job_id = job_rows[0]["id"]
        ok(f"Inserted jobs row: {job_id}")
    except Exception as e:
        fail(f"Failed inserting jobs row: {e}")

    # 3) Update job status progression
    try:
        update_resp = (
            sb.table("jobs")
            .update(
                {
                    "status": "extracted",
                    "job_scope": {
                        "title": "Smoke Test Title",
                        "company": "Smoke Test Company",
                        "raw_summary": "DB connectivity test",
                    },
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", job_id)
            .execute()
        )
        if not update_resp.data:
            fail("Update jobs returned no data.")
        ok("Updated jobs row to extracted with sample job_scope JSON.")
    except Exception as e:
        fail(f"Failed updating jobs row: {e}")

    # 4) Finish run
    try:
        finish_resp = (
            sb.table("runs")
            .update(
                {
                    "status": "completed",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", run_id)
            .execute()
        )
        if not finish_resp.data:
            fail("Update runs returned no data.")
        ok("Updated runs row to completed with finished_at.")
    except Exception as e:
        fail(f"Failed updating runs row: {e}")

    ok("Supabase DB smoke test passed.")


if __name__ == "__main__":
    main()