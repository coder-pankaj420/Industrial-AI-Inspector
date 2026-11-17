import cv2
import numpy as np
from models.base_model import SCORE_K

MAX_SIDE = 640
SEV_RANK = {"None": 0, "Low": 1, "Medium": 2, "High": 3}
SEV_BGR = {"Low": (11, 158, 245), "Medium": (11, 158, 245), "High": (68, 68, 239)}


def decode(data: bytes):
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("File is not a decodable image")
    return img


def preprocess(bgr):
    """Resize to working resolution and apply light denoising. Returns working image."""
    h, w = bgr.shape[:2]
    s = MAX_SIDE / max(h, w)
    if s < 1:
        bgr = cv2.resize(bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    return cv2.GaussianBlur(bgr, (3, 3), 0)


def score_from_map(z, sens, thr):
    """Return (score, region_threshold). z is scaled by sensitivity; score = peak/(peak+K)."""
    zs = z * sens
    peak = float(np.percentile(zs, 99.95))
    score = peak / (peak + SCORE_K)
    review = 0.75 * thr
    tz = SCORE_K * review / (1 - review)
    return score, zs, tz


def heatmap_overlay(bgr, zs, tz):
    top = max(float(zs.max()), tz * 1.5)
    norm = np.clip(zs / top, 0, 1)
    color = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_JET)
    alpha = (np.clip(norm * 1.4, 0, 0.65))[..., None]
    return (bgr * (1 - alpha) + color * alpha).astype(np.uint8)


def _classify(category, frac, aspect, extent, delta, chroma):
    if frac > 0.04:
        return "Structural irregularity"
    if aspect > 3.5:
        if category == "fabric":
            return "Thread irregularity"
        if category == "pcb":
            return "Trace damage"
        return "Scratch" if delta > 0 else "Crack"
    if chroma > 12 and abs(delta) < 35:
        return "Discoloration"
    if category == "pcb" and delta > 20 and aspect < 2.5:
        return "Solder blob / bridge"
    if category == "pcb" and extent > 0.65 and aspect < 2.5:
        return "Missing component"
    if aspect <= 2.2 and delta < -45:
        return "Hole"
    if aspect <= 2.2 and delta < -8:
        return "Contamination"
    if aspect <= 2.2 and category == "metal":
        return "Dent"
    return "Surface abnormality"


def localize(zs, bgr, category, tz):
    h, w = zs.shape
    mask = (zs > tz).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    if mask.mean() / 255 > 0.25:       # evidence everywhere = structure the detector cannot separate; do not draw boxes
        return []
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    out = []
    for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:8]:
        area = cv2.contourArea(c)
        frac = area / (h * w)
        if frac < 0.0004:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        m = np.zeros((h, w), np.uint8)
        cv2.drawContours(m, [c], -1, 255, -1)
        ring = cv2.dilate(m, np.ones((21, 21), np.uint8)) - m
        ins = m > 0
        rg = ring > 0 if ring.any() else ins
        delta = float(gray[ins].mean() - gray[rg].mean())
        chroma = float(np.linalg.norm(lab[ins][:, 1:].mean(0) - lab[rg][:, 1:].mean(0)))
        (_, (rw, rh), _) = cv2.minAreaRect(c)
        aspect = max(rw, rh) / max(min(rw, rh), 1)
        extent = area / max(bw * bh, 1)
        zmax = float(zs[ins].max())
        strength = zmax / (zmax + SCORE_K)
        t = _classify(category, frac, aspect, extent, delta, chroma)
        sev = "High" if (frac > 0.015 or strength > 0.75) else "Medium" if (frac > 0.004 or strength > 0.58) else "Low"
        out.append({"defect_type": t, "severity": sev, "confidence": strength, "x": x, "y": y, "width": bw, "height": bh,
                    "description": f"{t} (heuristic label) covering {frac*100:.2f}% of the frame; "
                                   f"{'brighter' if delta > 0 else 'darker'} than surroundings by {abs(delta):.0f} grey levels."})
    return out


def annotate(bgr, defects):
    img = bgr.copy()
    for i, d in enumerate(defects, 1):
        col = SEV_BGR.get(d["severity"], (11, 158, 245))
        x, y, w, h = d["x"], d["y"], d["width"], d["height"]
        cv2.rectangle(img, (x, y), (x + w, y + h), col, 2)
        label = f"#{i} {d['defect_type']} [{d['severity']}]"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        ty = y - 6 if y - th - 8 > 0 else y + h + th + 6
        cv2.rectangle(img, (x, ty - th - 4), (x + tw + 6, ty + 4), col, -1)
        cv2.putText(img, label, (x + 3, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    return img
