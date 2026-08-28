"""
This script ingests a manual scrape export file (JSON) and inserts the jobs into the database.
The JSON file needs to be produced by the manual scrape process, which is a separate script that scrapes job postings from a list of links.
The manual script is in manual_scrape/scrape_locally.py, and the export file is produced by running that script with the --export flag.
"""

import argparse
import glob
import json
import os
from typing import Any, Dict, List

from src.db import create_run, insert_job

REQUIRED_FIELDS = ["link", "cleaned_text"]


def find_latest_export(manual_dir: str = "manual_scrapes") -> str:
    paths = glob.glob(os.path.join(manual_dir, "*.json"))
    if not paths:
        raise RuntimeError("No export files found in manual_scrapes/")
    paths.sort(key=os.path.getmtime, reverse=True)
    return paths[0]


def parse_export(export_path: str) -> List[Dict[str, Any]]:
    with open(export_path, "r", encoding="utf-8") as f:
        jobs = json.load(f)

    if not isinstance(jobs, list) or not jobs:
        raise RuntimeError("Export file must contain a non-empty list of jobs")

    for job in jobs:
        missing = [field for field in REQUIRED_FIELDS if not (job.get(field) or "").strip()]
        if missing:
            raise RuntimeError(f"Job entry missing required field(s) {missing}: {job}")

    return jobs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=None, help="Optional explicit export file path")
    args = parser.parse_args()

    export_path = args.file or find_latest_export("manual_scrapes")
    jobs = parse_export(export_path)

    run_id = create_run(total_links=len(jobs), source_csv=export_path)
    for job in jobs:
        insert_job(
            run_id=run_id,
            link=job["link"],
            status="scraped",
            cleaned_text=job["cleaned_text"],
        )

    print(f"run_id={run_id}")
    print(f"links_json={json.dumps([job['link'] for job in jobs])}")


if __name__ == "__main__":
    main()