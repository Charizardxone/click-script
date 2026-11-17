from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from click_script.domain.models import ClickStep, ClickTask, FailurePolicy, IntRange
from click_script.infrastructure.capture import ScreenCapture
from click_script.infrastructure.mouse import (
    ActionCancelled,
    NaturalMouse,
    WindowsMouseController,
    sample_wait_ms,
)
from click_script.infrastructure.recognition import MatchResult, TemplateMatcher

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StepOutcome:
    success: bool
    message: str


class TaskWorker(QObject):
    status = Signal(str)
    progress = Signal(int, int, int)
    step_state = Signal(str, str)
    log_message = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, task: ClickTask) -> None:
        super().__init__()
        self.task = task
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()
        self._capture = ScreenCapture()
        self._matcher = TemplateMatcher()
        self._rng = random.Random()

    def request_cancel(self) -> None:
        self.cancel_event.set()
        self.pause_event.clear()

    def request_pause(self) -> None:
        self.pause_event.set()
        self.status.emit("已暂停")

    def request_resume(self) -> None:
        self.pause_event.clear()
        self.status.emit("运行中")

    @Slot()
    def run(self) -> None:
        try:
            self.task.validate()
            mouse = NaturalMouse(
                WindowsMouseController(),
                self.task.natural_click,
                rng=self._rng,
            )
            if self.task.startup_countdown_ms:
                self.status.emit("启动倒计时")
                self._wait_range(
                    IntRange(
                        self.task.startup_countdown_ms,
                        self.task.startup_countdown_ms,
                    )
                )
            self.status.emit("运行中")
            self._run_task(mouse)
            self.finished.emit(True, "任务执行完成")
        except ActionCancelled:
            self.finished.emit(False, "任务已停止")
        except Exception as error:
            logger.exception("Task execution failed")
            self.finished.emit(False, f"执行失败：{error}")

    def _run_task(self, mouse: NaturalMouse) -> None:
        enabled_steps = [step for step in self.task.steps if step.enabled]
        target_map = self.task.target_map()
        round_index = 0
        while self.task.repeat_count is None or round_index < self.task.repeat_count:
            round_index += 1
            self.log_message.emit(f"开始第 {round_index} 轮")
            for step_index, step in enumerate(enabled_steps, 1):
                self._checkpoint()
                self.progress.emit(round_index, step_index, len(enabled_steps))
                self.step_state.emit(step.id, "正在执行")
                outcome = self._run_step(step, target_map[step.target_image_id].path, mouse)
                if outcome.success:
                    self.step_state.emit(step.id, "成功")
                    self.log_message.emit(f"{step.name}：{outcome.message}")
                    continue
                self.step_state.emit(step.id, "失败")
                self.log_message.emit(f"{step.name}：{outcome.message}")
                if step.failure_policy != FailurePolicy.SKIP:
                    raise RuntimeError(outcome.message)
            has_next_round = self.task.repeat_count is None or round_index < self.task.repeat_count
            if has_next_round:
                self.status.emit("轮间等待")
                self.log_message.emit("本轮完成，等待后开始下一轮")
                self._wait_range(
                    self.task.round_delay_ms,
                    mouse=mouse,
                    allow_idle_motion=True,
                )
                self.status.emit("运行中")

    def _run_step(
        self,
        step: ClickStep,
        template_path: str,
        mouse: NaturalMouse,
    ) -> StepOutcome:
        attempts = None if step.infinite_retry else (
            1 + (step.retry_count if step.failure_policy == FailurePolicy.RETRY else 0)
        )
        best_confidence = 0.0
        attempt = 0
        while attempts is None or attempt < attempts:
            attempt += 1
            result = self._find_target(step, template_path)
            best_confidence = max(best_confidence, result.confidence)
            if result.found and result.bounds:
                self._wait_range(
                    step.before_click_delay_ms,
                    mouse=mouse,
                    allow_idle_motion=True,
                )
                frame = self._capture.capture(step.search_region)
                refreshed_matches = (
                    self._matcher.match_all(frame, template_path, step.confidence_threshold)
                    if step.click_all_matches
                    else [self._matcher.match(frame, template_path, step.confidence_threshold)]
                )
                refreshed_matches = [
                    match for match in refreshed_matches if match.found and match.bounds is not None
                ]
                if refreshed_matches:
                    best_confidence = max(
                        best_confidence,
                        max(match.confidence for match in refreshed_matches),
                    )
                if not refreshed_matches:
                    self.log_message.emit(f"{step.name}：点击前复核失败，不执行点击")
                    if attempts is None or attempt < attempts:
                        self._wait_range(IntRange(step.retry_delay_ms, step.retry_delay_ms))
                    continue
                clicked: list[str] = []
                for match in refreshed_matches:
                    self._checkpoint()
                    if match.bounds is None:
                        continue
                    point = mouse.click(
                        match.bounds,
                        self.cancel_event,
                        self.pause_event,
                    )
                    clicked.append(f"({point.x}, {point.y})")
                self._wait_range(
                    step.after_click_delay_ms,
                    mouse=mouse,
                    allow_idle_motion=True,
                )
                return StepOutcome(
                    True,
                    (
                        f"找到并点击 {len(refreshed_matches)} 个匹配，"
                        f"最高置信度 {max(item.confidence for item in refreshed_matches):.3f}，"
                        f"位置 {', '.join(clicked)}"
                    ),
                )
            if attempts is None or attempt < attempts:
                self.log_message.emit(f"{step.name}：第 {attempt} 次未找到，准备重试")
                self._wait_range(IntRange(step.retry_delay_ms, step.retry_delay_ms))
        return StepOutcome(
            False,
            f"查找超时，最高置信度 {best_confidence:.3f}",
        )

    def _find_target(self, step: ClickStep, template_path: str) -> MatchResult:
        remaining = step.search_timeout_ms / 1000
        best = MatchResult(False, 0.0, None, 0.0)
        while remaining > 0:
            self._checkpoint()
            started = time.monotonic()
            frame = self._capture.capture(step.search_region)
            result = self._matcher.match(
                frame,
                template_path,
                step.confidence_threshold,
            )
            remaining -= time.monotonic() - started
            if result.confidence > best.confidence:
                best = result
            if result.found:
                return result
            delay = min(step.poll_interval_ms / 1000, max(0.0, remaining))
            self._wait_duration(delay)
            remaining -= delay
        return best

    def _checkpoint(self) -> None:
        if self.cancel_event.is_set():
            raise ActionCancelled
        while self.pause_event.is_set():
            if self.cancel_event.wait(0.05):
                raise ActionCancelled

    def _wait_range(
        self,
        value: IntRange,
        *,
        mouse: NaturalMouse | None = None,
        allow_idle_motion: bool = False,
    ) -> None:
        duration = sample_wait_ms(value, self.task.natural_click, self._rng) / 1000
        if (
            not allow_idle_motion
            or mouse is None
            or duration < 0.35
            or self.task.natural_click.idle_motion_max_count == 0
            or self._rng.random() >= self.task.natural_click.idle_motion_probability
        ):
            self._wait_duration(duration)
            return

        desktop = self._capture.virtual_desktop_bounds()
        move_count = self._rng.randint(
            1,
            self.task.natural_click.idle_motion_max_count,
        )
        remaining = duration
        for _ in range(move_count):
            if remaining < 0.20:
                break
            before_move = min(
                remaining * self._rng.uniform(0.20, 0.45),
                max(0.0, remaining - 0.15),
            )
            self._wait_duration(before_move)
            remaining -= before_move
            move_duration = min(2.5, remaining)
            used = mouse.idle_move(
                desktop,
                self.cancel_event,
                self.pause_event,
                move_duration,
            )
            remaining -= used
        self._wait_duration(max(0.0, remaining))

    def _wait_duration(self, duration: float) -> None:
        remaining = duration
        while remaining > 0:
            self._checkpoint()
            interval = min(0.05, remaining)
            if self.cancel_event.wait(interval):
                raise ActionCancelled
            remaining -= interval
