"""PatchCore-style detector: ResNet18 (layer2+layer3) patch features, memory bank of normal patches, nearest-neighbour distance.
Needs PyTorch/torchvision and normal reference images. Not auto-downloaded."""
import cv2
import numpy as np
from pathlib import Path
from .base_model import BaseDetector

CATEGORY_TO_MVTEC = {"metal": "metal_nut", "fabric": "carpet", "pcb": "transistor", "wood": "wood",
                     "bottle": "bottle", "general": "screw"}   # nearest MVTec AD classes (MVTec has no PCB class)
SIZE = 256


class PatchCoreDetector(BaseDetector):
    key = "patchcore"
    name = "PatchCore-style (ResNet18)"
    architecture = "ResNet18 layer2+layer3 features, kNN memory bank"
    task = "Anomaly detection & localization"
    description = ("Builds a memory bank from normal reference images (datasets/reference/<category>/ or "
                   "datasets/mvtec/<class>/train/good/) and scores test patches by nearest-neighbour distance.")
    capabilities = ["Heatmap", "Localization", "CPU/CUDA", "Needs normal references"]

    def __init__(self, dataset_dir, instance_dir):
        self.ds, self.inst = Path(dataset_dir), Path(instance_dir)
        self._net = None
        self._banks = {}
        self._device = "cpu"

    def _torch_ok(self):
        try:
            import torch, torchvision  # noqa
            return True
        except Exception:
            return False

    def reference_files(self, category):
        dirs = [self.ds / "reference" / category, self.ds / "mvtec" / CATEGORY_TO_MVTEC.get(category, "x") / "train" / "good"]
        for d in dirs:
            if d.is_dir():
                f = sorted([p for p in d.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg")])
                if f:
                    return f[:40]
        return []

    def status(self):
        if not self._torch_ok():
            return {"state": "unavailable", "loaded": False, "reason": "PyTorch/torchvision not installed (pip install torch torchvision)"}
        have = [c for c in CATEGORY_TO_MVTEC if self.reference_files(c)]
        if not have:
            return {"state": "needs_setup", "loaded": False,
                    "reason": "No normal reference images found. Add images to datasets/reference/<category>/ or MVTec AD to datasets/mvtec/"}
        return {"state": "available", "loaded": self._net is not None,
                "reason": f"Reference images found for: {', '.join(have)}"}

    def _load(self, device):
        import torch, torchvision
        dev = "cuda" if device == "cuda" and torch.cuda.is_available() else "cpu"
        if self._net is None or dev != self._device:
            net = torchvision.models.resnet18(weights=torchvision.models.ResNet18_Weights.DEFAULT).eval().to(dev)
            self._net, self._device = net, dev
        return dev

    def _feats(self, bgr):
        import torch
        import torch.nn.functional as F
        rgb = cv2.cvtColor(cv2.resize(bgr, (SIZE, SIZE)), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
        x = (rgb - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
        x = torch.from_numpy(x.astype(np.float32)).permute(2, 0, 1)[None].to(self._device)
        n = self._net
        with torch.no_grad():
            x = n.maxpool(n.relu(n.bn1(n.conv1(x))))
            l2 = n.layer2(n.layer1(x))
            l3 = n.layer3(l2)
            l2, l3 = F.avg_pool2d(l2, 3, 1, 1), F.avg_pool2d(l3, 3, 1, 1)
            l3 = F.interpolate(l3, size=l2.shape[-2:], mode="bilinear", align_corners=False)
            f = torch.cat([l2, l3], 1)[0]
        c, h, w = f.shape
        return f.permute(1, 2, 0).reshape(-1, c), (h, w)

    def _bank(self, category):
        import torch
        if category in self._banks:
            return self._banks[category]
        files = self.reference_files(category)
        if not files:
            raise RuntimeError(f"No normal reference images for category '{category}'")
        imgs = [cv2.imread(str(f)) for f in files]
        imgs = [i for i in imgs if i is not None]
        hold = imgs[-max(1, len(imgs) // 5):] if len(imgs) >= 4 else []
        train = imgs[:len(imgs) - len(hold)] if hold else imgs
        feats = torch.cat([self._feats(i)[0] for i in train])
        if len(feats) > 20000:
            idx = torch.randperm(len(feats), generator=torch.Generator().manual_seed(0))[:20000]
            feats = feats[idx.to(feats.device)]
        mu, sd = 0.0, 1.0
        if hold:   # calibrate distance scale on held-out normal images
            d = torch.cat([torch.cdist(self._feats(i)[0], feats).min(1).values for i in hold])
            mu, sd = float(d.mean()), float(d.std() + 1e-6)
        else:
            d = torch.cdist(feats[:2000], feats).topk(2, largest=False).values[:, 1]
            mu, sd = float(d.mean()), float(d.std() + 1e-6)
        self._banks[category] = (feats, mu, sd, len(train))
        return self._banks[category]

    def anomaly_map(self, bgr, category, device="cpu"):
        if not self._torch_ok():
            raise RuntimeError("PyTorch is not installed")
        import torch
        dev = self._load(device)
        feats, mu, sd, n = self._bank(category)
        q, (h, w) = self._feats(bgr)
        d = torch.cdist(q, feats).min(1).values.reshape(h, w).cpu().numpy()
        z = np.clip((d - mu) / sd, 0, None).astype(np.float32) * 2.5   # scale into shared evidence units
        z = cv2.resize(z, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_CUBIC)
        return cv2.GaussianBlur(z, (0, 0), 4), f"PatchCore-style, ResNet18, {n} reference image(s), {dev}"
