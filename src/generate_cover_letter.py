import argparse
import json
from pathlib import Path

from src.db import get_job, update_job
from src.llm_backend import get_backend


def load_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def load_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()

    job_id = args.job_id
    job = get_job(job_id)
    if not job:
        raise RuntimeError(f"Job not found: {job_id}")

    if job.get("status") != "resume_generated":
        print(f"Skipping {job_id}: status is {job.get('status')}, expected resume_generated")
        return

    job_scope = job.get("job_scope")
    if not job_scope:
        update_job(job_id, status="failed", error_message="Missing job_scope for Stage 3")
        print(f"Failed {job_id}: missing job_scope")
        return

    resume_json = job.get("resume_json")
    if not resume_json:
        update_job(job_id, status="failed", error_message="Missing resume_json for Stage 3")
        print(f"Failed {job_id}: missing resume_json")
        return

    try:
        prompt_tmpl = load_text("prompts/prompt3_generate_cover_letter.txt")
        schema = load_json("schemas/cover_letter.schema.json")

        prompt = prompt_tmpl.format(
            job_scope_json=json.dumps(job_scope, ensure_ascii=False),
            resume_json=json.dumps(resume_json, ensure_ascii=False)
        )

        backend = get_backend("generate_cover_letter")
        cover_letter = backend.complete(prompt=prompt, json_schema=schema)

        update_job(
            job_id,
            status="cover_letter_generated",
            cover_letter_json=cover_letter,
        )
        print(f"Cover letter generated for {job_id}")
    except Exception as e:
        update_job(job_id, status="failed", error_message=str(e))
        print(f"Failed {job_id}: {e}")


if __name__ == "__main__":
    main()
