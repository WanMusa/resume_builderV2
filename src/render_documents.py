import argparse
import json
import os
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

TEMPLATE_RESUME = "assets/templates/resume_template.docx"
TEMPLATE_COVER = "assets/templates/cover_letter_template.docx"
BASE_RESUME = "assets/base_resume.json"
OUTPUT_DIR = "output"


def _clear_body(doc: Document) -> None:
    body = doc.element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def _add_hyperlink(paragraph, text: str, url: str) -> None:
    part = paragraph.part
    r_id = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)
    new_run = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = text
    new_run.append(t)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)


def _spacing(para, before: float = 0, after: float = 0, line: float = 1.1) -> None:
    pf = para.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    pf.line_spacing = line


def build_resume(resume_json: dict, base_resume: dict, output_path: str) -> None:
    doc = Document(TEMPLATE_RESUME)
    _clear_body(doc)

    identity = base_resume["identity"]
    fixed = base_resume["fixed_sections"]

    # Name
    p = doc.add_paragraph()
    r = p.add_run(identity["name"])
    r.bold = True
    r.font.size = Pt(18)
    _spacing(p)

    # Contact line: email | phone | location | LinkedIn
    p = doc.add_paragraph()
    r = p.add_run(
        identity["email"]
        + " | M: "
        + identity["mobile"]
        + " | "
        + identity["location"]
        + " | "
    )
    r.font.size = Pt(10)
    _add_hyperlink(p, "LinkedIn", identity["linkedin"])
    _spacing(p)

    # CAREER PROFILE
    p = doc.add_paragraph()
    p.add_run("CAREER PROFILE").bold = True
    _spacing(p, before=12)

    p = doc.add_paragraph()
    r = p.add_run(resume_json["career_profile"])
    r.font.size = Pt(10)
    _spacing(p, before=6)

    # AREAS OF EXPERTISE
    p = doc.add_paragraph()
    p.add_run("AREAS OF EXPERTISE/HIGHLIGHTS").bold = True
    _spacing(p, before=12)

    for area in resume_json["areas_of_expertise"]:
        p = doc.add_paragraph(style="List Paragraph")
        if ":" in area:
            key, rest = area.split(":", 1)
            rb = p.add_run(key + ":")
            rb.bold = True
            rb.font.size = Pt(10)
            rn = p.add_run(rest)
            rn.font.size = Pt(10)
        else:
            rn = p.add_run(area)
            rn.font.size = Pt(10)
        _spacing(p)

    # PROFESSIONAL EXPERIENCE
    p = doc.add_paragraph()
    p.add_run("PROFESSIONAL EXPERIENCE").bold = True
    _spacing(p, before=12)

    for job in resume_json["professional_experience"]:
        p = doc.add_paragraph()
        title_str = job["title"] + " \u2015 " + job["company"]
        period = job.get("period", "")
        r = p.add_run(title_str)
        r.bold = True
        r.font.size = Pt(10)
        if period:
            r2 = p.add_run("\t" + period)
            r2.bold = True
            r2.font.size = Pt(10)
        _spacing(p, before=6)

        if job.get("tailored_summary"):
            p = doc.add_paragraph()
            r = p.add_run(job["tailored_summary"])
            r.font.size = Pt(10)
            _spacing(p)

        achievements = job.get("tailored_achievements", [])
        if achievements:
            p = doc.add_paragraph()
            r = p.add_run("Key Achievements")
            r.bold = True
            r.italic = True
            r.font.size = Pt(10)
            _spacing(p)

            for ach in achievements:
                p = doc.add_paragraph(style="List Paragraph")
                r = p.add_run(ach)
                r.font.size = Pt(10)
                _spacing(p)

    # EDUCATION
    p = doc.add_paragraph()
    p.add_run("EDUCATION").bold = True
    _spacing(p, before=12)

    for edu in fixed.get("education", []):
        p = doc.add_paragraph()
        r = p.add_run(edu["qualification"])
        r.bold = True
        r.font.size = Pt(10)
        suffix = " \u2013 " + edu["institution"]
        if edu.get("period"):
            suffix += "\t" + edu["period"]
        p.add_run(suffix).font.size = Pt(10)
        _spacing(p)
        if edu.get("details"):
            p = doc.add_paragraph()
            p.add_run(edu["details"]).font.size = Pt(10)
            _spacing(p)

    for cert in fixed.get("certifications", []):
        p = doc.add_paragraph()
        r = p.add_run(cert)
        r.bold = True
        r.font.size = Pt(10)
        _spacing(p)

    # REFERENCES
    p = doc.add_paragraph()
    p.add_run("REFERENCES").bold = True
    _spacing(p, before=12)

    p = doc.add_paragraph()
    p.add_run(fixed.get("references", "References available upon request.")).font.size = Pt(10)
    _spacing(p)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    print(f"Resume saved: {output_path}")


def build_cover_letter(cover_letter_json: dict, base_resume: dict, output_path: str) -> None:
    doc = Document(TEMPLATE_COVER)
    _clear_body(doc)

    identity = base_resume["identity"]
    today = date.today().strftime("%d %B %Y").lstrip("0")

    # Header block (name + contact on newlines within one paragraph)
    p = doc.add_paragraph()
    r = p.add_run(identity["name"])
    r.bold = True
    r.font.size = Pt(11)
    p.add_run("\n" + identity["location"]).font.size = Pt(11)
    p.add_run("\n" + identity["email"] + "\xa0| " + identity["mobile"]).font.size = Pt(11)
    p.add_run("\n")
    _add_hyperlink(p, "LinkedIn", identity["linkedin"])
    _spacing(p, line=1.15)

    # Date
    p = doc.add_paragraph()
    p.add_run(today).font.size = Pt(11)
    _spacing(p)

    # Recipient
    hiring_manager = cover_letter_json.get("hiring_manager_name", "")
    company = cover_letter_json.get("company_name", "")
    recipient_line = hiring_manager or "Hiring Team"
    if company:
        recipient_line += "\n" + company
    p = doc.add_paragraph()
    p.add_run(recipient_line).font.size = Pt(11)
    _spacing(p)

    # Empty line
    doc.add_paragraph()

    # Salutation
    p = doc.add_paragraph()
    p.add_run(cover_letter_json["salutation"]).font.size = Pt(11)
    _spacing(p)

    # Body paragraphs
    for field in ["opening_paragraph", "body_paragraph_1", "body_paragraph_2", "closing_paragraph"]:
        p = doc.add_paragraph()
        p.add_run(cover_letter_json[field]).font.size = Pt(11)
        _spacing(p)

    # Empty line before sign-off
    doc.add_paragraph()

    # Sign-off
    p = doc.add_paragraph()
    p.add_run(cover_letter_json["sign_off"]).font.size = Pt(11)
    _spacing(p)

    # Name
    p = doc.add_paragraph()
    r = p.add_run(identity["name"])
    r.bold = True
    r.font.size = Pt(11)
    _spacing(p)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    print(f"Cover letter saved: {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-json", required=True, help="Path to resume JSON file")
    parser.add_argument("--cover-letter-json", required=True, help="Path to cover letter JSON file")
    parser.add_argument("--job-id", required=True, help="Job ID used for output filenames")
    args = parser.parse_args()

    with open(args.resume_json, encoding="utf-8") as f:
        resume_json = json.load(f)
    with open(args.cover_letter_json, encoding="utf-8") as f:
        cover_letter_json = json.load(f)
    with open(BASE_RESUME, encoding="utf-8") as f:
        base_resume = json.load(f)

    build_resume(resume_json, base_resume, f"{OUTPUT_DIR}/{args.job_id}_resume.docx")
    build_cover_letter(cover_letter_json, base_resume, f"{OUTPUT_DIR}/{args.job_id}_cover_letter.docx")


if __name__ == "__main__":
    main()
