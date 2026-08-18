import argparse
import json
import re
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

TEMPLATE_RESUME = "assets/templates/resume_template.docx"
TEMPLATE_COVER = "assets/templates/cover_letter_template.docx"
BASE_RESUME = "assets/base_resume.json"
OUTPUT_DIR = "output"

COVER_FONT = "Aptos"
COVER_SIZE = 11


def _clear_body(doc: Document) -> None:
    body = doc.element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def _add_hyperlink(paragraph, text: str, url: str, font_name: str = "Aptos", font_size: int = 11) -> None:
    """Add a styled hyperlink (blue, underlined) to a paragraph."""
    part = paragraph.part
    r_id = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    new_run = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")

    # Apply Hyperlink character style (blue + underline)
    rStyle = OxmlElement("w:rStyle")
    rStyle.set(qn("w:val"), "Hyperlink")
    rPr.append(rStyle)

    # Font
    rFonts = OxmlElement("w:rFonts")
    rFonts.set(qn("w:ascii"), font_name)
    rFonts.set(qn("w:hAnsi"), font_name)
    rPr.append(rFonts)

    # Size (half-points)
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(font_size * 2))
    rPr.append(sz)
    szCs = OxmlElement("w:szCs")
    szCs.set(qn("w:val"), str(font_size * 2))
    rPr.append(szCs)

    new_run.append(rPr)
    t = OxmlElement("w:t")
    t.text = text
    new_run.append(t)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)


def _run(paragraph, text: str, bold: bool = False, size: float = 10, font: str | None = None):
    r = paragraph.add_run(text)
    r.bold = bold
    r.font.size = Pt(size)
    if font:
        r.font.name = font
    return r


def _spacing(para, before: float = 0, after: float = 0, line: float = 1.1) -> None:
    pf = para.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    pf.line_spacing = line


def _no_em_dash(text: str) -> str:
    """Replace em dashes with a comma-space as a safety net."""
    return re.sub(r"\s*\u2014\s*", ", ", text)


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
    S = COVER_SIZE
    F = COVER_FONT

    def cp(text="", bold=False, justify=False, before=0, after=8, line=1.0):
        """Add a cover letter paragraph with standard formatting."""
        p = doc.add_paragraph()
        if text:
            r = p.add_run(_no_em_dash(text))
            r.bold = bold
            r.font.size = Pt(S)
            r.font.name = F
        if justify:
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _spacing(p, before=before, after=after, line=line)
        return p

    # --- Header block ---
    p = doc.add_paragraph()
    # Name (bold)
    r = p.add_run(identity["name"])
    r.bold = True
    r.font.size = Pt(S)
    r.font.name = F
    # Location
    r2 = p.add_run("\n" + identity["location"])
    r2.font.size = Pt(S)
    r2.font.name = F
    # Email as mailto hyperlink + phone
    r3 = p.add_run("\n")
    r3.font.size = Pt(S)
    _add_hyperlink(p, identity["email"], "mailto:" + identity["email"], F, S)
    r4 = p.add_run(" | " + identity["mobile"])
    r4.font.size = Pt(S)
    r4.font.name = F
    # LinkedIn on its own line
    r5 = p.add_run("\n")
    r5.font.size = Pt(S)
    _add_hyperlink(p, "LinkedIn", identity["linkedin"], F, S)
    _spacing(p, before=0, after=12, line=1.0)

    # --- Blank line after header ---
    cp()

    # --- Date ---
    cp(today)

    # --- Recipient: company name (not "Hiring Team") ---
    company = cover_letter_json.get("company_name", "")
    hiring_manager = cover_letter_json.get("hiring_manager_name", "")
    if hiring_manager and company:
        recipient = hiring_manager + "\n" + company
    elif company:
        recipient = company
    elif hiring_manager:
        recipient = hiring_manager
    else:
        recipient = ""
    if recipient:
        p = doc.add_paragraph()
        r = p.add_run(recipient)
        r.font.size = Pt(S)
        r.font.name = F
        _spacing(p, after=8, line=1.15)

    # --- Salutation ---
    cp(cover_letter_json["salutation"])

    # --- Space after salutation ---
    cp()

    # --- Body paragraphs (justified, with space after each) ---
    for field in ["opening_paragraph", "body_paragraph_1", "body_paragraph_2", "closing_paragraph"]:
        cp(_no_em_dash(cover_letter_json[field]), justify=True, after=10)

    # --- Space before sign-off ---
    cp()

    # --- Sign-off ---
    cp(cover_letter_json["sign_off"], after=0)

    # --- Name ---
    p = doc.add_paragraph()
    r = p.add_run(identity["name"])
    r.bold = True
    r.font.size = Pt(S)
    r.font.name = F
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
