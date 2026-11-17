"""Procedurally generates local sample images (no downloads, deterministic). Defects are drawn deliberately so the
gallery contains normal/defective pairs; the inspection pipeline then analyses them like any uploaded image."""
import cv2
import numpy as np
from pathlib import Path

S = 512
SAMPLES = {
    "normal_metal": ("Normal metal surface", "metal"), "scratched_metal": ("Scratched metal surface", "metal"),
    "normal_pcb": ("Normal PCB", "pcb"), "defective_pcb": ("Defective PCB (burn, solder blob, cut trace)", "pcb"),
    "normal_fabric": ("Normal fabric", "fabric"), "defective_fabric": ("Fabric with stain & thread defect", "fabric"),
    "normal_wood": ("Normal wood surface", "wood"), "defective_wood": ("Defective wood (crack & hole)", "wood"),
    "normal_bottle": ("Normal bottle (top view)", "bottle"), "defective_bottle": ("Bottle with contamination", "bottle"),
}


def _noise(rng, sigma, amp):
    n = rng.normal(0, 1, (S, S)).astype(np.float32)
    return cv2.GaussianBlur(n, (0, 0), sigma) * amp


def _gray(v):
    return cv2.cvtColor(np.clip(v, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


def metal(rng, defect):
    base = 150 + np.linspace(-12, 12, S)[None, :] + cv2.GaussianBlur(rng.normal(0, 1, (S, S)).astype(np.float32), (0, 0), (0.1), sigmaY=6) * 55
    img = _gray(base + _noise(rng, 1, 3))
    if defect:
        cv2.line(img, (130, 330), (380, 190), (225, 225, 225), 2, cv2.LINE_AA)
        cv2.line(img, (132, 333), (378, 194), (90, 90, 90), 1, cv2.LINE_AA)
    return img


def pcb(rng, defect):
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (60, 110, 20)
    img += rng.normal(0, 2, img.shape)
    img = img.astype(np.uint8)
    for k in range(40, S, 56):
        cv2.line(img, (k, 0), (k, S), (72, 128, 32), 3)
        cv2.line(img, (0, k), (S, k), (72, 128, 32), 3)
    for gx in range(70, S - 40, 112):
        for gy in range(70, S - 40, 112):
            cv2.circle(img, (gx, gy), 7, (70, 150, 170), -1)
    chips = [(100, 100), (300, 100), (100, 300), (300, 300)]
    for i, (cx, cy) in enumerate(chips):
        cv2.rectangle(img, (cx, cy), (cx + 80, cy + 50), (40, 48, 40), -1)
        for p in range(5):
            cv2.line(img, (cx + 10 + p * 15, cy - 6), (cx + 10 + p * 15, cy), (150, 150, 150), 2)
            cv2.line(img, (cx + 10 + p * 15, cy + 50), (cx + 10 + p * 15, cy + 56), (150, 150, 150), 2)
    if defect:
        cv2.circle(img, (440, 90), 18, (30, 60, 110), -1)    # burn mark
        cv2.ellipse(img, (340, 330), (16, 10), 0, 0, 360, (215, 225, 230), -1)   # solder blob on chip
        cv2.rectangle(img, (96, 36), (112, 46), (60, 110, 20), -1)               # cut in a trace
        img = cv2.GaussianBlur(img, (3, 3), 0)
    return img


def fabric(rng, defect):
    y, x = np.mgrid[0:S, 0:S].astype(np.float32)
    v = 135 + 30 * np.sin(x * 0.9) * np.sin(y * 0.9) + _noise(rng, 1, 4)
    img = cv2.merge([v * 0.8, v * 0.95, v * 1.1])
    if defect:
        img = img.astype(np.float32)
        cv2.ellipse(img, (350, 150), (38, 28), 20, 0, 360, (60, 90, 150), -1)
        img = cv2.GaussianBlur(img, (0, 0), 1.2)
        img[300:304, 80:330] *= 0.45
    return np.clip(img, 0, 255).astype(np.uint8)


def wood(rng, defect):
    y, x = np.mgrid[0:S, 0:S].astype(np.float32)
    v = 0.5 + 0.5 * np.sin((y + 18 * np.sin(x / 70.0)) * 0.22) + _noise(rng, 2, 0.08)
    img = cv2.merge([70 + v * 40, 110 + v * 55, 165 + v * 55])
    if defect:
        pts = np.array([[90, 120], [170, 150], [230, 140], [330, 200], [400, 190]], np.int32)
        cv2.polylines(img, [pts], False, (15, 25, 40), 2, cv2.LINE_AA)
        cv2.circle(img, (330, 380), 16, (12, 18, 30), -1)
        img = cv2.GaussianBlur(img, (3, 3), 0)
    return np.clip(img, 0, 255).astype(np.uint8)


def bottle(rng, defect):
    img = np.full((S, S, 3), 38, np.float32)
    y, x = np.mgrid[0:S, 0:S].astype(np.float32)
    r = np.hypot(x - S / 2, y - S / 2)
    ring = np.exp(-((r - 150) ** 2) / (2 * 28 ** 2))
    inner = np.exp(-((r - 90) ** 2) / (2 * 14 ** 2))
    v = 40 + ring * 150 + inner * 60 + _noise(rng, 1.5, 3)
    img = cv2.merge([v * 1.1, v * 1.0, v * 0.9])
    if defect:
        cv2.ellipse(img, (S // 2 + 112, S // 2 - 90), (20, 13), 35, 0, 360, (25, 45, 70), -1)
        img = cv2.GaussianBlur(img, (0, 0), 1.0)
    return np.clip(img, 0, 255).astype(np.uint8)


GEN = {"metal": metal, "pcb": pcb, "fabric": fabric, "wood": wood, "bottle": bottle}


def ensure_samples(sample_dir, dataset_dir=None):
    sample_dir = Path(sample_dir)
    sample_dir.mkdir(parents=True, exist_ok=True)
    for i, (name, (_, cat)) in enumerate(SAMPLES.items()):
        p = sample_dir / f"{name}.png"
        if not p.exists():
            rng = np.random.default_rng(100 + i)
            cv2.imwrite(str(p), GEN[cat](rng, not name.startswith("normal")))
    if dataset_dir:   # normal reference ("golden") images so reference-based detectors work out of the box
        for cat, fn in GEN.items():
            d = Path(dataset_dir) / "reference" / cat
            d.mkdir(parents=True, exist_ok=True)
            for j in range(3):
                p = d / f"ref_{j}.png"
                if not p.exists():
                    cv2.imwrite(str(p), fn(np.random.default_rng(900 + j * 7 + len(cat)), False))
    return [{"key": k, "title": v[0], "category": v[1], "url": f"/static/samples/{k}.png",
             "expected": "normal" if k.startswith("normal") else "defective"} for k, v in SAMPLES.items()]
