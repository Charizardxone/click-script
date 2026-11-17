from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from click_script.domain.models import ClickStep, ClickTask, FailurePolicy, IntRange, new_id
from click_script.infrastructure.persistence import TaskRepository


def test_task_round_trip_copies_images(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    cv2.imwrite(str(source), np.full((25, 35, 3), 127, dtype=np.uint8))
    target = TaskRepository.create_target(source, "确认")
    task = ClickTask(
        name="测试任务",
        targets=[target],
        round_delay_ms=IntRange(1500, 4200),
        steps=[
            ClickStep(
                id=new_id(),
                name="点击确认",
                target_image_id=target.id,
                failure_policy=FailurePolicy.RETRY,
                click_all_matches=True,
                infinite_retry=True,
            )
        ],
    )
    project = tmp_path / "project"

    task_file = TaskRepository.save(task, project)
    loaded = TaskRepository.load(task_file)

    assert loaded.name == "测试任务"
    assert loaded.targets[0].name == "确认"
    assert Path(loaded.targets[0].path).is_file()
    assert Path(loaded.targets[0].path).parent == project / "images"
    assert loaded.steps[0].failure_policy == FailurePolicy.RETRY
    assert loaded.steps[0].click_all_matches
    assert loaded.steps[0].infinite_retry
    assert loaded.round_delay_ms == IntRange(1500, 4200)
    loaded.validate()


def test_task_loader_rejects_path_escape(tmp_path: Path) -> None:
    task_file = tmp_path / "task.json"
    task_file.write_text(
        """
        {
          "name": "bad",
          "targets": [{
            "id": "x", "name": "x", "path": "../secret.png",
            "width": 1, "height": 1, "sha256": "x"
          }],
          "steps": []
        }
        """,
        encoding="utf-8",
    )

    try:
        TaskRepository.load(task_file)
    except ValueError as error:
        assert "超出任务目录" in str(error)
    else:
        raise AssertionError("path escape should have been rejected")
