import argparse
import csv
import glob
import json
import os
from typing import List

from src.db import create_run, insert_job

CANDIDATE_COLUMNS = ["job_link", "link", "url", "job_url"]


def find_latest_csv(incoming_dir: str = "incoming") -> str:
    paths = glob.glob(os.path.join(incoming_dir, "*.csv"))
    if not paths:
        raise RuntimeError("No CSV files found in incoming/")
    paths.sort(key=os.path.getmtime, reverse=True)
    return paths[0]


def parse_links(csv_path: str) -> List[str]:
    links: List[str] = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise RuntimeError("CSV has no header row")

        col = None
        for c in CANDIDATE_COLUMNS:
            if c in reader.fieldnames:
                col = c
                break
        if not col:
            raise RuntimeError(
                f"CSV must contain one of columns: {', '.join(CANDIDATE_COLUMNS)}"
            )

        for row in reader:
            link = (row.get(col) or "").strip()
            if link:
                links.append(link)

    if not links:
        raise RuntimeError("No non-empty job links found in CSV")
    return links


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=None, help="Optional explicit CSV path")
    args = parser.parse_args()

    csv_path = args.csv or find_latest_csv("incoming")
    links = parse_links(csv_path)

    run_id = create_run(total_links=len(links), source_csv=csv_path)
    for link in links:
        insert_job(run_id=run_id, link=link)

    print(f"run_id={run_id}")
    print(f"links_json={json.dumps(links)}")


if __name__ == "__main__":
    main()