from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import cv2
import mss
import numpy as np
from numpy.typing import NDArray

from click_script.domain.models import Rect, SearchMode, SearchRegion


@dataclass(slots=True)
class CapturedFrame:
    image: NDArray[np.uint8]
    bounds: Rect


class ScreenCapture:
    def capture(self, region: SearchRegion | Rect | None = None) -> CapturedFrame:
        with mss.mss() as grabber:
            if region is None:
                monitor = grabber.monitors[0]
            elif isinstance(region, Rect):
                monitor = {
                    "left": region.left,
                    "top": region.top,
                    "width": region.width,
                    "height": region.height,
                }
            elif region.mode == SearchMode.RECTANGLE and region.rect is not None:
                monitor = {
                    "left": region.rect.left,
                    "top": region.rect.top,
                    "width": region.rect.width,
                    "height": region.rect.height,
                }
            else:
                monitor = grabber.monitors[0]
            shot = grabber.grab(monitor)
            bgra = np.asarray(shot, dtype=np.uint8)
            bgr = cast(NDArray[np.uint8], cv2.cvtColor(bgra, cv2.COLOR_BGRA2BGR))
            return CapturedFrame(
                image=bgr.copy(),
                bounds=Rect(shot.left, shot.top, shot.width, shot.height),
            )

    def virtual_desktop_bounds(self) -> Rect:
        with mss.mss() as grabber:
            monitor = grabber.monitors[0]
            return Rect(
                monitor["left"],
                monitor["top"],
                monitor["width"],
                monitor["height"],
            )
