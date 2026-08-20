import argparse
import json
import requests

from src.db import get_job, update_job
from src.llm_backend import get_backend


def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_job_page(link: str) -> str:
    # Basic fetch; some sites may block and become failed jobs (by design).
    resp = requests.get(link, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return resp.text[:120000]  # keep prompt bounded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()

    job_id = args.job_id
    job = get_job(job_id)
    if not job:
        raise RuntimeError(f"Job not found: {job_id}")

    link = job["link"]

    try:
        page_html = fetch_job_page(link)
        prompt_tmpl = load_text("prompts/prompt1_extract_job_scope.txt")
        schema = load_json("schemas/job_scope.schema.json")

        prompt = (
            prompt_tmpl
            .replace("{job_link}", link)
            .replace("{page_content}", page_html)
        )

        backend = get_backend("extract")
        job_scope = backend.complete(prompt=prompt, json_schema=schema)

        update_job(job_id, status="extracted", job_scope=job_scope, error_message=None)
        print(f"Extracted job scope for {job_id}")
    except Exception as e:
        update_job(job_id, status="failed", error_message=str(e))
        print(f"Failed job {job_id}: {e}")


if __name__ == "__main__":
    main()