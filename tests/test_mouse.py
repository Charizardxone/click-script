from __future__ import annotations

import random
import threading

from click_script.domain.models import NaturalClickProfile, Rect
from click_script.infrastructure.mouse import (
    ActionCancelled,
    NaturalMouse,
    Point,
    bezier_path,
    sample_click_point,
    sample_wait_ms,
)


def test_normal_click_points_stay_inside_safe_area() -> None:
    bounds = Rect(100, 200, 200, 100)
    profile = NaturalClickProfile(
        safe_margin_ratio_x=0.2,
        safe_margin_ratio_y=0.2,
    )
    rng = random.Random(42)

    points = [sample_click_point(bounds, profile, rng) for _ in range(1000)]

    assert all(140 <= point.x < 260 for point in points)
    assert all(220 <= point.y < 280 for point in points)
    assert len({(point.x, point.y) for point in points}) > 100


def test_bezier_path_finishes_exactly_at_target() -> None:
    profile = NaturalClickProfile(path_segments_per_second=80)
    target = Point(800, 500)

    points = bezier_path(
        Point(20, 30),
        target,
        duration_seconds=0.5,
        profile=profile,
        rng=random.Random(7),
    )

    assert len(points) == 40
    assert points[-1] == target
    assert len(set(points)) > 20


def test_tiny_target_is_rejected() -> None:
    profile = NaturalClickProfile(
        safe_margin_ratio_x=0.49,
        safe_margin_ratio_y=0.49,
    )

    try:
        sample_click_point(Rect(0, 0, 5, 5), profile, random.Random(1))
    except ValueError as error:
        assert "目标过小" in str(error)
    else:
        raise AssertionError("tiny target should have been rejected")


def test_cancel_after_mouse_down_always_releases_button() -> None:
    cancel = threading.Event()

    class FakeController:
        released = False

        @staticmethod
        def position() -> Point:
            return Point(50, 50)

        @staticmethod
        def move_to(_point: Point) -> None:
            return None

        @staticmethod
        def mouse_down() -> None:
            cancel.set()

        def mouse_up(self) -> None:
            self.released = True

    controller = FakeController()
    profile = NaturalClickProfile(
        minimum_move_duration_ms=1,
        maximum_move_duration_ms=1,
        path_segments_per_second=10,
        arrival_pause_ms=type(NaturalClickProfile().arrival_pause_ms)(0, 0),
        press_duration_ms=type(NaturalClickProfile().press_duration_ms)(10, 10),
    )
    mouse = NaturalMouse(controller, profile, rng=random.Random(3))

    try:
        mouse.click(Rect(40, 40, 20, 20), cancel, threading.Event())
    except ActionCancelled:
        pass
    else:
        raise AssertionError("click should have been cancelled")

    assert controller.released


def test_wait_distribution_is_usually_near_minimum_and_sometimes_long() -> None:
    profile = NaturalClickProfile(
        long_wait_probability=0.10,
        wait_bias_power=6.0,
    )
    rng = random.Random(2026)
    wait_range = type(profile.arrival_pause_ms)(1000, 5000)

    values = [sample_wait_ms(wait_range, profile, rng) for _ in range(10_000)]

    near_minimum = sum(value <= 1800 for value in values)
    near_maximum = sum(value >= 4200 for value in values)
    assert all(1000 <= value <= 5000 for value in values)
    assert near_minimum > 6500
    assert 500 < near_maximum < 1500


def test_idle_move_can_travel_across_the_virtual_desktop(monkeypatch) -> None:
    class RecordingController:
        current = Point(500, 400)
        points: list[Point] = []

        def position(self) -> Point:
            return self.current

        def move_to(self, point: Point) -> None:
            self.current = point
            self.points.append(point)

        @staticmethod
        def mouse_down() -> None:
            return None

        @staticmethod
        def mouse_up() -> None:
            return None

    monkeypatch.setattr(
        NaturalMouse,
        "_interruptible_sleep",
        lambda *_args, **_kwargs: None,
    )
    controller = RecordingController()
    profile = NaturalClickProfile(
        pixels_per_second=1000,
        speed_variation_ratio=0,
        idle_motion_radius_px=24,
    )
    mouse = NaturalMouse(controller, profile, rng=random.Random(17))

    used = mouse.idle_move(
        Rect(0, 0, 1920, 1080),
        threading.Event(),
        threading.Event(),
        maximum_duration_seconds=5,
    )

    assert 0.12 <= used <= 5
    assert controller.points
    assert 24 <= controller.points[-1].x < 1896
    assert 24 <= controller.points[-1].y < 1056
    assert abs(controller.points[-1].x - 500) > 32 or abs(controller.points[-1].y - 400) > 32
