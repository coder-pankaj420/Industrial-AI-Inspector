from .base_model import UnavailableDetector
from .classical_model import ClassicalDetector
from .autoencoder_model import AutoencoderDetector
from .patchcore_model import PatchCoreDetector


class ModelManager:
    def __init__(self, dataset_dir, instance_dir):
        why = "Listed for completeness: no defect-localization head is implemented for this backbone in this build"
        self.detectors = {d.key: d for d in [
            ClassicalDetector(),
            AutoencoderDetector(dataset_dir),
            PatchCoreDetector(dataset_dir, instance_dir),
            UnavailableDetector("efficientnet", "EfficientNet", "EfficientNet-B0", "Classification backbone",
                                "Image classification backbone; not wired into the inspection pipeline.", why),
            UnavailableDetector("resnet", "ResNet", "ResNet", "Classification backbone",
                                "Used internally as the PatchCore feature extractor (ResNet18), not as a standalone detector.", why),
            UnavailableDetector("vit", "Vision Transformer", "ViT-B/16", "Classification backbone",
                                "Image classification backbone; not wired into the inspection pipeline.", why),
            UnavailableDetector("clip", "CLIP", "CLIP ViT-B/32", "Image-text similarity",
                                "Zero-shot image-text similarity; not implemented in this build.", why),
        ]}

    def list(self, device="cpu"):
        return [d.info(device) for d in self.detectors.values()]

    def get(self, key):
        d = self.detectors.get(key)
        if d is None:
            raise ValueError(f"Unknown model '{key}'")
        return d

    def usable(self, key):
        return self.get(key).status()["state"] in ("available", "demo")
