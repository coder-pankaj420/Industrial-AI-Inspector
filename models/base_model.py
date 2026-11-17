"""Common detector interface. Every detector returns a spatial 'evidence' map (robust z-like units)."""
import cv2
import numpy as np

SCORE_K = 14.0   # evidence value at which the 0-1 anomaly score reaches 0.5 (before sensitivity scaling)


def robust_z(x, floor=1.0):
    med = np.median(x)
    mad = np.median(np.abs(x - med)) * 1.4826
    return np.clip((x - med) / max(mad, floor), 0, None).astype(np.float32)


class BaseDetector:
    key = ""
    name = ""
    architecture = ""
    task = ""
    description = ""
    capabilities = []
    demo_only = False

    def status(self):
        """Return {state: available|demo|needs_setup|unavailable, loaded: bool, reason: str}."""
        return {"state": "unavailable", "loaded": False, "reason": "Not implemented"}

    def anomaly_map(self, bgr, category, device="cpu"):
        """Return (evidence_map float32 HxW, mode_label str)."""
        raise NotImplementedError

    def info(self, device="cpu"):
        s = self.status()
        return {"key": self.key, "name": self.name, "architecture": self.architecture, "task": self.task,
                "description": self.description, "capabilities": self.capabilities,
                "device": device if s["loaded"] else "-", **s}


class UnavailableDetector(BaseDetector):
    """Placeholder for backbones listed in the Model Center that have no localization head wired up."""
    def __init__(self, key, name, architecture, task, description, reason):
        self.key, self.name, self.architecture, self.task = key, name, architecture, task
        self.description, self._reason, self.capabilities = description, reason, []

    def status(self):
        return {"state": "unavailable", "loaded": False, "reason": self._reason}

    def anomaly_map(self, bgr, category, device="cpu"):
        raise RuntimeError(self._reason)
