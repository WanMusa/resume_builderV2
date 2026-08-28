"""
manual_scrape/scrape_locally.py

Run this locally (not in CI) against sites that block GitHub Actions'
datacenter IPs. Reads links from manual_scrape/links.csv, scrapes each
with a plain requests.get (works from a residential IP), and applies
the same cleaning/blocklist logic as src.scrape_job_page.

By default writes to manual_scrapes/exports/<timestamp>.json, which
triggers manual_scrape_pipeline.yml on push.

Use --test to write to manual_scrape/test_runs/<timestamp>.json instead —
a path the pipeline does NOT watch, so you can sanity-check scraping
and cleaning without touching the DB or triggering anything.

Usage:
    python -m manual_scrape.scrape_locally
    python -m manual_scrape.scrape_locally --test
"""

import argparse
import csv
import json
import os
from datetime import datetime, timezone

"""
I am reusing the same cleaning logic as src.scrape_job_page.py, so we just update that file and import the functions here. 
This way we don't have to maintain two separate cleaning implementations.
"""
from src.scrape_job_page import (
    fetch_job_page,
    clean_html_for_llm,
    strip_repeating_chrome,
    trim_trailing_boilerplate,
    extract_seek_company,
)

LINKS_CSV = "manual_scrape/links.csv"
EXPORTS_DIR = "incoming_manual/exports"
TEST_DIR = "manual_scrape/test_runs"


def read_links(csv_path: str) -> list[str]:
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise RuntimeError("CSV has no header row")

        col = None
        for c in ["link", "job_link", "url", "job_url"]:
            if c in reader.fieldnames:
                col = c
                break
        if not col:
            raise RuntimeError(
                "CSV must contain one of columns: link, job_link, url, job_url"
            )

        links = [row[col].strip() for row in reader if (row.get(col) or "").strip()]

    if not links:
        raise RuntimeError(f"No non-empty links found in {csv_path}")
    return links


def scrape_link(link: str) -> dict | None:
    try:
        raw_html = fetch_job_page(link)
        cleaned_text = clean_html_for_llm(raw_html)
        cleaned_text = strip_repeating_chrome(cleaned_text, link)
        cleaned_text = trim_trailing_boilerplate(cleaned_text, link)

        if not cleaned_text.strip():
            print(f"WARNING: empty cleaned text for {link}, skipping")
            return None

        print(f"Scraped {link} ({len(cleaned_text)} chars)")
        return {"link": link, "cleaned_text": cleaned_text}
    except Exception as e:
        print(f"FAILED {link}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--test",
        action="store_true",
        help="Write output to manual_scrape/test_runs/ instead — does not trigger the pipeline",
    )
    parser.add_argument("--links-csv", default=LINKS_CSV)
    args = parser.parse_args()

    links = read_links(args.links_csv)

    results = [r for r in (scrape_link(link) for link in links) if r is not None]

    if not results:
        raise RuntimeError("No jobs scraped successfully — nothing to write")

    out_dir = TEST_DIR if args.test else EXPORTS_DIR
    os.makedirs(out_dir, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = os.path.join(out_dir, f"export_{timestamp}.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"Wrote {len(results)} jobs to {out_path}")
    if args.test:
        print("Test mode — this path is not watched by manual_scrape_pipeline.yml.")
    else:
        print("Next: git add, commit, and push this file to trigger the pipeline.")


if __name__ == "__main__":
    main()