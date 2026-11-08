#!/usr/bin/env python3
"""Build the report and application highlight from their editable Markdown sources."""

import argparse
from functools import partial
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from xml.sax.saxutils import escape, quoteattr

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "report"
sys.path.insert(0, str(ROOT / ".tools/report-packages"))

from PIL import Image as PillowImage
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK = colors.HexColor("#162433")
MUTED = colors.HexColor("#4e6072")
BLUE = colors.HexColor("#154971")
TEAL = colors.HexColor("#0b615f")
RULE = colors.HexColor("#c8d5df")
HIGHLIGHT = colors.HexColor("#eaf5f3")
LIGHT = colors.HexColor("#eef3f8")
WHITE = colors.white
FONTS = Path("/usr/share/fonts/truetype")
TOKEN = re.compile(r"\*\*([^*]+)\*\*|\*([^*]+)\*|\x60([^\x60]+)\x60|\[([^\]]+)\]\(([^)]+)\)")
FIGURE = re.compile(r"!\[([^\]]+)\]\(([^)]+)\)")
PAGE_MARK = "<!-- page -->"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def register_fonts():
    names = {
        "StudySans": "lato/Lato-Regular.ttf",
        "StudySansBold": "lato/Lato-Bold.ttf",
        "StudySansItalic": "lato/Lato-Italic.ttf",
        "StudySansBoldItalic": "lato/Lato-BoldItalic.ttf",
        "StudySerif": "dejavu/DejaVuSerif.ttf",
        "StudySerifBold": "dejavu/DejaVuSerif-Bold.ttf",
        "StudySerifItalic": "dejavu/DejaVuSerif-Italic.ttf",
        "StudySerifBoldItalic": "dejavu/DejaVuSerif-BoldItalic.ttf",
    }
    for name, file in names.items():
        pdfmetrics.registerFont(TTFont(name, str(FONTS / file)))
    for family in ("StudySans", "StudySerif"):
        pdfmetrics.registerFontFamily(family, normal=family, bold=family+"Bold",
                                     italic=family+"Italic", boldItalic=family+"BoldItalic")


def inline(text):
    spans, start = [], 0
    for token in TOKEN.finditer(text):
        spans.append(escape(text[start:token.start()]))
        bold, italics, code, label, uri = token.groups()
        if bold:
            spans.append("<b>" + escape(bold) + "</b>")
        elif italics:
            spans.append("<i>" + escape(italics) + "</i>")
        elif code:
            spans.append("<font name='StudySans'>" + escape(code) + "</font>")
        elif uri.startswith("https://"):
            spans.append(f"<link href={quoteattr(uri)} color='#154971'>{escape(label)}</link>")
        else:
            spans.append(escape(label))
        start = token.end()
    spans.append(escape(text[start:]))
    return "".join(spans)


def styles(highlight):
    accent = TEAL if highlight else BLUE
    body_size, body_lead = (10.65, 15.4) if highlight else (10.05, 13.7)
    return {
        "title": ParagraphStyle("Title", fontName="StudySansBold", fontSize=28.3, leading=31.5,
                                textColor=INK, spaceAfter=7, keepWithNext=True),
        "subtitle": ParagraphStyle("Subtitle", fontName="StudySans", fontSize=13.6, leading=17.2,
                                   textColor=accent, spaceAfter=16, keepWithNext=True),
        "h2": ParagraphStyle("Section", fontName="StudySansBold", fontSize=17.2 if not highlight else 15.0,
                             leading=21.0 if not highlight else 18.8, textColor=accent,
                             spaceBefore=4, spaceAfter=7, keepWithNext=True),
        "h3": ParagraphStyle("Subsection", fontName="StudySansBold", fontSize=10.6, leading=13,
                             textColor=accent, spaceBefore=4, spaceAfter=4, keepWithNext=True),
        "body": ParagraphStyle("Body", fontName="StudySerif", fontSize=body_size, leading=body_lead,
                               textColor=INK, spaceAfter=8 if highlight else 6, allowWidows=0, allowOrphans=0),
        "reference": ParagraphStyle("Reference", fontName="StudySans", fontSize=8.9, leading=11.6,
                                    textColor=MUTED, spaceAfter=4, allowWidows=0, allowOrphans=0),
        "note": ParagraphStyle("Note", fontName="StudySerif", fontSize=10.4 if highlight else 9.9,
                               leading=15.0 if highlight else 13.6, textColor=INK),
        "caption": ParagraphStyle("Caption", fontName="StudySans", fontSize=8.9, leading=11.2,
                                  textColor=MUTED, spaceBefore=3.0, spaceAfter=7),
        "cell": ParagraphStyle("Cell", fontName="StudySans", fontSize=9.0, leading=11.25, textColor=INK),
        "cell_label": ParagraphStyle("CellLabel", fontName="StudySansBold", fontSize=8.9, leading=11.0,
                                     textColor=WHITE),
        "highlight_cell": ParagraphStyle("HighlightCell", fontName="StudySans", fontSize=9.5, leading=12.8,
                                         textColor=INK, alignment=TA_CENTER),
        "highlight_label": ParagraphStyle("HighlightLabel", fontName="StudySansBold", fontSize=11.8,
                                          leading=14.4, textColor=WHITE, alignment=TA_CENTER),
    }


def paragraph(text, style):
    return Paragraph(inline(text), style)


def card(text, width, fmt, highlight):
    table = Table([[paragraph(text, fmt["note"])]], colWidths=[width], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), HIGHLIGHT if highlight else LIGHT),
        ("LINEBEFORE", (0, 0), (0, 0), 2.0, TEAL if highlight else BLUE),
        ("LEFTPADDING", (0, 0), (0, 0), 10),
        ("RIGHTPADDING", (0, 0), (0, 0), 10),
        ("TOPPADDING", (0, 0), (0, 0), 8 if highlight else 5),
        ("BOTTOMPADDING", (0, 0), (0, 0), 8 if highlight else 5),
    ]))
    return [table, Spacer(1, 9 if highlight else 7)]


def data_table(raw, widths, width, fmt, highlight):
    def cells(row):
        return [x.strip() for x in row.strip().strip("|").split("|")]

    values = [cells(raw[0]), *(cells(row) for row in raw[2:])]
    columns = len(values[0])
    if len(raw) < 3 or not all(re.fullmatch(r":?-{3,}:?", x) for x in cells(raw[1])):
        raise ValueError("A Markdown table requires a delimiter row.")
    if any(len(row) != columns for row in values):
        raise ValueError("Inconsistent column count in Markdown table.")
    weights = widths or [1] * columns
    if len(weights) != columns or any(x <= 0 for x in weights):
        raise ValueError("The table weights must match the number of columns.")
    key = "highlight_" if highlight else "cell_"
    header = [paragraph(x, fmt[key + "label"]) for x in values[0]]
    rows = [header, *[[paragraph(x, fmt["highlight_cell" if highlight else "cell"]) for x in row]
                      for row in values[1:]]]
    table = Table(rows, colWidths=[width*w/sum(weights) for w in weights], hAlign="LEFT", repeatRows=1)
    padding = 7 if highlight else 3.1
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TEAL if highlight else BLUE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HIGHLIGHT if highlight else LIGHT, WHITE]),
        ("LINEBELOW", (0, -1), (-1, -1), .55, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), padding),
        ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
    ]))
    return [table, Spacer(1, 11 if highlight else 6)]


def story_from(source, highlight, width):
    fmt = styles(highlight)
    story, images = [], set()
    lines = source.read_text(encoding="utf-8").splitlines()
    table_widths, figure_width = None, None
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        if line == PAGE_MARK:
            story.append(PageBreak())
        elif line.startswith("<!-- table-widths:") and line.endswith("-->"):
            table_widths = [float(w.strip()) for w in line.removeprefix("<!-- table-widths:")[:-3].split(",")]
        elif line.startswith("<!-- figure-width:") and line.endswith("-->"):
            figure_width = float(line.removeprefix("<!-- figure-width:")[:-3])
        elif line.startswith("# "):
            story.append(paragraph(line[2:], fmt["title"]))
        elif line.startswith("## "):
            story.append(paragraph(line[3:], fmt["h2"]))
        elif line.startswith("### "):
            story.append(paragraph(line[4:], fmt["subtitle" if i < 5 else "h3"]))
        elif line.startswith("> "):
            story.extend(card(line[2:], width, fmt, highlight))
        elif line.startswith("|"):
            table_rows = [line]
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                table_rows.append(lines[i])
                i += 1
            story.extend(data_table(table_rows, table_widths, width, fmt, highlight))
            table_widths = None
        elif match := FIGURE.fullmatch(line):
            image = (source.parent / match.group(2)).resolve()
            if not image.is_relative_to(ROOT / "figures") or image.suffix != ".png":
                raise ValueError("Figures must be PNG files within the project's figures directory.")
            images.add(image)
            with PillowImage.open(image) as file:
                px_w, px_h = file.size
            fit = min(width, figure_width or width)
            figure_width = None
            graphic = Image(str(image), width=fit, height=fit * px_h / px_w, hAlign="CENTER")
            if i < len(lines) and lines[i].startswith("*Figure"):
                story.append(KeepTogether([graphic, paragraph(lines[i], fmt["caption"])]))
                i += 1
            else:
                story.append(graphic)
        else:
            style = fmt["reference"] if re.match(r"^\[\d+\] ", line) else fmt["body"]
            story.append(paragraph(line, style))
    if story and isinstance(story[-1], Spacer):
        story.pop()
    return story, images


def draw_furniture(canvas, doc, highlight, page_count):
    width, height = A4
    edge = doc.leftMargin + 6
    accent = TEAL if highlight else BLUE
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(.7)
    canvas.line(edge, height - 44, width - edge, height - 44)
    canvas.line(edge, 37, width - edge, 37)
    canvas.setFont("StudySansBold", 8.0)
    canvas.setFillColor(accent)
    canvas.drawString(edge, height - 33, "RESEARCH HIGHLIGHT" if highlight else "PENDULUM DYNAMICS  /  RESEARCH REPORT")
    canvas.setFont("StudySans", 8.0)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(width - edge, height - 33, "NOVEMBER 2026")
    canvas.drawString(edge, 25, "Independent research project")
    canvas.drawRightString(width - edge, 25, f"{doc.page:02d} / {page_count:02d}")


def build_one(source, target, highlight, marks):
    title = source.read_text(encoding="utf-8").splitlines()[0].removeprefix("# ")
    doc = SimpleDocTemplate(str(target), pagesize=A4, leftMargin=43, rightMargin=43,
                            topMargin=55, bottomMargin=45, invariant=1, title=title,
                            subject="Nonlinear pendulum system identification and formal verification",
                            author="Independent research project")
    content, figures = story_from(source, highlight, doc.width - 12)
    if source.read_text(encoding="utf-8").splitlines().count(PAGE_MARK) + 1 != len(marks):
        raise ValueError(f"Page plan changed in {source.name}.")
    decorate = partial(draw_furniture, highlight=highlight, page_count=len(marks))
    doc.build(content, onFirstPage=decorate, onLaterPages=decorate, canvasmaker=partial(Canvas, invariant=1))
    reader = PdfReader(target)
    texts = [" ".join((p.extract_text() or "").split()) for p in reader.pages]
    if len(texts) != len(marks) or not all(mark.casefold() in txt.casefold() for mark, txt in zip(marks, texts)):
        page_info = [dict(words=len(p.split()), start=p[:135], end=p[-85:]) for p in texts]
        raise RuntimeError(f"Page flow changed in {target.name}: {page_info}")
    if any("\ufffd" in txt or "\u25a0" in txt for txt in texts):
        raise RuntimeError(f"Missing text glyph in {target.name}.")
    return {"pages": len(texts), "page_word_counts": [len(p.split()) for p in texts], "sha256": digest(target),
            "source": source.relative_to(ROOT).as_posix(),
            "images": [path.relative_to(ROOT).as_posix() for path in sorted(figures)]}, figures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPORT / "pdf")
    output = parser.parse_args().output.resolve()
    if not output.is_relative_to(ROOT) or output.exists():
        parser.error("Use a new output directory within this project.")
    (ROOT / ".tmp").mkdir(exist_ok=True)
    register_fonts()
    artifacts = [
        ("research_report", False, ["Abstract.", "noiseless baselines", "noisy identification",
         "why the models failed", "Formal verification", "Discussion and conclusion"]),
        ("research_highlight", True, ["Research question."]),
    ]
    outputs, files = {}, {Path(__file__), ROOT / "requirements-report-lock.txt"}
    with tempfile.TemporaryDirectory(dir=ROOT / ".tmp") as name:
        work = Path(name)
        for stem, highlight, marks in artifacts:
            source = REPORT / (stem + ".md")
            target = work / (stem + ".pdf")
            outputs[target.name], figures = build_one(source, target, highlight, marks)
            files.update({source, *figures})
        receipt = {"status": "built", "packages": {name: metadata.version(name) for name in ("reportlab", "pypdf")},
                   "outputs": outputs,
                   "input_sha256": {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(files)}}
        (work / "build_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        shutil.copytree(work, output)
    print(json.dumps({name: val["pages"] for name, val in outputs.items()}, indent=2))


if __name__ == "__main__":
    main()
