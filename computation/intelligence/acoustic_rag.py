
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

SR = 16000
N_MFCC = 13
MATCH_THRESHOLD = 55.0


def extract_mfcc(audio: np.ndarray, sr: int) -> np.ndarray:
    import librosa
    if audio.ndim > 1:
        audio = audio.mean(axis=-1)
    audio = audio.astype(np.float32)
    if sr != SR:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=SR)
    m = librosa.feature.mfcc(y=audio, sr=SR, n_mfcc=N_MFCC,
                             n_fft=512, hop_length=160)
    m = m.T.astype(np.float64)
    m = m - m.mean(axis=0, keepdims=True)
    return m


def _dtw_distance(a: np.ndarray, b: np.ndarray) -> float:
    from fastdtw import fastdtw
    from scipy.spatial.distance import euclidean
    dist, path = fastdtw(a, b, dist=euclidean)
    return float(dist / max(1, len(path)))


class AcousticRAG:

    def __init__(self, store_dir: str | Path = "database/acoustic_rag"):
        self.store = Path(store_dir)
        self.store.mkdir(parents=True, exist_ok=True)

    def enroll(self, user: str, label: str, audio: np.ndarray, sr: int,
               intent: str | None = None) -> None:
        udir = self.store / user
        udir.mkdir(parents=True, exist_ok=True)
        np.save(udir / f"{label}.npy", extract_mfcc(audio, sr))
        index = self._load_index(user)
        index[label] = {"intent": intent or label}
        (udir / "index.json").write_text(json.dumps(index, indent=2))

    def _load_index(self, user: str) -> dict:
        idx = self.store / user / "index.json"
        return json.loads(idx.read_text()) if idx.exists() else {}

    def _load_templates(self, user: str) -> dict[str, np.ndarray]:
        udir = self.store / user
        if not udir.is_dir():
            return {}
        return {p.stem: np.load(p) for p in udir.glob("*.npy")}

    def match(self, audio: np.ndarray, sr: int, user: str,
              threshold: float = MATCH_THRESHOLD) -> dict:
        templates = self._load_templates(user)
        if not templates:
            return {"label": None, "intent": None, "distance": float("inf"),
                    "matched": False, "ranking": []}

        feat = extract_mfcc(audio, sr)
        index = self._load_index(user)
        scored = sorted(
            ((label, _dtw_distance(feat, tmpl)) for label, tmpl in templates.items()),
            key=lambda x: x[1],
        )
        best_label, best_dist = scored[0]
        matched = best_dist <= threshold
        return {
            "label":    best_label if matched else None,
            "intent":   index.get(best_label, {}).get("intent") if matched else None,
            "distance": round(best_dist, 3),
            "matched":  matched,
            "ranking":  [(l, round(d, 3)) for l, d in scored],
        }

    def users(self) -> list[str]:
        return [p.name for p in self.store.iterdir() if p.is_dir()] if self.store.exists() else []

    def open_set_match(self, audio: np.ndarray, sr: int,
                       threshold: float = MATCH_THRESHOLD) -> dict:
        feat = None
        best = {"user": None, "label": None, "intent": None,
                "distance": float("inf"), "matched": False}
        for user in self.users():
            templates = self._load_templates(user)
            if not templates:
                continue
            if feat is None:
                feat = extract_mfcc(audio, sr)
            index = self._load_index(user)
            for label, tmpl in templates.items():
                d = _dtw_distance(feat, tmpl)
                if d < best["distance"]:
                    best = {"user": user, "label": label,
                            "intent": index.get(label, {}).get("intent", label),
                            "distance": round(d, 3), "matched": d <= threshold}
        return best
