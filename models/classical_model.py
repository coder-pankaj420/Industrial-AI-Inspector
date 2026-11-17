import cv2
import numpy as np
from .base_model import BaseDetector, robust_z


class ClassicalDetector(BaseDetector):
    key = "classical"
    name = "Classical CV Anomaly Heuristics"
    architecture = "Lab residual + local-texture statistics"
    task = "Anomaly heatmap & localization (demo)"
    description = ("Deterministic image-processing detector: deviation from the smooth local background in Lab space "
                   "plus local texture variance. No trained weights. Output is a demonstration estimate, not a validated model.")
    capabilities = ["Heatmap", "Localization", "CPU only", "No weights needed"]
    demo_only = True

    def status(self):
        return {"state": "demo", "loaded": True, "reason": "Demo mode - always available, no weights required"}

    def anomaly_map(self, bgr, category, device="cpu"):
        h, w = bgr.shape[:2]
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
        sigma = max(8, min(h, w) // 14)
        maps = []
        for c in range(3):
            ch = lab[..., c]
            res = np.abs(ch - cv2.GaussianBlur(ch, (0, 0), sigma))
            maps.append(robust_z(res, floor=2.0 if c == 0 else 1.5))
        g = lab[..., 0]
        mean, sq = cv2.blur(g, (9, 9)), cv2.blur(g * g, (9, 9))
        std = np.sqrt(np.maximum(sq - mean * mean, 0))
        tex = robust_z(np.abs(std - np.median(std)), floor=1.0)
        m = np.maximum.reduce([maps[0], maps[1] * 0.8, maps[2] * 0.8, tex])
        return cv2.GaussianBlur(m, (0, 0), 3), "DEMO: classical image-processing heuristics (not a trained model)"
