from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import cv2
from pynput import keyboard
from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QAction, QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from click_script.application.runner import TaskWorker
from click_script.domain.models import (
    ClickStep,
    ClickTask,
    FailurePolicy,
    IntRange,
    SearchMode,
    SearchRegion,
    new_id,
)
from click_script.infrastructure.capture import ScreenCapture
from click_script.infrastructure.persistence import TaskRepository
from click_script.infrastructure.recognition import TemplateMatcher
from click_script.ui.overlay import SelectionOverlay
from click_script.ui.settings_dialog import NaturalSettingsDialog


class MainWindow(QMainWindow):
    emergency_stop = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Click Script")
        self.resize(1280, 780)
        self.task = ClickTask()
        self.project_dir: Path | None = None
        self._session_dir = Path(tempfile.mkdtemp(prefix="click-script-"))
        self._dirty = False
        self._loading_form = False
        self._loading_task_form = False
        self._thread: QThread | None = None
        self._worker: TaskWorker | None = None
        self._step_states: dict[str, str] = {}
        self._hotkeys: keyboard.GlobalHotKeys | None = None

        self._build_ui()
        self._apply_modern_theme()
        self._connect_signals()
        self._refresh_all()
        self._start_hotkey_listener()

    def _build_ui(self) -> None:
        toolbar = QToolBar("文件")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for text, handler in (
            ("新建", self.new_task),
            ("打开", self.open_task),
            ("保存", self.save_task),
            ("另存为", self.save_task_as),
        ):
            action = QAction(text, self)
            action.triggered.connect(handler)
            toolbar.addAction(action)
        toolbar.addSeparator()
        natural_action = QAction("自然点击设置", self)
        natural_action.triggered.connect(self.edit_natural_settings)
        toolbar.addAction(natural_action)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_target_panel())
        splitter.addWidget(self._build_steps_panel())
        splitter.addWidget(self._build_properties_panel())
        splitter.setSizes([280, 440, 390])
        root_layout.addWidget(splitter, 1)
        root_layout.addWidget(self._build_run_panel())
        self.setCentralWidget(root)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪")

    def _apply_modern_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f5f7fb; color: #172033; }
            QToolBar { background: #ffffff; border: 0; border-bottom: 1px solid #e5e9f2;
                       spacing: 6px; padding: 8px 12px; }
            QToolButton { border: 0; border-radius: 7px; padding: 7px 12px; }
            QToolButton:hover { background: #eef3ff; color: #315bd6; }
            QGroupBox { background: #ffffff; border: 1px solid #e2e7f0; border-radius: 12px;
                        margin-top: 16px; padding: 16px 12px 12px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 5px;
                               color: #344054; }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QListWidget {
                background: #ffffff; border: 1px solid #d8deea; border-radius: 8px;
                padding: 7px; selection-background-color: #4f7cff;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
            QTextEdit:focus, QListWidget:focus { border: 1px solid #4f7cff; }
            QListWidget::item { border-radius: 7px; padding: 8px; margin: 2px; }
            QListWidget::item:selected { background: #e9efff; color: #315bd6; }
            QPushButton { background: #edf1f7; border: 0; border-radius: 8px;
                          padding: 8px 14px; font-weight: 500; }
            QPushButton:hover { background: #dfe7f5; }
            QPushButton:pressed { background: #d2dced; }
            QPushButton:disabled { color: #98a2b3; background: #f1f3f6; }
            QCheckBox { spacing: 7px; }
            QStatusBar { background: #ffffff; border-top: 1px solid #e5e9f2; }
            QSplitter::handle { background: transparent; width: 8px; }
            """
        )
        self.start_button.setStyleSheet(
            "QPushButton { background:#4f7cff; color:white; font-weight:600; }"
            "QPushButton:hover { background:#3f6de8; }"
            "QPushButton:disabled { background:#b9c7ea; color:#f5f7fb; }"
        )
        self.stop_button.setStyleSheet(
            "QPushButton { background:#fff0f0; color:#d92d20; }"
            "QPushButton:hover { background:#ffe0e0; }"
        )

    def _build_target_panel(self) -> QWidget:
        panel = QGroupBox("目标图片")
        layout = QVBoxLayout(panel)
        self.target_list = QListWidget()
        self.target_list.setIconSize(QSize(72, 48))
        layout.addWidget(self.target_list, 1)

        row = QHBoxLayout()
        self.import_button = QPushButton("导入")
        self.capture_button = QPushButton("截图")
        self.delete_target_button = QPushButton("删除")
        row.addWidget(self.import_button)
        row.addWidget(self.capture_button)
        row.addWidget(self.delete_target_button)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        self.add_step_button = QPushButton("添加为步骤")
        self.test_target_button = QPushButton("测试识别")
        row2.addWidget(self.add_step_button)
        row2.addWidget(self.test_target_button)
        layout.addLayout(row2)
        return panel

    def _build_steps_panel(self) -> QWidget:
        panel = QGroupBox("点击步骤（可拖拽排序）")
        layout = QVBoxLayout(panel)
        self.step_list = QListWidget()
        self.step_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.step_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        layout.addWidget(self.step_list, 1)

        row = QHBoxLayout()
        self.remove_step_button = QPushButton("删除步骤")
        self.move_up_button = QPushButton("上移")
        self.move_down_button = QPushButton("下移")
        row.addWidget(self.remove_step_button)
        row.addStretch()
        row.addWidget(self.move_up_button)
        row.addWidget(self.move_down_button)
        layout.addLayout(row)
        return panel

    def _build_properties_panel(self) -> QWidget:
        panel = QGroupBox("步骤属性")
        form = QFormLayout(panel)

        self.step_enabled = QCheckBox("启用")
        self.step_name = QLineEdit()
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0.70, 0.99)
        self.threshold.setSingleStep(0.01)
        self.threshold.setDecimals(2)
        self.timeout = self._spin(100, 120_000, 100, " ms")
        self.poll_interval = self._spin(20, 5000, 20, " ms")
        self.before_min = self._spin(0, 30_000, 10, " ms")
        self.before_max = self._spin(0, 30_000, 10, " ms")
        self.after_min = self._spin(0, 60_000, 10, " ms")
        self.after_max = self._spin(0, 60_000, 10, " ms")
        self.failure_policy = QComboBox()
        self.failure_policy.addItem("停止任务", FailurePolicy.STOP)
        self.failure_policy.addItem("跳过步骤", FailurePolicy.SKIP)
        self.failure_policy.addItem("重试", FailurePolicy.RETRY)
        self.retry_count = self._spin(0, 20, 1)
        self.retry_delay = self._spin(0, 30_000, 50, " ms")
        self.click_all_matches = QCheckBox("点击画面中的全部匹配")
        self.infinite_retry = QCheckBox("未识别时无限重试")
        self.region_label = QLabel("全屏")
        self.select_region_button = QPushButton("框选搜索区域")
        self.clear_region_button = QPushButton("恢复全屏")
        region_row = QHBoxLayout()
        region_row.addWidget(self.select_region_button)
        region_row.addWidget(self.clear_region_button)

        form.addRow(self.step_enabled)
        form.addRow("名称", self.step_name)
        form.addRow("匹配阈值", self.threshold)
        form.addRow("查找超时", self.timeout)
        form.addRow("轮询间隔", self.poll_interval)
        form.addRow("点击前最小等待", self.before_min)
        form.addRow("点击前最大等待", self.before_max)
        form.addRow("点击后最小等待", self.after_min)
        form.addRow("点击后最大等待", self.after_max)
        form.addRow("失败处理", self.failure_policy)
        form.addRow("重试次数", self.retry_count)
        form.addRow("重试间隔", self.retry_delay)
        form.addRow(self.click_all_matches)
        form.addRow(self.infinite_retry)
        form.addRow("搜索范围", self.region_label)
        form.addRow(region_row)
        return panel

    def _build_run_panel(self) -> QWidget:
        panel = QGroupBox("运行")
        layout = QHBoxLayout(panel)
        self.task_name = QLineEdit()
        self.task_name.setPlaceholderText("任务名称")
        self.repeat_count = self._spin(1, 100_000, 1)
        self.infinite_repeat = QCheckBox("无限循环")
        self.round_delay_min = self._spin(0, 600_000, 100, " ms")
        self.round_delay_max = self._spin(0, 600_000, 100, " ms")
        self.countdown = self._spin(0, 30_000, 500, " ms")
        self.start_button = QPushButton("开始")
        self.pause_button = QPushButton("暂停")
        self.stop_button = QPushButton("停止")
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.run_status = QLabel("就绪")
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(90)

        top = QHBoxLayout()
        top.addWidget(QLabel("任务"))
        top.addWidget(self.task_name, 1)
        top.addWidget(QLabel("循环"))
        top.addWidget(self.repeat_count)
        top.addWidget(self.infinite_repeat)
        top.addWidget(QLabel("轮间"))
        top.addWidget(self.round_delay_min)
        top.addWidget(QLabel("～"))
        top.addWidget(self.round_delay_max)
        top.addWidget(QLabel("倒计时"))
        top.addWidget(self.countdown)
        top.addWidget(self.start_button)
        top.addWidget(self.pause_button)
        top.addWidget(self.stop_button)
        top.addWidget(self.run_status)

        wrapper = QVBoxLayout()
        wrapper.addLayout(top)
        wrapper.addWidget(self.log_view)
        layout.addLayout(wrapper)
        return panel

    @staticmethod
    def _spin(
        minimum: int,
        maximum: int,
        step: int,
        suffix: str = "",
    ) -> QSpinBox:
        control = QSpinBox()
        control.setRange(minimum, maximum)
        control.setSingleStep(step)
        control.setSuffix(suffix)
        return control

    def _connect_signals(self) -> None:
        self.import_button.clicked.connect(self.import_images)
        self.capture_button.clicked.connect(self.capture_target)
        self.delete_target_button.clicked.connect(self.delete_target)
        self.add_step_button.clicked.connect(self.add_selected_target_as_step)
        self.test_target_button.clicked.connect(self.test_target)
        self.remove_step_button.clicked.connect(self.remove_step)
        self.move_up_button.clicked.connect(lambda: self.move_step(-1))
        self.move_down_button.clicked.connect(lambda: self.move_step(1))
        self.step_list.currentItemChanged.connect(self._load_selected_step)
        self.step_list.model().rowsMoved.connect(self._sync_step_order)
        self.select_region_button.clicked.connect(self.select_step_region)
        self.clear_region_button.clicked.connect(self.clear_step_region)
        self.start_button.clicked.connect(self.start_task)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.stop_button.clicked.connect(self.stop_task)
        self.emergency_stop.connect(self.stop_task)
        self.task_name.textEdited.connect(self._update_task_options)
        self.repeat_count.valueChanged.connect(self._update_task_options)
        self.infinite_repeat.toggled.connect(self._update_task_options)
        self.round_delay_min.valueChanged.connect(self._update_task_options)
        self.round_delay_max.valueChanged.connect(self._update_task_options)
        self.countdown.valueChanged.connect(self._update_task_options)

        for control in (
            self.step_enabled,
            self.step_name,
            self.threshold,
            self.timeout,
            self.poll_interval,
            self.before_min,
            self.before_max,
            self.after_min,
            self.after_max,
            self.failure_policy,
            self.retry_count,
            self.retry_delay,
            self.click_all_matches,
            self.infinite_retry,
        ):
            if isinstance(control, QLineEdit):
                control.textEdited.connect(self._update_selected_step)
            elif isinstance(control, QCheckBox):
                control.toggled.connect(self._update_selected_step)
            elif isinstance(control, QComboBox):
                control.currentIndexChanged.connect(self._update_selected_step)
            else:
                control.valueChanged.connect(self._update_selected_step)

    def _selected_target(self):
        item = self.target_list.currentItem()
        if item is None:
            return None
        target_id = item.data(Qt.ItemDataRole.UserRole)
        return self.task.target_map().get(target_id)

    def _selected_step(self) -> ClickStep | None:
        item = self.step_list.currentItem()
        if item is None:
            return None
        step_id = item.data(Qt.ItemDataRole.UserRole)
        return next((step for step in self.task.steps if step.id == step_id), None)

    def _refresh_all(self) -> None:
        self._loading_task_form = True
        self.task_name.setText(self.task.name)
        self.infinite_repeat.setChecked(self.task.repeat_count is None)
        self.repeat_count.setValue(self.task.repeat_count or 1)
        self.repeat_count.setEnabled(self.task.repeat_count is not None)
        self.round_delay_max.setMinimum(0)
        self.round_delay_min.setValue(self.task.round_delay_ms.minimum)
        self.round_delay_max.setMinimum(self.task.round_delay_ms.minimum)
        self.round_delay_max.setValue(self.task.round_delay_ms.maximum)
        self.countdown.setValue(self.task.startup_countdown_ms)
        self._loading_task_form = False
        self._refresh_targets()
        self._refresh_steps()
        self._load_selected_step()
        self._update_title()

    def _refresh_targets(self) -> None:
        selected_id = (
            self.target_list.currentItem().data(Qt.ItemDataRole.UserRole)
            if self.target_list.currentItem()
            else None
        )
        self.target_list.clear()
        for target in self.task.targets:
            item = QListWidgetItem(QIcon(target.path), target.name)
            item.setToolTip(f"{target.width} × {target.height}\n{target.path}")
            item.setData(Qt.ItemDataRole.UserRole, target.id)
            self.target_list.addItem(item)
            if target.id == selected_id:
                self.target_list.setCurrentItem(item)

    def _refresh_steps(self, selected_id: str | None = None) -> None:
        if selected_id is None and self.step_list.currentItem():
            selected_id = self.step_list.currentItem().data(Qt.ItemDataRole.UserRole)
        self.step_list.clear()
        targets = self.task.target_map()
        for index, step in enumerate(self.task.steps, 1):
            target_name = targets.get(step.target_image_id)
            state = self._step_states.get(step.id, "")
            prefix = "✓" if step.enabled else "○"
            suffix = f" · {state}" if state else ""
            target_label = target_name.name if target_name else "缺失"
            item = QListWidgetItem(f"{prefix} {index}. {step.name}  [{target_label}]{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, step.id)
            self.step_list.addItem(item)
            if step.id == selected_id:
                self.step_list.setCurrentItem(item)

    def import_images(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "导入目标图片",
            "",
            "图片 (*.png *.jpg *.jpeg *.bmp)",
        )
        if not paths:
            return
        try:
            for raw_path in paths:
                source = Path(raw_path)
                target = TaskRepository.create_target(source)
                staged = self._session_dir / f"{target.id}{source.suffix.lower()}"
                shutil.copy2(source, staged)
                target.path = str(staged)
                self.task.targets.append(target)
            self._mark_dirty()
            self._refresh_targets()
        except Exception as error:  # noqa: BLE001 - UI error boundary
            self._show_error(str(error))

    def capture_target(self) -> None:
        result = self._select_screen_area(with_image=True)
        if result is None:
            return
        _rect, image = result
        name, accepted = QInputDialog.getText(self, "目标名称", "名称")
        if not accepted or not name.strip():
            return
        output = self._session_dir / f"{new_id()}.png"
        if not cv2.imwrite(str(output), image):
            self._show_error("截图保存失败")
            return
        target = TaskRepository.create_target(output, name)
        renamed = self._session_dir / f"{target.id}.png"
        output.replace(renamed)
        target.path = str(renamed)
        self.task.targets.append(target)
        self._mark_dirty()
        self._refresh_targets()

    def _select_screen_area(self, with_image: bool):
        self.hide()
        QApplication.processEvents()
        try:
            frame = ScreenCapture().capture()
            overlay = SelectionOverlay(frame)
            accepted = overlay.exec()
            if not accepted:
                return None
            rect = overlay.selection_global()
            if rect is None:
                return None
            return (rect, overlay.selection_image()) if with_image else (rect, None)
        finally:
            self.show()
            self.activateWindow()

    def delete_target(self) -> None:
        target = self._selected_target()
        if target is None:
            return
        if any(step.target_image_id == target.id for step in self.task.steps):
            self._show_error("该图片仍被步骤引用，请先删除对应步骤")
            return
        self.task.targets = [item for item in self.task.targets if item.id != target.id]
        self._mark_dirty()
        self._refresh_targets()

    def add_selected_target_as_step(self) -> None:
        target = self._selected_target()
        if target is None:
            self._show_error("请先选择一个目标图片")
            return
        step = ClickStep(
            id=new_id(),
            name=f"点击 {target.name}",
            target_image_id=target.id,
        )
        self.task.steps.append(step)
        self._mark_dirty()
        self._refresh_steps(step.id)

    def remove_step(self) -> None:
        step = self._selected_step()
        if step is None:
            return
        self.task.steps = [item for item in self.task.steps if item.id != step.id]
        self._step_states.pop(step.id, None)
        self._mark_dirty()
        self._refresh_steps()

    def move_step(self, offset: int) -> None:
        row = self.step_list.currentRow()
        destination = row + offset
        if row < 0 or destination < 0 or destination >= self.step_list.count():
            return
        item = self.step_list.takeItem(row)
        self.step_list.insertItem(destination, item)
        self.step_list.setCurrentItem(item)
        self._sync_step_order()

    def _sync_step_order(self, *_args) -> None:
        by_id = {step.id: step for step in self.task.steps}
        ordered = []
        for row in range(self.step_list.count()):
            step_id = self.step_list.item(row).data(Qt.ItemDataRole.UserRole)
            if step_id in by_id:
                ordered.append(by_id[step_id])
        if len(ordered) == len(self.task.steps) and ordered != self.task.steps:
            self.task.steps = ordered
            self._mark_dirty()
            self._refresh_steps(
                self.step_list.currentItem().data(Qt.ItemDataRole.UserRole)
                if self.step_list.currentItem()
                else None
            )

    def _load_selected_step(self, *_args) -> None:
        step = self._selected_step()
        self._loading_form = True
        controls = (
            self.step_enabled,
            self.step_name,
            self.threshold,
            self.timeout,
            self.poll_interval,
            self.before_min,
            self.before_max,
            self.after_min,
            self.after_max,
            self.failure_policy,
            self.retry_count,
            self.retry_delay,
            self.select_region_button,
            self.clear_region_button,
        )
        for control in controls:
            control.setEnabled(step is not None and self._thread is None)
        if step:
            self.step_enabled.setChecked(step.enabled)
            self.step_name.setText(step.name)
            self.threshold.setValue(step.confidence_threshold)
            self.timeout.setValue(step.search_timeout_ms)
            self.poll_interval.setValue(step.poll_interval_ms)
            self.before_min.setValue(step.before_click_delay_ms.minimum)
            self.before_max.setValue(step.before_click_delay_ms.maximum)
            self.after_min.setValue(step.after_click_delay_ms.minimum)
            self.after_max.setValue(step.after_click_delay_ms.maximum)
            index = self.failure_policy.findData(step.failure_policy)
            self.failure_policy.setCurrentIndex(max(0, index))
            self.retry_count.setValue(step.retry_count)
            self.retry_delay.setValue(step.retry_delay_ms)
            self.click_all_matches.setChecked(step.click_all_matches)
            self.infinite_retry.setChecked(step.infinite_retry)
            self._show_region(step.search_region)
        else:
            self.step_name.clear()
            self.region_label.setText("未选择步骤")
        self._loading_form = False

    def _update_selected_step(self, *_args) -> None:
        if self._loading_form:
            return
        step = self._selected_step()
        if step is None:
            return
        step.enabled = self.step_enabled.isChecked()
        step.name = self.step_name.text().strip() or "未命名步骤"
        step.confidence_threshold = self.threshold.value()
        step.search_timeout_ms = self.timeout.value()
        step.poll_interval_ms = self.poll_interval.value()
        step.before_click_delay_ms = IntRange(
            self.before_min.value(), max(self.before_min.value(), self.before_max.value())
        )
        step.after_click_delay_ms = IntRange(
            self.after_min.value(), max(self.after_min.value(), self.after_max.value())
        )
        step.failure_policy = self.failure_policy.currentData()
        step.retry_count = self.retry_count.value()
        step.retry_delay_ms = self.retry_delay.value()
        step.click_all_matches = self.click_all_matches.isChecked()
        step.infinite_retry = self.infinite_retry.isChecked()
        self._mark_dirty()
        self._refresh_steps(step.id)

    def select_step_region(self) -> None:
        step = self._selected_step()
        if step is None:
            return
        result = self._select_screen_area(with_image=False)
        if result is None:
            return
        rect, _image = result
        step.search_region = SearchRegion(SearchMode.RECTANGLE, rect)
        self._show_region(step.search_region)
        self._mark_dirty()

    def clear_step_region(self) -> None:
        step = self._selected_step()
        if step is None:
            return
        step.search_region = SearchRegion()
        self._show_region(step.search_region)
        self._mark_dirty()

    def _show_region(self, region: SearchRegion) -> None:
        if region.mode == SearchMode.RECTANGLE and region.rect:
            rect = region.rect
            self.region_label.setText(f"({rect.left}, {rect.top}) {rect.width} × {rect.height}")
        else:
            self.region_label.setText("全屏")

    def test_target(self) -> None:
        target = self._selected_target()
        if target is None:
            self._show_error("请先选择目标图片")
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            frame = ScreenCapture().capture()
            result = TemplateMatcher().match(frame, target.path, 0.70)
            location = f"({result.bounds.left}, {result.bounds.top})" if result.bounds else "无"
            QMessageBox.information(
                self,
                "识别结果",
                (
                    f"最高置信度：{result.confidence:.3f}\n"
                    f"位置：{location}\n"
                    f"耗时：{result.elapsed_ms:.0f} ms"
                ),
            )
        except Exception as error:  # noqa: BLE001 - UI error boundary
            self._show_error(str(error))
        finally:
            QApplication.restoreOverrideCursor()

    def edit_natural_settings(self) -> None:
        dialog = NaturalSettingsDialog(self.task.natural_click, self)
        if dialog.exec():
            self.task.natural_click = dialog.profile
            self._mark_dirty()

    def _update_task_options(self, *_args) -> None:
        if self._loading_task_form:
            return
        self.task.name = self.task_name.text().strip() or "未命名任务"
        self.task.repeat_count = (
            None if self.infinite_repeat.isChecked() else self.repeat_count.value()
        )
        self.round_delay_max.setMinimum(self.round_delay_min.value())
        self.task.round_delay_ms = IntRange(
            self.round_delay_min.value(),
            self.round_delay_max.value(),
        )
        self.repeat_count.setEnabled(not self.infinite_repeat.isChecked() and self._thread is None)
        self.task.startup_countdown_ms = self.countdown.value()
        self._mark_dirty()

    def start_task(self) -> None:
        self._update_task_options()
        try:
            self.task.validate()
        except Exception as error:  # noqa: BLE001 - validation boundary
            self._show_error(str(error))
            return
        self._step_states.clear()
        self.log_view.clear()
        self._thread = QThread(self)
        self._worker = TaskWorker(self.task)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.status.connect(self.run_status.setText)
        self._worker.progress.connect(self._on_progress)
        self._worker.step_state.connect(self._on_step_state)
        self._worker.log_message.connect(self.log_view.append)
        self._worker.finished.connect(self._on_task_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread_finished)
        self._set_running(True)
        self._thread.start()

    def toggle_pause(self) -> None:
        if self._worker is None:
            return
        if self._worker.pause_event.is_set():
            self._worker.request_resume()
            self.pause_button.setText("暂停")
        else:
            self._worker.request_pause()
            self.pause_button.setText("继续")

    def stop_task(self) -> None:
        if self._worker is not None:
            self.run_status.setText("正在停止")
            self._worker.request_cancel()

    def _on_progress(self, round_index: int, step_index: int, total: int) -> None:
        self.statusBar().showMessage(f"第 {round_index} 轮 · 步骤 {step_index}/{total}")

    def _on_step_state(self, step_id: str, state: str) -> None:
        self._step_states[step_id] = state
        current = (
            self.step_list.currentItem().data(Qt.ItemDataRole.UserRole)
            if self.step_list.currentItem()
            else None
        )
        self._refresh_steps(current)

    def _on_task_finished(self, success: bool, message: str) -> None:
        self.run_status.setText("完成" if success else "已停止/失败")
        self.log_view.append(message)
        self.statusBar().showMessage(message)

    def _thread_finished(self) -> None:
        self._worker = None
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.deleteLater()
        self._set_running(False)

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.pause_button.setEnabled(running)
        self.stop_button.setEnabled(running)
        self.pause_button.setText("暂停")
        for control in (
            self.target_list,
            self.step_list,
            self.import_button,
            self.capture_button,
            self.delete_target_button,
            self.add_step_button,
            self.remove_step_button,
            self.move_up_button,
            self.move_down_button,
            self.task_name,
            self.infinite_repeat,
            self.round_delay_min,
            self.round_delay_max,
            self.countdown,
        ):
            control.setEnabled(not running)
        self.repeat_count.setEnabled(not running and not self.infinite_repeat.isChecked())
        self._load_selected_step()

    def new_task(self) -> None:
        if not self._confirm_discard():
            return
        self.task = ClickTask()
        self.project_dir = None
        self._step_states.clear()
        self._dirty = False
        self._refresh_all()

    def open_task(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "打开任务", "", "Click Script 任务 (task.json);;JSON (*.json)"
        )
        if not path:
            return
        try:
            self.task = TaskRepository.load(Path(path))
            self.project_dir = Path(path).parent
            self._dirty = False
            self._step_states.clear()
            self._refresh_all()
        except Exception as error:  # noqa: BLE001 - file format boundary
            self._show_error(str(error))

    def save_task(self) -> bool:
        if self.project_dir is None:
            return self.save_task_as()
        try:
            TaskRepository.save(self.task, self.project_dir)
            self._dirty = False
            self._update_title()
            self.statusBar().showMessage(f"已保存到 {self.project_dir}")
            return True
        except Exception as error:  # noqa: BLE001 - persistence boundary
            self._show_error(str(error))
            return False

    def save_task_as(self) -> bool:
        path = QFileDialog.getExistingDirectory(self, "选择任务保存目录")
        if not path:
            return False
        self.project_dir = Path(path)
        return self.save_task()

    def _confirm_discard(self) -> bool:
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "未保存更改",
            "当前任务有未保存更改，是否先保存？",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save_task()
        return answer == QMessageBox.StandardButton.Discard

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._update_title()

    def _update_title(self) -> None:
        marker = " *" if self._dirty else ""
        self.setWindowTitle(f"Click Script — {self.task.name}{marker}")

    def _start_hotkey_listener(self) -> None:
        try:
            listener = keyboard.GlobalHotKeys(
                {"<ctrl>+<alt>+<f12>": lambda: self.emergency_stop.emit()}
            )
            listener.start()
            self._hotkeys = listener
            self.statusBar().showMessage("就绪 · 紧急停止 Ctrl+Alt+F12")
        except Exception as error:  # noqa: BLE001 - optional OS hook
            self.statusBar().showMessage(f"全局热键不可用：{error}")

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "错误", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._thread is not None:
            answer = QMessageBox.question(
                self,
                "任务正在运行",
                "停止任务并退出？",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.stop_task()
            self._thread.quit()
            self._thread.wait(2000)
        if not self._confirm_discard():
            event.ignore()
            return
        if self._hotkeys is not None:
            self._hotkeys.stop()
        shutil.rmtree(self._session_dir, ignore_errors=True)
        event.accept()
