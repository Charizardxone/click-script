from __future__ import annotations

from typing import cast

from click_script.application.runner import StepOutcome, TaskWorker
from click_script.domain.models import (
    ClickStep,
    ClickTask,
    IntRange,
    TargetImage,
    new_id,
)
from click_script.infrastructure.mouse import NaturalMouse


class RecordingWorker(TaskWorker):
    def __init__(self, task: ClickTask) -> None:
        super().__init__(task)
        self.step_runs = 0
        self.round_waits: list[IntRange] = []

    def _run_step(self, *_args) -> StepOutcome:
        self.step_runs += 1
        return StepOutcome(True, "ok")

    def _wait_range(self, value: IntRange, **_kwargs) -> None:
        self.round_waits.append(value)


def make_task(repeat_count: int) -> ClickTask:
    target = TargetImage("target", "目标", "unused.png", 10, 10, "hash")
    step = ClickStep(new_id(), "点击目标", target.id)
    return ClickTask(
        targets=[target],
        steps=[step],
        repeat_count=repeat_count,
        round_delay_ms=IntRange(1200, 4500),
    )


def test_round_delay_runs_only_between_rounds() -> None:
    worker = RecordingWorker(make_task(3))

    worker._run_task(cast(NaturalMouse, object()))

    assert worker.step_runs == 3
    assert worker.round_waits == [IntRange(1200, 4500), IntRange(1200, 4500)]


def test_single_round_has_no_round_delay() -> None:
    worker = RecordingWorker(make_task(1))

    worker._run_task(cast(NaturalMouse, object()))

    assert worker.step_runs == 1
    assert worker.round_waits == []
