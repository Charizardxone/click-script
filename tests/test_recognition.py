from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from click_script.domain.models import Rect
from click_script.infrastructure.capture import CapturedFrame
from click_script.infrastructure.recognition import TemplateMatcher


def make_pattern() -> np.ndarray:
    image = np.zeros((30, 40, 3), dtype=np.uint8)
    image[2:12, 3:20] = (10, 210, 40)
    image[15:27, 22:37] = (220, 30, 180)
    cv2.line(image, (0, 29), (39, 0), (255, 255, 255), 2)
    return image


def test_template_match_returns_global_coordinates(tmp_path: Path) -> None:
    template = make_pattern()
    template_path = tmp_path / "target.png"
    cv2.imwrite(str(template_path), template)
    screen = np.zeros((200, 300, 3), dtype=np.uint8)
    screen[70:100, 120:160] = template
    frame = CapturedFrame(screen, Rect(-500, 100, 300, 200))

    result = TemplateMatcher().match(frame, str(template_path), 0.95)

    assert result.found
    assert result.confidence > 0.99
    assert result.bounds == Rect(-380, 170, 40, 30)


def test_template_larger_than_frame_is_not_found(tmp_path: Path) -> None:
    template_path = tmp_path / "large.png"
    cv2.imwrite(str(template_path), np.zeros((50, 50, 3), dtype=np.uint8))
    frame = CapturedFrame(np.zeros((20, 20, 3), dtype=np.uint8), Rect(0, 0, 20, 20))

    result = TemplateMatcher().match(frame, str(template_path), 0.8)

    assert not result.found
    assert result.bounds is None


def test_match_all_returns_distinct_global_matches(tmp_path: Path) -> None:
    template = make_pattern()
    template_path = tmp_path / "target.png"
    cv2.imwrite(str(template_path), template)
    screen = np.zeros((180, 280, 3), dtype=np.uint8)
    screen[20:50, 30:70] = template
    screen[100:130, 190:230] = template
    frame = CapturedFrame(screen, Rect(-100, 50, 280, 180))

    results = TemplateMatcher().match_all(frame, str(template_path), 0.95)

    assert len(results) == 2
    assert sorted(
        (result.bounds.left, result.bounds.top, result.bounds.width, result.bounds.height)
        for result in results
        if result.bounds
    ) == [
        (-70, 70, 40, 30),
        (90, 150, 40, 30),
    ]
