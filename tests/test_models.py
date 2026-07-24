from __future__ import annotations

from click_script.domain.models import ClickStep, ClickTask, TargetImage, new_id


def test_task_requires_enabled_step() -> None:
    task = ClickTask()

    try:
        task.validate()
    except ValueError as error:
        assert "至少需要" in str(error)
    else:
        raise AssertionError("empty task should have been rejected")


def test_step_threshold_is_validated(tmp_path) -> None:
    image = tmp_path / "target.png"
    image.write_bytes(b"placeholder")
    target = TargetImage("target", "目标", str(image), 10, 10, "hash")
    step = ClickStep(new_id(), "步骤", target.id, confidence_threshold=0.5)
    task = ClickTask(targets=[target], steps=[step])

    try:
        task.validate()
    except ValueError as error:
        assert "匹配阈值" in str(error)
    else:
        raise AssertionError("invalid threshold should have been rejected")


def test_old_task_without_round_delay_uses_default() -> None:
    task = ClickTask.from_dict({"name": "旧任务"})

    assert task.round_delay_ms.minimum == 1000
    assert task.round_delay_ms.maximum == 3000
