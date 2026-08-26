import argparse
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Comment

from src.db import get_job, update_job

# Tags that are essentially never useful job-ad content
NOISE_TAGS = [
    "script", "style", "svg", "noscript", "iframe",
    "nav", "footer", "head", "form", "button", "img", "meta", "link",
]

# Invisible/zero-width Unicode characters that add noise but no visible
# content (word joiner, zero-width space/non-joiner/joiner, BOM).
ZERO_WIDTH_CHARS_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")

# Per-site markers where real job content ends and page chrome
# (related listings, sidebar widgets, scam warnings) begins. Text from
# the first matching marker onward is cut. Add new domains here as you
# hit them — every job board has its own trailing cruft.
TRAILING_BOILERPLATE_MARKERS = {
    "linkedin.com": [
        "Referrals increase your chances",
        "Similar jobs",
        "People also viewed",
    ],
    # Matches nz.seek.com, seek.com.au, etc.
    "seek.com": [
        "Unlock job insights",
    ],
}

# Recurring multi-line blocks that repeat verbatim mid-page (login
# walls, consent prompts). Matched with regex since the surrounding
# text is identical every time it appears, just repeated.
REPEATED_BLOCK_PATTERNS = {
    "linkedin.com": [
        re.compile(
            r"or\nNew to LinkedIn\?\nJoin now\nBy clicking Continue to join or "
            r"sign in, you agree to LinkedIn.s\nUser Agreement\n,\nPrivacy Policy\n"
            r", and\nCookie Policy\n\."
        ),
    ],
}

# Standalone lines that are pure chrome/CTA text, regardless of context.
# Add new domains here as you hit them.
LINE_BLOCKLIST_BY_DOMAIN = {
    "linkedin.com": {
        "Join or sign in to find your next job",
        "Join or sign in to save this job",
        "Use AI to assess how you fit",
        "Get AI-powered advice on this job and more exclusive features.",
        "Sign in to access AI-powered advices",
        "Sign in to evaluate your skills",
        "Sign in to tailor your resume",
        "Report this job",
    },
    "seek.com": {
        "Skip to content", "SEEK", "Sign in", "Sign In", "Job search",
        "People search", "Career advice", "Companies", "Recruiters",
        "Employer site", "Register", "View all jobs", "Apply",
        "Australia", "Hong Kong", "Indonesia", "Malaysia", "New Zealand",
        "Philippines", "Singapore", "Thailand",
    },
}


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
    text = ZERO_WIDTH_CHARS_RE.sub("", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def strip_repeating_chrome(text: str, link: str) -> str:
    """
    Remove recurring consent/login blocks and standalone nav/CTA lines
    that repeat or appear mid-page. Domain-keyed, so it's a no-op for
    sites not yet listed.
    """
    domain = urlparse(link).netloc.lower()

    for known_domain, patterns in REPEATED_BLOCK_PATTERNS.items():
        if known_domain in domain:
            for pattern in patterns:
                text = pattern.sub("", text)

    blocklist = set()
    for known_domain, lines in LINE_BLOCKLIST_BY_DOMAIN.items():
        if known_domain in domain:
            blocklist |= lines

    if blocklist:
        text = "\n".join(
            line for line in text.splitlines() if line.strip() not in blocklist
        )

    # Re-collapse any blank-line runs left behind by the removals
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def trim_trailing_boilerplate(text: str, link: str) -> str:
    """
    Cut off text from the first matching trailing-boilerplate marker
    onward, based on the job link's domain. No-op for domains not yet
    in TRAILING_BOILERPLATE_MARKERS.
    """
    domain = urlparse(link).netloc.lower()

    for known_domain, markers in TRAILING_BOILERPLATE_MARKERS.items():
        if known_domain in domain:
            for marker in markers:
                idx = text.find(marker)
                if idx != -1:
                    text = text[:idx]
            break

    return text.strip()


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
        cleaned_text = strip_repeating_chrome(cleaned_text, link)
        cleaned_text = trim_trailing_boilerplate(cleaned_text, link)

        if not cleaned_text.strip():
            raise RuntimeError("Cleaned text was empty after scraping")

        update_job(job_id, status="scraped", cleaned_text=cleaned_text, error_message=None)
        print(f"Scraped job page for {job_id} ({len(cleaned_text)} chars)")
    except Exception as e:
        update_job(job_id, status="failed", error_message=str(e))
        print(f"Failed to scrape job {job_id}: {e}")


if __name__ == "__main__":
    main()
