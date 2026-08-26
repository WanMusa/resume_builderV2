import argparse

import requests
from bs4 import BeautifulSoup, Comment

from src.db import get_job, update_job

# Tags that are essentially never useful job-ad content
NOISE_TAGS = [
    "script", "style", "svg", "noscript", "iframe",
    "nav", "footer", "head", "form", "button", "img", "meta", "link",
]


def fetch_job_page(link: str) -> str:
    resp = requests.get(link, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return resp.text


def clean_html_for_llm(raw_html: str) -> str:
    """
    Strip noise tags, comments, and attributes from HTML, then return
    plain text. Deliberately does NOT do "main content" detection
    (like trafilatura/readability) since that can drop bullet lists
    (responsibilities, requirements) that get misjudged as boilerplate.
    """
    soup = BeautifulSoup(raw_html, "lxml")

    for tag in soup(NOISE_TAGS):
        tag.decompose()

    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()

    # Attributes (class/id/style/data-*) are most of the token bloat
    for tag in soup.find_all(True):
        tag.attrs = {}

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


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
        raw_html = fetch_job_page(link)
        cleaned_text = clean_html_for_llm(raw_html)

        if not cleaned_text.strip():
            raise RuntimeError("Cleaned text was empty after scraping")

        update_job(job_id, status="scraped", cleaned_text=cleaned_text, error_message=None)
        print(f"Scraped job page for {job_id} ({len(cleaned_text)} chars)")
    except Exception as e:
        update_job(job_id, status="failed", error_message=str(e))
        print(f"Failed to scrape job {job_id}: {e}")


if __name__ == "__main__":
    main()
