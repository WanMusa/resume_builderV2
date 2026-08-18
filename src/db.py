import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from supabase import create_client, Client


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SECRET_KEY")
    if not url:
        raise RuntimeError("Missing SUPABASE_URL")
    if not key:
        raise RuntimeError("Missing SUPABASE_SECRET_KEY")
    return create_client(url, key)


def create_run(total_links: int, source_csv: str) -> str:
    sb = get_client()
    resp = (
        sb.table("runs")
        .insert(
            {
                "status": "running",
                "total_links": total_links,
                "source_csv": source_csv,
            }
        )
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise RuntimeError("Failed to create run row")
    return rows[0]["id"]


def finish_run(run_id: str, status: str) -> None:
    sb = get_client()
    (
        sb.table("runs")
        .update({"status": status, "finished_at": _now_iso()})
        .eq("id", run_id)
        .execute()
    )


def insert_job(run_id: str, link: str) -> str:
    sb = get_client()
    resp = (
        sb.table("jobs")
        .insert(
            {
                "run_id": run_id,
                "link": link,
                "status": "pending",
            }
        )
        .execute()
    )
    rows = resp.data or []
    if not rows:
        raise RuntimeError(f"Failed to insert job for link: {link}")
    return rows[0]["id"]


def update_job(job_id: str, **fields: Any) -> None:
    sb = get_client()
    payload: Dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
    payload["updated_at"] = _now_iso()
    resp = sb.table("jobs").update(payload).eq("id", job_id).execute()
    if not resp.data:
        raise RuntimeError(f"update_job affected 0 rows for job_id={job_id}. Payload keys: {list(payload.keys())}")


def get_jobs_by_status(run_id: str, status: str) -> List[Dict[str, Any]]:
    sb = get_client()
    resp = (
        sb.table("jobs")
        .select("*")
        .eq("run_id", run_id)
        .eq("status", status)
        .execute()
    )
    return resp.data or []


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    sb = get_client()
    resp = sb.table("jobs").select("*").eq("id", job_id).limit(1).execute()
    rows = resp.data or []
    return rows[0] if rows else None