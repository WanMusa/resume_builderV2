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
    parser.add_argument("--smoke-test", action="store_true", default=False)
    args = parser.parse_args()

    job_id = args.job_id
    job = get_job(job_id)
    if not job:
        raise RuntimeError(f"Job not found: {job_id}")

    if job.get("status") != "extracted":
        print(f"Skipping {job_id}: status is {job.get('status')}, expected extracted")
        return

    if args.smoke_test:
        update_job(job_id, status="resume_generated", resume_json={"smoke_test": True})
        print(f"Smoke test: wrote placeholder resume_json for {job_id}")
        return

    job_scope = job.get("job_scope")
    if not job_scope:
        update_job(job_id, status="failed", error_message="Missing job_scope for Stage 2")
        print(f"Failed {job_id}: missing job_scope")
        return

    try:
        prompt_tmpl = load_text("prompts/prompt2_generate_resume_partial.txt")
        schema = load_json("schemas/resume_partial.schema.json")
        base_resume = load_json("assets/base_resume.json")

        prompt = prompt_tmpl.format(
            job_scope_json=json.dumps(job_scope, ensure_ascii=False),
            base_resume_json=json.dumps(base_resume, ensure_ascii=False)
        )

        backend = get_backend("generate_resume")
        resume_partial = backend.complete(prompt=prompt, json_schema=schema)

        update_job(
            job_id,
            status="resume_generated",
            resume_json=resume_partial,
            error_message=None
        )
        print(f"Resume partial generated for {job_id}")
    except Exception as e:
        update_job(job_id, status="failed", error_message=str(e))
        print(f"Failed {job_id}: {e}")


if __name__ == "__main__":
    main()