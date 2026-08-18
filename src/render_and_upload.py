import argparse
import io
import json
import re
from pathlib import Path

from src.db import get_job, get_run, update_job
from src.render_documents import build_resume, build_cover_letter, BASE_RESUME


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _safe(text: str) -> str:
    """Strip characters that are invalid in file/folder names."""
    return re.sub(r'[\\/:*?"<>|]', "", text).strip()


def _upload(sb, bucket: str, storage_path: str, doc_bytes: bytes) -> str:
    """Upload bytes to Supabase Storage and return a signed URL (7 days)."""
    sb.storage.from_(bucket).upload(
        path=storage_path,
        file=doc_bytes,
        file_options={
            "content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "upsert": "true",
        },
    )
    result = sb.storage.from_(bucket).create_signed_url(
        path=storage_path,
        expires_in=604800,
    )
    return result.get("signedURL") or result.get("signed_url", "")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--bucket", default="generated-documents")
    args = parser.parse_args()

    job_id = args.job_id

    from src.db import get_client
    sb = get_client()

    job = get_job(job_id)
    if not job:
        raise RuntimeError(f"Job not found: {job_id}")

    if job.get("status") != "cover_letter_generated":
        print(f"Skipping {job_id}: status is {job.get('status')}, expected cover_letter_generated")
        return

    resume_json = job.get("resume_json")
    cover_letter_json = job.get("cover_letter_json")
    job_scope = job.get("job_scope") or {}
    if not resume_json or not cover_letter_json:
        update_job(job_id, status="failed", error_message="Missing resume_json or cover_letter_json for Stage 4")
        print(f"Failed {job_id}: missing JSON data")
        return

    try:
        base_resume = _load_json(BASE_RESUME)
        identity = base_resume["identity"]

        # File name parts
        candidate_name = _safe(identity.get("name", "Candidate"))
        position = _safe(job_scope.get("title", resume_json.get("target_role_tags", ["Role"])[0]))
        organisation = _safe(job_scope.get("company", cover_letter_json.get("company_name", "Organisation")))

        resume_filename = f"{candidate_name}-{position}-{organisation}-Resume.docx"
        cover_filename = f"{candidate_name}-{position}-{organisation}-Cover Letter.docx"

        # Folder: run created_at timestamp (shared across all jobs in the same batch)
        run = get_run(job.get("run_id", ""))
        if run and run.get("created_at"):
            ts = run["created_at"][:16].replace("T", "_").replace(":", "-")
        else:
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M")

        resume_path = f"{ts}/{resume_filename}"
        cover_path = f"{ts}/{cover_filename}"

        # Render to in-memory buffers
        resume_buf = io.BytesIO()
        cover_buf = io.BytesIO()
        build_resume(resume_json, base_resume, resume_buf)
        build_cover_letter(cover_letter_json, base_resume, cover_buf)

        # Upload
        resume_url = _upload(sb, args.bucket, resume_path, resume_buf.getvalue())
        cover_url = _upload(sb, args.bucket, cover_path, cover_buf.getvalue())

        update_job(
            job_id,
            status="completed",
            resume_url=resume_url,
            cover_letter_url=cover_url,
        )
        print(f"Stage 4 complete for {job_id}")
        print(f"  Folder:       {ts}")
        print(f"  Resume:       {resume_url}")
        print(f"  Cover letter: {cover_url}")

    except Exception as e:
        update_job(job_id, status="failed", error_message=str(e))
        print(f"Failed {job_id}: {e}")


if __name__ == "__main__":
    main()
