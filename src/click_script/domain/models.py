from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4


def new_id() -> str:
    return str(uuid4())


class FailurePolicy(StrEnum):
    STOP = "stop"
    SKIP = "skip"
    RETRY = "retry"


class SearchMode(StrEnum):
    FULL_DESKTOP = "full_desktop"
    RECTANGLE = "rectangle"


@dataclass(slots=True)
class IntRange:
    minimum: int
    maximum: int

    def validate(self, name: str) -> None:
        if self.minimum < 0 or self.maximum < self.minimum:
            raise ValueError(f"{name}范围无效")


@dataclass(slots=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def validate(self, name: str = "区域") -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"{name}宽高必须大于 0")

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom


@dataclass(slots=True)
class SearchRegion:
    mode: SearchMode = SearchMode.FULL_DESKTOP
    rect: Rect | None = None

    def validate(self) -> None:
        if self.mode == SearchMode.RECTANGLE:
            if self.rect is None:
                raise ValueError("自定义搜索区域不能为空")
            self.rect.validate("搜索区域")


@dataclass(slots=True)
class TargetImage:
    id: str
    name: str
    path: str
    width: int
    height: int
    sha256: str

    def resolved_path(self) -> Path:
        return Path(self.path)

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("目标图片名称不能为空")
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"目标图片“{self.name}”尺寸无效")
        if not self.resolved_path().is_file():
            raise ValueError(f"目标图片不存在：{self.path}")


@dataclass(slots=True)
class NaturalClickProfile:
    minimum_move_duration_ms: int = 250
    maximum_move_duration_ms: int = 1200
    pixels_per_second: float = 1200.0
    speed_variation_ratio: float = 0.25
    curve_strength_ratio: float = 0.12
    path_segments_per_second: int = 80
    safe_margin_ratio_x: float = 0.20
    safe_margin_ratio_y: float = 0.20
    click_sigma_ratio_x: float = 0.12
    click_sigma_ratio_y: float = 0.12
    long_wait_probability: float = 0.10
    wait_bias_power: float = 6.0
    idle_motion_probability: float = 0.40
    idle_motion_radius_px: int = 32
    idle_motion_max_count: int = 2
    arrival_pause_ms: IntRange = field(default_factory=lambda: IntRange(60, 180))
    press_duration_ms: IntRange = field(default_factory=lambda: IntRange(40, 120))

    def validate(self) -> None:
        if not 0 < self.minimum_move_duration_ms <= self.maximum_move_duration_ms:
            raise ValueError("鼠标移动时长范围无效")
        if self.pixels_per_second <= 0:
            raise ValueError("鼠标移动速度必须大于 0")
        if not 0 <= self.speed_variation_ratio <= 0.8:
            raise ValueError("速度随机幅度必须在 0～0.8 之间")
        if not 0 <= self.curve_strength_ratio <= 0.5:
            raise ValueError("轨迹弯曲强度必须在 0～0.5 之间")
        if not 10 <= self.path_segments_per_second <= 240:
            raise ValueError("轨迹采样率必须在 10～240 之间")
        for value, name in (
            (self.safe_margin_ratio_x, "水平安全边距"),
            (self.safe_margin_ratio_y, "垂直安全边距"),
        ):
            if not 0 <= value < 0.5:
                raise ValueError(f"{name}必须在 0～0.5 之间")
        for value, name in (
            (self.click_sigma_ratio_x, "水平点击标准差"),
            (self.click_sigma_ratio_y, "垂直点击标准差"),
        ):
            if not 0 < value <= 0.5:
                raise ValueError(f"{name}必须在 0～0.5 之间")
        if not 0 <= self.long_wait_probability <= 0.5:
            raise ValueError("长等待概率必须在 0～0.5 之间")
        if not 1 <= self.wait_bias_power <= 10:
            raise ValueError("等待偏向强度必须在 1～10 之间")
        if not 0 <= self.idle_motion_probability <= 1:
            raise ValueError("等待游移概率必须在 0～1 之间")
        if not 0 <= self.idle_motion_radius_px <= 200:
            raise ValueError("等待游移屏幕边距必须在 0～200 像素之间")
        if not 0 <= self.idle_motion_max_count <= 5:
            raise ValueError("等待游移次数必须在 0～5 之间")
        self.arrival_pause_ms.validate("到达停顿")
        self.press_duration_ms.validate("按下时长")


@dataclass(slots=True)
class ClickStep:
    id: str
    name: str
    target_image_id: str
    enabled: bool = True
    confidence_threshold: float = 0.88
    search_timeout_ms: int = 5000
    poll_interval_ms: int = 200
    before_click_delay_ms: IntRange = field(default_factory=lambda: IntRange(80, 220))
    after_click_delay_ms: IntRange = field(default_factory=lambda: IntRange(300, 700))
    failure_policy: FailurePolicy = FailurePolicy.STOP
    retry_count: int = 1
    retry_delay_ms: int = 500
    click_all_matches: bool = False
    infinite_retry: bool = False
    search_region: SearchRegion = field(default_factory=SearchRegion)

    def validate(self, target_ids: set[str]) -> None:
        if not self.name.strip():
            raise ValueError("步骤名称不能为空")
        if self.target_image_id not in target_ids:
            raise ValueError(f"步骤“{self.name}”引用的目标不存在")
        if not 0.7 <= self.confidence_threshold <= 0.99:
            raise ValueError(f"步骤“{self.name}”匹配阈值必须在 0.70～0.99 之间")
        if self.search_timeout_ms <= 0 or self.poll_interval_ms < 20:
            raise ValueError(f"步骤“{self.name}”超时或轮询间隔无效")
        if self.retry_count < 0 or self.retry_delay_ms < 0:
            raise ValueError(f"步骤“{self.name}”重试参数无效")
        self.before_click_delay_ms.validate("点击前等待")
        self.after_click_delay_ms.validate("点击后等待")
        self.search_region.validate()


@dataclass(slots=True)
class ClickTask:
    name: str = "未命名任务"
    id: str = field(default_factory=new_id)
    schema_version: int = 1
    targets: list[TargetImage] = field(default_factory=list)
    steps: list[ClickStep] = field(default_factory=list)
    repeat_count: int | None = 1
    round_delay_ms: IntRange = field(default_factory=lambda: IntRange(1000, 3000))
    startup_countdown_ms: int = 3000
    natural_click: NaturalClickProfile = field(default_factory=NaturalClickProfile)

    def target_map(self) -> dict[str, TargetImage]:
        return {target.id: target for target in self.targets}

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("任务名称不能为空")
        if self.repeat_count is not None and self.repeat_count < 1:
            raise ValueError("循环次数必须大于 0")
        self.round_delay_ms.validate("轮间等待")
        if not 0 <= self.startup_countdown_ms <= 30_000:
            raise ValueError("启动倒计时必须在 0～30 秒之间")
        enabled_steps = [step for step in self.steps if step.enabled]
        if not enabled_steps:
            raise ValueError("至少需要一个已启用步骤")
        target_ids = {target.id for target in self.targets}
        for target in self.targets:
            target.validate()
        for step in enabled_steps:
            step.validate(target_ids)
        self.natural_click.validate()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClickTask:
        natural_data = data.get("natural_click", {})
        natural = NaturalClickProfile(
            **{
                **natural_data,
                "arrival_pause_ms": IntRange(
                    **natural_data.get("arrival_pause_ms", {"minimum": 60, "maximum": 180})
                ),
                "press_duration_ms": IntRange(
                    **natural_data.get("press_duration_ms", {"minimum": 40, "maximum": 120})
                ),
            }
        )
        targets = [TargetImage(**item) for item in data.get("targets", [])]
        steps: list[ClickStep] = []
        for item in data.get("steps", []):
            item = dict(item)
            item["before_click_delay_ms"] = IntRange(**item["before_click_delay_ms"])
            item["after_click_delay_ms"] = IntRange(**item["after_click_delay_ms"])
            item["failure_policy"] = FailurePolicy(item["failure_policy"])
            region_data = item.get("search_region", {})
            rect_data = region_data.get("rect")
            item["search_region"] = SearchRegion(
                mode=SearchMode(region_data.get("mode", SearchMode.FULL_DESKTOP)),
                rect=Rect(**rect_data) if rect_data else None,
            )
            steps.append(ClickStep(**item))
        return cls(
            name=data.get("name", "未命名任务"),
            id=data.get("id", new_id()),
            schema_version=data.get("schema_version", 1),
            targets=targets,
            steps=steps,
            repeat_count=data.get("repeat_count", 1),
            round_delay_ms=IntRange(
                **data.get(
                    "round_delay_ms",
                    {"minimum": 1000, "maximum": 3000},
                )
            ),
            startup_countdown_ms=data.get("startup_countdown_ms", 3000),
            natural_click=natural,
        )
