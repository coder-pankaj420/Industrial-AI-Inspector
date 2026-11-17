"""Linear (PCA) patch autoencoder. Reconstruction error of patches = anomaly evidence."""
import cv2
import numpy as np
from pathlib import Path
from numpy.lib.stride_tricks import sliding_window_view
from sklearn.decomposition import PCA
from .base_model import BaseDetector, robust_z

P, STRIDE, WORK = 8, 3, 320


def _patches(img):
    win = sliding_window_view(img, (P, P, 3))[::STRIDE, ::STRIDE, 0]
    return win.reshape(-1, P * P * 3), win.shape[:2]


class AutoencoderDetector(BaseDetector):
    key = "autoencoder"
    name = "PCA Patch Autoencoder"
    architecture = "Linear autoencoder (PCA, 24 components) on 8x8 colour patches"
    task = "Reconstruction-error anomaly detection"
    description = ("Learns the dominant patch structure and flags patches it reconstructs poorly. If reference images exist in "
                   "datasets/reference/<category>/ it is fitted on them; otherwise it is fitted on the test image itself "
                   "(self-supervised, labelled as such).")
    capabilities = ["Heatmap", "Localization", "CPU only", "Optional reference images"]

    def __init__(self, dataset_dir):
        self.ref_dir = Path(dataset_dir) / "reference"
        self._loaded = False

    def status(self):
        return {"state": "available", "loaded": self._loaded, "reason": "scikit-learn PCA; fitted per inspection"}

    def _refs(self, category):
        d = self.ref_dir / category
        files = sorted([f for f in d.glob("*") if f.suffix.lower() in (".png", ".jpg", ".jpeg")])[:12] if d.is_dir() else []
        out = []
        for f in files:
            im = cv2.imread(str(f))
            if im is not None:
                out.append(self._small(im))
        return out

    @staticmethod
    def _small(bgr):
        s = WORK / max(bgr.shape[:2])
        return cv2.resize(bgr, (int(bgr.shape[1] * s), int(bgr.shape[0] * s)), interpolation=cv2.INTER_AREA).astype(np.float32) / 255

    def anomaly_map(self, bgr, category, device="cpu"):
        h, w = bgr.shape[:2]
        small = self._small(bgr)
        X, grid = _patches(small)
        refs = self._refs(category)
        rng = np.random.default_rng(0)
        scale = None
        if len(refs) >= 2:   # calibrate on a held-out normal reference so scores are relative to normal variation
            fit = np.concatenate([_patches(r)[0] for r in refs[1:]])
            cal = _patches(refs[0])[0]
            label = f"PCA autoencoder fitted on {len(refs) - 1} reference image(s), calibrated on 1 held-out normal"
        elif refs:
            fit, cal = _patches(refs[0])[0], None
            label = "PCA autoencoder fitted on 1 reference image (uncalibrated)"
        else:
            fit, cal = X, None
            label = "DEMO: PCA autoencoder fitted on the test image itself (no reference images)"
        if len(fit) > 8000:
            fit = fit[rng.choice(len(fit), 8000, replace=False)]
        pca = PCA(n_components=24, random_state=0).fit(fit)
        rec = lambda A: ((A - pca.inverse_transform(pca.transform(A))) ** 2).mean(1)
        err = rec(X).reshape(grid)
        if cal is not None:
            scale = float(np.percentile(rec(cal), 99.9)) + 1e-6
        self._loaded = True
        m = cv2.resize(err.astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
        if scale is not None:   # 8 = worst normal-reference patch; sqrt compresses the dynamic range
            z = (8.0 * np.sqrt(np.clip(m / max(scale, 2e-4), 0, None))).astype(np.float32)
            z = np.where(z > 8.0, z, z * 0.5).astype(np.float32)
        else:
            z = robust_z(m, floor=float(np.median(m)) * 0.1 + 1e-5)
        return cv2.GaussianBlur(z, (0, 0), 3), label
