import re
from io import BytesIO
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

STATUS_COL = {"PASS": "#10B981", "FAIL": "#EF4444", "REVIEW REQUIRED": "#F59E0B"}


def _md(text):
    text = re.sub(r"[<>&]", lambda m: {"<": "&lt;", ">": "&gt;", "&": "&amp;"}[m.group()], text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", text)


def build_pdf(rec, upload_dir, processed_dir):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Inspection Report {rec['inspection_code']}")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=colors.HexColor("#0B1120"), fontSize=20, alignment=0)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=colors.HexColor("#3B82F6"), fontSize=12, spaceBefore=10)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=13)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=colors.HexColor("#64748B"))
    S = []
    band = Table([[Paragraph("<font color='white'><b>INDUSTRIAL AI INSPECTOR</b></font>", ss["Normal"]),
                   Paragraph("<font color='#94A3B8'>Intelligent Visual Inspection. Automated Quality Assurance.</font>", ss["Normal"])]],
                 colWidths=[70 * mm, 104 * mm])
    band.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0B1120")), ("PADDING", (0, 0), (-1, -1), 10)]))
    S += [band, Spacer(1, 8), Paragraph("Inspection Report", h1)]
    col = STATUS_COL.get(rec["status"], "#3B82F6")
    meta = [["Inspection ID", rec["inspection_code"], "Date / time (UTC)", rec["created_at"]],
            ["Category", rec["category"].title(), "Model", rec["model_name"]],
            ["Outcome", Paragraph(f"<font color='{col}'><b>{rec['status']}</b></font>", body), "Anomaly score", f"{rec['anomaly_score']:.3f}"],
            ["Severity", rec["severity"], "Defects", str(rec["defect_count"])],
            ["Processing time", f"{rec['processing_time']:.2f} s", "Inspection mode", rec["inspection_mode"]]]
    t = Table(meta, colWidths=[32 * mm, 55 * mm, 32 * mm, 55 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#CBD5E1")), ("FONTSIZE", (0, 0), (-1, -1), 9),
                           ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")), ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F1F5F9")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    S += [t, Paragraph("Inference mode", h2), Paragraph(_md(rec["inference_mode"] or "-"), body), Paragraph("Images", h2)]
    imgs = []
    for title, folder, name in [("Original", upload_dir, rec["original_image"]), ("Anomaly heatmap", processed_dir, rec["heatmap_image"]),
                                ("Defect localization", processed_dir, rec["annotated_image"])]:
        p = Path(folder) / name
        if p.exists():
            imgs.append([Image(str(p), width=56 * mm, height=56 * mm * (rec["height"] or 1) / (rec["width"] or 1)), Paragraph(title, small)])
    if imgs:
        S.append(Table([[i[0] for i in imgs], [i[1] for i in imgs]], colWidths=[58 * mm] * len(imgs)))
    S.append(Paragraph("Detected defects", h2))
    rows = [["#", "Type", "Severity", "Strength", "Box (x, y, w, h)"]] + [
        [str(i), d["defect_type"], d["severity"], f"{d['confidence']:.2f}", f"{d['x']}, {d['y']}, {d['width']}, {d['height']}"]
        for i, d in enumerate(rec["defects"], 1)]
    if len(rows) == 1:
        rows.append(["-", "No localised defects", "-", "-", "-"])
    dt = Table(rows, colWidths=[10 * mm, 55 * mm, 25 * mm, 25 * mm, 55 * mm], repeatRows=1)
    dt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B1120")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#CBD5E1")), ("FONTSIZE", (0, 0), (-1, -1), 8.5)]))
    S += [dt, Paragraph(f"AI inspection summary <font size=8 color='#64748B'>({rec['explanation_source']})</font>", h2)]
    for line in (rec["explanation"] or "").split("\n"):
        if line.strip():
            S.append(Paragraph(_md(line.lstrip("- ").replace("- ", "", 1) if line.startswith("- ") else line), body))
    S += [Spacer(1, 10), Paragraph(
        "Disclaimer: Defect labels, strengths and scores are outputs of an automated demonstration pipeline. 'Strength' is a relative "
        "anomaly measure, not a calibrated probability, and results are not validated model performance. Human verification is required "
        "before any quality-control decision.", small)]
    doc.build(S)
    return buf.getvalue()
