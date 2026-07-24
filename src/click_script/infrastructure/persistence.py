from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

import cv2

from click_script.domain.models import ClickTask, TargetImage, new_id


class TaskRepository:
    FILE_NAME = "task.json"

    @staticmethod
    def create_target(source: Path, name: str | None = None) -> TargetImage:
        source = source.resolve()
        image = cv2.imread(str(source), cv2.IMREAD_UNCHANGED)
        if image is None:
            raise ValueError(f"无法读取图片：{source}")
        height, width = image.shape[:2]
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        return TargetImage(
            id=new_id(),
            name=(name or source.stem).strip(),
            path=str(source),
            width=width,
            height=height,
            sha256=digest,
        )

    @classmethod
    def save(cls, task: ClickTask, project_dir: Path) -> Path:
        project_dir = project_dir.resolve()
        images_dir = project_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        for target in task.targets:
            source = Path(target.path).resolve()
            if not source.is_file():
                raise ValueError(f"目标图片不存在：{source}")
            suffix = source.suffix.lower() or ".png"
            destination = images_dir / f"{target.id}{suffix}"
            if source != destination.resolve():
                shutil.copy2(source, destination)
            target.path = str(destination)

        payload = task.to_dict()
        for item in payload["targets"]:
            item["path"] = str(Path("images") / Path(item["path"]).name)

        output = project_dir / cls.FILE_NAME
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=project_dir,
            prefix="task-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary_path = Path(temporary.name)
        temporary_path.replace(output)
        return output

    @classmethod
    def load(cls, task_file: Path) -> ClickTask:
        task_file = task_file.resolve()
        with task_file.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        task = ClickTask.from_dict(data)
        root = task_file.parent
        for target in task.targets:
            candidate = (root / target.path).resolve()
            if root not in candidate.parents and candidate != root:
                raise ValueError("任务图片路径超出任务目录")
            target.path = str(candidate)
        return task
