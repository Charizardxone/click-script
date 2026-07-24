from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
)

from click_script.domain.models import NaturalClickProfile


class NaturalSettingsDialog(QDialog):
    def __init__(self, profile: NaturalClickProfile, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("自然点击设置")
        self.setMinimumWidth(390)
        self.profile = profile

        form = QFormLayout()
        self.speed = self._double(100, 5000, profile.pixels_per_second, 50)
        self.speed_variation = self._double(0, 0.8, profile.speed_variation_ratio, 0.05, 2)
        self.min_duration = self._integer(50, 5000, profile.minimum_move_duration_ms)
        self.max_duration = self._integer(50, 5000, profile.maximum_move_duration_ms)
        self.curve = self._double(0, 0.5, profile.curve_strength_ratio, 0.01, 2)
        self.margin_x = self._double(0, 0.45, profile.safe_margin_ratio_x, 0.01, 2)
        self.margin_y = self._double(0, 0.45, profile.safe_margin_ratio_y, 0.01, 2)
        self.sigma_x = self._double(0.01, 0.5, profile.click_sigma_ratio_x, 0.01, 2)
        self.sigma_y = self._double(0.01, 0.5, profile.click_sigma_ratio_y, 0.01, 2)
        self.long_wait_probability = self._double(0, 0.5, profile.long_wait_probability, 0.01, 2)
        self.wait_bias_power = self._double(1, 10, profile.wait_bias_power, 0.5, 1)
        self.idle_motion_probability = self._double(0, 1, profile.idle_motion_probability, 0.05, 2)
        self.idle_motion_radius = self._integer(0, 200, profile.idle_motion_radius_px)
        self.idle_motion_count = self._integer(0, 5, profile.idle_motion_max_count)
        self.arrival_min = self._integer(0, 2000, profile.arrival_pause_ms.minimum)
        self.arrival_max = self._integer(0, 2000, profile.arrival_pause_ms.maximum)
        self.press_min = self._integer(1, 1000, profile.press_duration_ms.minimum)
        self.press_max = self._integer(1, 1000, profile.press_duration_ms.maximum)

        form.addRow("移动速度（像素/秒）", self.speed)
        form.addRow("移动速度随机幅度", self.speed_variation)
        form.addRow("最短移动（毫秒）", self.min_duration)
        form.addRow("最长移动（毫秒）", self.max_duration)
        form.addRow("轨迹弯曲强度", self.curve)
        form.addRow("水平安全边距比例", self.margin_x)
        form.addRow("垂直安全边距比例", self.margin_y)
        form.addRow("水平点击标准差比例", self.sigma_x)
        form.addRow("垂直点击标准差比例", self.sigma_y)
        form.addRow("接近最大等待的概率", self.long_wait_probability)
        form.addRow("等待偏向强度", self.wait_bias_power)
        form.addRow("等待期间鼠标游移概率", self.idle_motion_probability)
        form.addRow("全屏游移边缘留白（像素）", self.idle_motion_radius)
        form.addRow("单次等待最多游移次数", self.idle_motion_count)
        form.addRow("到达停顿最小值（毫秒）", self.arrival_min)
        form.addRow("到达停顿最大值（毫秒）", self.arrival_max)
        form.addRow("按下最小值（毫秒）", self.press_min)
        form.addRow("按下最大值（毫秒）", self.press_max)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @staticmethod
    def _integer(minimum: int, maximum: int, value: int) -> QSpinBox:
        control = QSpinBox()
        control.setRange(minimum, maximum)
        control.setValue(value)
        return control

    @staticmethod
    def _double(
        minimum: float,
        maximum: float,
        value: float,
        step: float,
        decimals: int = 1,
    ) -> QDoubleSpinBox:
        control = QDoubleSpinBox()
        control.setRange(minimum, maximum)
        control.setDecimals(decimals)
        control.setSingleStep(step)
        control.setValue(value)
        return control

    def _accept_if_valid(self) -> None:
        updated = NaturalClickProfile(
            minimum_move_duration_ms=self.min_duration.value(),
            maximum_move_duration_ms=self.max_duration.value(),
            pixels_per_second=self.speed.value(),
            speed_variation_ratio=self.speed_variation.value(),
            curve_strength_ratio=self.curve.value(),
            path_segments_per_second=self.profile.path_segments_per_second,
            safe_margin_ratio_x=self.margin_x.value(),
            safe_margin_ratio_y=self.margin_y.value(),
            click_sigma_ratio_x=self.sigma_x.value(),
            click_sigma_ratio_y=self.sigma_y.value(),
            long_wait_probability=self.long_wait_probability.value(),
            wait_bias_power=self.wait_bias_power.value(),
            idle_motion_probability=self.idle_motion_probability.value(),
            idle_motion_radius_px=self.idle_motion_radius.value(),
            idle_motion_max_count=self.idle_motion_count.value(),
            arrival_pause_ms=type(self.profile.arrival_pause_ms)(
                self.arrival_min.value(),
                self.arrival_max.value(),
            ),
            press_duration_ms=type(self.profile.press_duration_ms)(
                self.press_min.value(),
                self.press_max.value(),
            ),
        )
        try:
            updated.validate()
        except ValueError:
            return
        self.profile = updated
        self.accept()
