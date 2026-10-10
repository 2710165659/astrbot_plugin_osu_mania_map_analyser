"""CPU-only recognition of the fixed Yumu score-card beatmap ID region."""
from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .errors import ManiaMapAnalyserError

FAILURE_TEXT = "未能可靠识别图片中的 bid，请手动发送 /ma <bid>。"
log = logging.getLogger(__name__)


def parse_bid(text: str) -> str | None:
    # Reject substitutions such as O -> 0: guessing can select a real, wrong map.
    text = re.sub(r"\s+", "", text).lower()
    match = re.fullmatch(r"b?([1-9][0-9]{4,9})", text)
    return match.group(1) if match else None


def consensus(results: list[tuple[str, float]], threshold: float) -> str:
    candidates = [parse_bid(text) for text, _ in results]
    if len(results) < 2 or None in candidates or len(set(candidates)) != 1:
        raise ManiaMapAnalyserError(FAILURE_TEXT)
    if any(score < threshold for _, score in results):
        raise ManiaMapAnalyserError(FAILURE_TEXT)
    return candidates[0]


class ImageBidRecognizer:
    def __init__(self, threshold: float = 0.9, debug: bool = False):
        self.threshold = max(0.0, min(float(threshold), 1.0))
        self.debug = debug
        self._engine = None
        self._lock = threading.Lock()

    def _load_engine(self):
        import rapidocr_onnxruntime
        from rapidocr_onnxruntime.ch_ppocr_rec import TextRecognizer
        from rapidocr_onnxruntime.utils import read_yaml

        root = Path(rapidocr_onnxruntime.__file__).parent
        config = read_yaml(str(root / "config.yaml"))["Rec"]
        config.update(model_path=str(root / config["model_path"]),
                      intra_op_num_threads=1, inter_op_num_threads=1,
                      use_cuda=False, use_dml=False)
        return TextRecognizer(config)

    @staticmethod
    def prepare(path: str) -> list[Image.Image]:
        if Path(path).stat().st_size > 15 * 1024 * 1024:
            raise ManiaMapAnalyserError(FAILURE_TEXT)
        with Image.open(path) as source:
            width, height = source.size
            if width * height > 16_000_000 or width < 640 or abs(width / height - 16 / 9) > 0.04:
                raise ManiaMapAnalyserError(FAILURE_TEXT)
            if source.format not in {"JPEG", "PNG", "WEBP"} or getattr(source, "n_frames", 1) != 1:
                raise ManiaMapAnalyserError(FAILURE_TEXT)
            # Canonical 1920x1080: bID occupies approximately x=1225..1355,
            # y=1000..1029, below the title and to the right of the difficulty.
            crop = source.crop((round(width * .638), round(height * .925),
                                round(width * .708), round(height * .954))).convert("RGB")
        crop = crop.resize((crop.width * 3, crop.height * 3), Image.Resampling.LANCZOS)
        gray = ImageOps.grayscale(crop)
        contrast = ImageEnhance.Contrast(gray).enhance(1.7).filter(ImageFilter.SHARPEN)
        return [crop, contrast.convert("RGB")]

    def recognize(self, path: str) -> str:
        # A timed-out request must not accumulate queued ORT work.
        if not self._lock.acquire(blocking=False):
            raise ManiaMapAnalyserError("图片识别任务正在进行，请稍后再试")
        try:
            images = self.prepare(path)
            if self._engine is None:
                self._engine = self._load_engine()
            import numpy as np
            results, elapsed = self._engine([np.asarray(img)[:, :, ::-1].copy() for img in images])
            if self.debug:
                log.debug("Yumu OCR results=%r inference_seconds=%.3f", results, elapsed)
            return consensus(results, self.threshold)
        except ManiaMapAnalyserError:
            raise
        except Exception as exc:
            log.warning("Yumu OCR failed (%s)", type(exc).__name__)
            raise ManiaMapAnalyserError(FAILURE_TEXT) from exc
        finally:
            self._lock.release()
