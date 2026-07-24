from __future__ import annotations

import ctypes
import math
import random
import threading
from ctypes import wintypes
from dataclasses import dataclass
from typing import Protocol

from click_script.domain.models import IntRange, NaturalClickProfile, Rect


class ActionCancelled(Exception):
    """Raised when a running mouse action is cancelled."""


class CancelState(Protocol):
    def is_set(self) -> bool: ...

    def wait(self, timeout: float | None = None) -> bool: ...


class PauseState(Protocol):
    def is_set(self) -> bool: ...


class MouseController(Protocol):
    def position(self) -> Point: ...

    def move_to(self, point: Point) -> None: ...

    def mouse_down(self) -> None: ...

    def mouse_up(self) -> None: ...


@dataclass(frozen=True, slots=True)
class Point:
    x: int
    y: int


def sample_click_point(
    bounds: Rect,
    profile: NaturalClickProfile,
    rng: random.Random,
) -> Point:
    bounds.validate("目标")
    left = bounds.left + bounds.width * profile.safe_margin_ratio_x
    right = bounds.right - bounds.width * profile.safe_margin_ratio_x
    top = bounds.top + bounds.height * profile.safe_margin_ratio_y
    bottom = bounds.bottom - bounds.height * profile.safe_margin_ratio_y
    if right - left < 2 or bottom - top < 2:
        raise ValueError("目标过小，无法生成安全点击区域")

    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    sigma_x = bounds.width * profile.click_sigma_ratio_x
    sigma_y = bounds.height * profile.click_sigma_ratio_y
    for _ in range(50):
        x = rng.gauss(center_x, sigma_x)
        y = rng.gauss(center_y, sigma_y)
        if left <= x < right and top <= y < bottom:
            return Point(round(x), round(y))
    return Point(round(center_x), round(center_y))


def sample_wait_ms(
    value: IntRange,
    profile: NaturalClickProfile,
    rng: random.Random,
) -> int:
    """Sample a wait biased to the minimum, with an occasional long-wait mode."""
    value.validate("等待")
    if value.minimum == value.maximum:
        return value.minimum
    unit = rng.random()
    if rng.random() < profile.long_wait_probability:
        ratio = 1 - unit**profile.wait_bias_power
    else:
        ratio = unit**profile.wait_bias_power
    return round(value.minimum + (value.maximum - value.minimum) * ratio)


def bezier_path(
    start: Point,
    end: Point,
    duration_seconds: float,
    profile: NaturalClickProfile,
    rng: random.Random,
) -> list[Point]:
    dx = end.x - start.x
    dy = end.y - start.y
    distance = math.hypot(dx, dy)
    if distance < 1:
        return [end]
    perpendicular_x = -dy / distance
    perpendicular_y = dx / distance
    curve = min(120.0, distance * profile.curve_strength_ratio)
    bend = rng.uniform(-curve, curve)
    control_1 = (
        start.x + dx * 0.30 + perpendicular_x * bend,
        start.y + dy * 0.30 + perpendicular_y * bend,
    )
    control_2 = (
        start.x + dx * 0.70 + perpendicular_x * bend * 0.55,
        start.y + dy * 0.70 + perpendicular_y * bend * 0.55,
    )
    segments = max(2, round(duration_seconds * profile.path_segments_per_second))
    points: list[Point] = []
    for index in range(1, segments + 1):
        t = index / segments
        eased = 1 - (1 - t) ** 3
        one_minus = 1 - eased
        x = (
            one_minus**3 * start.x
            + 3 * one_minus**2 * eased * control_1[0]
            + 3 * one_minus * eased**2 * control_2[0]
            + eased**3 * end.x
        )
        y = (
            one_minus**3 * start.y
            + 3 * one_minus**2 * eased * control_1[1]
            + 3 * one_minus * eased**2 * control_2[1]
            + eased**3 * end.y
        )
        points.append(Point(round(x), round(y)))
    points[-1] = end
    return points


if hasattr(wintypes, "ULONG_PTR"):
    ULONG_PTR = wintypes.ULONG_PTR
else:
    ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class INPUT_UNION(ctypes.Union):
    _fields_ = (("mi", MOUSEINPUT),)


class INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("data", INPUT_UNION))


class WindowsMouseController:
    INPUT_MOUSE = 0
    LEFT_DOWN = 0x0002
    LEFT_UP = 0x0004

    def __init__(self) -> None:
        if not hasattr(ctypes, "windll"):
            raise RuntimeError("鼠标控制仅支持 Windows")
        self._user32 = ctypes.windll.user32

    def position(self) -> Point:
        point = wintypes.POINT()
        if not self._user32.GetCursorPos(ctypes.byref(point)):
            raise OSError("无法获取鼠标位置")
        return Point(point.x, point.y)

    def move_to(self, point: Point) -> None:
        if not self._user32.SetCursorPos(point.x, point.y):
            raise OSError("无法移动鼠标")

    def _send_button(self, flag: int) -> None:
        item = INPUT(
            type=self.INPUT_MOUSE,
            data=INPUT_UNION(
                mi=MOUSEINPUT(
                    dx=0,
                    dy=0,
                    mouseData=0,
                    dwFlags=flag,
                    time=0,
                    dwExtraInfo=0,
                )
            ),
        )
        sent = self._user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(INPUT))
        if sent != 1:
            raise OSError("Windows SendInput 失败")

    def mouse_down(self) -> None:
        self._send_button(self.LEFT_DOWN)

    def mouse_up(self) -> None:
        self._send_button(self.LEFT_UP)


class NaturalMouse:
    def __init__(
        self,
        controller: MouseController,
        profile: NaturalClickProfile,
        *,
        rng: random.Random | None = None,
    ) -> None:
        self.controller = controller
        self.profile = profile
        self.rng = rng or random.Random()

    def click(
        self,
        bounds: Rect,
        cancel: CancelState,
        pause: PauseState,
    ) -> Point:
        target = sample_click_point(bounds, self.profile, self.rng)
        start = self.controller.position()
        distance = math.hypot(target.x - start.x, target.y - start.y)
        speed_factor = self.rng.uniform(
            1 - self.profile.speed_variation_ratio,
            1 + self.profile.speed_variation_ratio,
        )
        move_speed = self.profile.pixels_per_second * speed_factor
        duration_ms = max(
            self.profile.minimum_move_duration_ms,
            min(
                self.profile.maximum_move_duration_ms,
                round(distance / move_speed * 1000),
            ),
        )
        duration_seconds = duration_ms / 1000
        path = bezier_path(start, target, duration_seconds, self.profile, self.rng)
        delay = duration_seconds / max(1, len(path))

        for point in path:
            self._checkpoint(cancel, pause)
            self.controller.move_to(point)
            self._interruptible_sleep(delay, cancel, pause)

        self._interruptible_sleep(
            self.rng.randint(
                self.profile.arrival_pause_ms.minimum,
                self.profile.arrival_pause_ms.maximum,
            )
            / 1000,
            cancel,
            pause,
        )
        self._checkpoint(cancel, pause)
        pressed = False
        try:
            self.controller.mouse_down()
            pressed = True
            self._cancel_only_sleep(
                self.rng.randint(
                    self.profile.press_duration_ms.minimum,
                    self.profile.press_duration_ms.maximum,
                )
                / 1000,
                cancel,
            )
        finally:
            if pressed:
                self.controller.mouse_up()
        return target

    def idle_move(
        self,
        desktop: Rect,
        cancel: CancelState,
        pause: PauseState,
        maximum_duration_seconds: float,
    ) -> float:
        """Move smoothly toward a random point across the virtual desktop."""
        if maximum_duration_seconds < 0.12:
            return 0.0
        start = self.controller.position()
        margin_x = min(self.profile.idle_motion_radius_px, max(0, desktop.width // 3))
        margin_y = min(self.profile.idle_motion_radius_px, max(0, desktop.height // 3))
        desired = Point(
            self.rng.randint(desktop.left + margin_x, desktop.right - margin_x - 1),
            self.rng.randint(desktop.top + margin_y, desktop.bottom - margin_y - 1),
        )
        speed_factor = self.rng.uniform(
            1 - self.profile.speed_variation_ratio,
            1 + self.profile.speed_variation_ratio,
        )
        move_speed = self.profile.pixels_per_second * speed_factor
        dx = desired.x - start.x
        dy = desired.y - start.y
        distance = math.hypot(dx, dy)
        if distance < 3:
            return 0.0
        desired_duration = distance / move_speed
        if desired_duration > maximum_duration_seconds:
            travel_ratio = maximum_duration_seconds / desired_duration
            travel_ratio *= self.rng.uniform(0.80, 0.98)
            end = Point(
                round(start.x + dx * travel_ratio),
                round(start.y + dy * travel_ratio),
            )
        else:
            end = desired
        actual_distance = math.hypot(end.x - start.x, end.y - start.y)
        duration_seconds = max(0.12, actual_distance / move_speed)
        duration_seconds = min(duration_seconds, maximum_duration_seconds)
        end = Point(
            min(desktop.right - 1, max(desktop.left, end.x)),
            min(desktop.bottom - 1, max(desktop.top, end.y)),
        )
        path = bezier_path(start, end, duration_seconds, self.profile, self.rng)
        delay = duration_seconds / max(1, len(path))
        for point in path:
            self._checkpoint(cancel, pause)
            self.controller.move_to(point)
            self._interruptible_sleep(delay, cancel, pause)
        return duration_seconds

    @staticmethod
    def _checkpoint(cancel: CancelState, pause: PauseState) -> None:
        if cancel.is_set():
            raise ActionCancelled
        while pause.is_set():
            if cancel.wait(0.05):
                raise ActionCancelled

    @classmethod
    def _interruptible_sleep(
        cls,
        duration: float,
        cancel: CancelState,
        pause: PauseState,
    ) -> None:
        remaining = duration
        while remaining > 0:
            cls._checkpoint(cancel, pause)
            interval = min(0.02, remaining)
            if cancel.wait(interval):
                raise ActionCancelled
            remaining -= interval

    @staticmethod
    def _cancel_only_sleep(duration: float, cancel: CancelState) -> None:
        remaining = duration
        while remaining > 0:
            interval = min(0.01, remaining)
            if cancel.wait(interval):
                raise ActionCancelled
            remaining -= interval


class NeverPaused(threading.Event):
    """Convenience pause state used by tests and previews."""
