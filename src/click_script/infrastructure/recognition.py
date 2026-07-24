from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from click_script.domain.models import Rect
from click_script.infrastructure.capture import CapturedFrame


@dataclass(slots=True)
class MatchResult:
    found: bool
    confidence: float
    bounds: Rect | None
    elapsed_ms: float


class TemplateMatcher:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[int, NDArray[np.uint8]]] = {}

    def load_template(self, path: str) -> NDArray[np.uint8]:
        source = Path(path)
        stamp = source.stat().st_mtime_ns
        cached = self._cache.get(str(source))
        if cached and cached[0] == stamp:
            return cached[1]
        template = cast(
            NDArray[np.uint8] | None,
            cv2.imread(str(source), cv2.IMREAD_COLOR),
        )
        if template is None:
            raise ValueError(f"无法读取模板图片：{source}")
        self._cache[str(source)] = (stamp, template)
        return template

    def match(
        self,
        frame: CapturedFrame,
        template_path: str,
        threshold: float,
    ) -> MatchResult:
        started = perf_counter()
        template = self.load_template(template_path)
        image_height, image_width = frame.image.shape[:2]
        template_height, template_width = template.shape[:2]
        if template_width > image_width or template_height > image_height:
            return MatchResult(False, 0.0, None, (perf_counter() - started) * 1000)

        result = cv2.matchTemplate(frame.image, template, cv2.TM_CCOEFF_NORMED)
        _min_value, max_value, _min_location, max_location = cv2.minMaxLoc(result)
        bounds = Rect(
            left=frame.bounds.left + max_location[0],
            top=frame.bounds.top + max_location[1],
            width=template_width,
            height=template_height,
        )
        elapsed = (perf_counter() - started) * 1000
        return MatchResult(max_value >= threshold, float(max_value), bounds, elapsed)
