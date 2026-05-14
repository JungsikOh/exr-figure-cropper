from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from .exr_io import export_crop, read_exr, save_reference_overlay
from .processing import Region, rgb_from_channels, tonemap_rgb
from .styles import APP_STYLESHEET, COLOR_DIALOG_STYLESHEET


DEFAULT_BOX_COLOR = QtGui.QColor(255, 210, 80)
DEFAULT_LINE_WIDTH = 3


@dataclass
class CropBox:
    region: Region
    color: QtGui.QColor
    line_width: int = DEFAULT_LINE_WIDTH

    def color_tuple(self) -> tuple[int, int, int]:
        return (self.color.red(), self.color.green(), self.color.blue())


def qimage_from_rgb8(rgb: np.ndarray) -> QtGui.QImage:
    rgb = np.ascontiguousarray(rgb, dtype=np.uint8)
    height, width, _ = rgb.shape
    bytes_per_line = width * 3
    return QtGui.QImage(
        rgb.data,
        width,
        height,
        bytes_per_line,
        QtGui.QImage.Format.Format_RGB888,
    ).copy()


class ImageSelector(QtWidgets.QWidget):
    region_changed = QtCore.Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._image: QtGui.QImage | None = None
        self._boxes: list[CropBox] = []
        self._active_index = -1
        self._drag_anchor: tuple[int, int] | None = None
        self.setMinimumSize(640, 480)
        self.setMouseTracking(True)

    def set_image(self, image: QtGui.QImage | None) -> None:
        self._image = image
        self._drag_anchor = None
        self.update()

    def set_boxes(self, boxes: list[CropBox], active_index: int) -> None:
        self._boxes = [
            CropBox(box.region, QtGui.QColor(box.color), box.line_width) for box in boxes
        ]
        self._active_index = active_index
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor(18, 20, 24))

        if self._image is None:
            painter.setPen(QtGui.QColor(150, 157, 168))
            painter.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, "No EXR loaded")
            return

        image_rect = self._display_rect()
        painter.drawImage(image_rect, self._image)
        painter.setPen(QtGui.QPen(QtGui.QColor(62, 70, 82), 1))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRect(image_rect)

        for index, box in enumerate(self._boxes):
            self._paint_box(painter, index, box)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.MouseButton.LeftButton or self._image is None:
            return
        point = self._widget_to_image(event.position(), clamp=False)
        if point is None:
            return
        self._drag_anchor = point
        self._emit_drag_region(point)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_anchor is None:
            return
        point = self._widget_to_image(event.position(), clamp=True)
        if point is not None:
            self._emit_drag_region(point)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_anchor = None

    def _paint_box(self, painter: QtGui.QPainter, index: int, box: CropBox) -> None:
        selection = self._region_to_widget_rect(box.region)
        active = index == self._active_index

        pen_color = QtGui.QColor(box.color)
        if not active:
            pen_color.setAlpha(170)
        painter.setPen(QtGui.QPen(pen_color, max(1, int(box.line_width))))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRect(selection)

        label = f"r{index + 1:02d}"
        metrics = painter.fontMetrics()
        label_width = metrics.horizontalAdvance(label) + 12
        label_height = metrics.height() + 6
        image_rect = self._display_rect()
        label_x = min(max(selection.left(), image_rect.left()), image_rect.right() - label_width)
        label_y = selection.top() - label_height - 4
        if label_y < image_rect.top():
            label_y = selection.bottom() + 4
        if label_y + label_height > image_rect.bottom():
            label_y = max(image_rect.top(), image_rect.bottom() - label_height)
        label_rect = QtCore.QRectF(
            label_x,
            label_y,
            label_width,
            label_height,
        )
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        label_bg = QtGui.QColor(20, 22, 25, 210)
        painter.setBrush(label_bg)
        painter.drawRoundedRect(label_rect, 4, 4)
        painter.setPen(QtGui.QPen(pen_color, 1))
        painter.drawText(label_rect, QtCore.Qt.AlignmentFlag.AlignCenter, label)

    def _emit_drag_region(self, point: tuple[int, int]) -> None:
        if self._drag_anchor is None:
            return
        x0, y0 = self._drag_anchor
        x1, y1 = point
        region = Region(
            min(x0, x1),
            min(y0, y1),
            abs(x1 - x0) + 1,
            abs(y1 - y0) + 1,
        )
        self.region_changed.emit(region)

    def _display_rect(self) -> QtCore.QRectF:
        if self._image is None:
            return QtCore.QRectF()
        image_width = self._image.width()
        image_height = self._image.height()
        scale = min(self.width() / image_width, self.height() / image_height)
        width = image_width * scale
        height = image_height * scale
        x = (self.width() - width) / 2.0
        y = (self.height() - height) / 2.0
        return QtCore.QRectF(x, y, width, height)

    def _widget_to_image(
        self,
        position: QtCore.QPointF,
        clamp: bool,
    ) -> tuple[int, int] | None:
        if self._image is None:
            return None
        rect = self._display_rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return None
        if not clamp and not rect.contains(position):
            return None

        rel_x = (position.x() - rect.left()) / rect.width()
        rel_y = (position.y() - rect.top()) / rect.height()
        if clamp:
            rel_x = min(max(rel_x, 0.0), 1.0)
            rel_y = min(max(rel_y, 0.0), 1.0)

        image_x = min(max(int(rel_x * self._image.width()), 0), self._image.width() - 1)
        image_y = min(max(int(rel_y * self._image.height()), 0), self._image.height() - 1)
        return image_x, image_y

    def _region_to_widget_rect(self, region: Region) -> QtCore.QRectF:
        if self._image is None:
            return QtCore.QRectF()
        rect = self._display_rect()
        scale_x = rect.width() / self._image.width()
        scale_y = rect.height() / self._image.height()
        return QtCore.QRectF(
            rect.left() + region.x * scale_x,
            rect.top() + region.y * scale_y,
            region.width * scale_x,
            region.height * scale_y,
        )


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("EXR Cropper")
        self.resize(1220, 780)

        self.files: list[Path] = []
        self.ref_file: Path | None = None
        self.output_dir: Path | None = None
        self.current_size: tuple[int, int] | None = None
        self.crop_boxes: list[CropBox] = []
        self.active_box_index = -1
        self._syncing_box_ui = False

        self.file_list = self._list_widget(minimum_height=240)
        self.file_list.currentRowChanged.connect(self.load_current_preview)

        self.add_button = self._button("Add EXR", "SP_DialogOpenButton")
        self.add_button.clicked.connect(self.add_files)
        self.remove_button = self._button("Remove")
        self.remove_button.clicked.connect(self.remove_selected)
        self.set_ref_button = self._button("Set Ref")
        self.set_ref_button.clicked.connect(self.set_selected_ref)
        self.ref_label = self._path_label("Ref: none")

        self.output_button = self._button("Output Folder")
        self.output_button.clicked.connect(self.choose_output_dir)
        self.output_label = self._path_label("No output folder")

        self.box_list = self._list_widget(minimum_height=120)
        self.box_list.currentRowChanged.connect(self.select_box)
        self.add_box_button = self._button("Add Box", "SP_FileDialogNewFolder")
        self.add_box_button.clicked.connect(self.add_box)
        self.remove_box_button = self._button("Remove Box")
        self.remove_box_button.clicked.connect(self.remove_box)
        self.color_button = self._button("Box Color")
        self.color_button.clicked.connect(self.choose_box_color)

        self.x_spin = self._make_spinbox()
        self.y_spin = self._make_spinbox()
        self.w_spin = self._make_spinbox()
        self.h_spin = self._make_spinbox()
        self.line_width_spin = QtWidgets.QSpinBox()
        self.line_width_spin.setRange(1, 32)
        self.line_width_spin.setValue(DEFAULT_LINE_WIDTH)
        self.line_width_spin.setMinimumHeight(30)
        for spin in (self.x_spin, self.y_spin, self.w_spin, self.h_spin):
            spin.valueChanged.connect(self.controls_to_box)
        self.line_width_spin.valueChanged.connect(self.controls_to_box)

        self.exposure_spin = QtWidgets.QDoubleSpinBox()
        self.exposure_spin.setRange(-10.0, 10.0)
        self.exposure_spin.setSingleStep(0.25)
        self.exposure_spin.setDecimals(2)
        self.exposure_spin.setSuffix(" stops")
        self.exposure_spin.valueChanged.connect(self.load_current_preview)

        self.export_button = self._button("Export Crops", "SP_DialogSaveButton")
        self.export_button.setObjectName("exportButton")
        self.export_button.clicked.connect(self.export_all)
        self.export_button.setEnabled(False)

        self.status_label = self._path_label("Ready")
        self.status_label.setObjectName("statusLabel")

        self.preview = ImageSelector()
        self.preview.region_changed.connect(self.preview_region_to_controls)

        self._build_layout()
        self._refresh_box_controls()
        self._refresh_file_list_labels()

    def _build_layout(self) -> None:
        controls = QtWidgets.QWidget()
        controls.setMinimumWidth(420)
        controls.setMaximumWidth(560)
        controls_layout = QtWidgets.QVBoxLayout(controls)
        controls_layout.setContentsMargins(12, 12, 12, 12)
        controls_layout.setSpacing(10)

        files_group = QtWidgets.QGroupBox("Files")
        files_layout = QtWidgets.QVBoxLayout(files_group)
        files_buttons = QtWidgets.QHBoxLayout()
        files_buttons.addWidget(self.add_button)
        files_buttons.addWidget(self.remove_button)
        files_layout.addLayout(files_buttons)
        files_layout.addWidget(self.file_list, 4)
        files_layout.addWidget(self.set_ref_button)
        files_layout.addWidget(self.ref_label)
        files_layout.addWidget(self.output_button)
        files_layout.addWidget(self.output_label)

        boxes_group = QtWidgets.QGroupBox("Crop Boxes")
        boxes_layout = QtWidgets.QVBoxLayout(boxes_group)
        boxes_layout.addWidget(self.box_list, 1)
        box_buttons = QtWidgets.QHBoxLayout()
        box_buttons.addWidget(self.add_box_button)
        box_buttons.addWidget(self.remove_box_button)
        boxes_layout.addLayout(box_buttons)
        boxes_layout.addWidget(self.color_button)

        coordinates_group = QtWidgets.QGroupBox("Coordinates")
        coordinates_layout = QtWidgets.QFormLayout(coordinates_group)
        coordinates_layout.addRow("X", self.x_spin)
        coordinates_layout.addRow("Y", self.y_spin)
        coordinates_layout.addRow("Width", self.w_spin)
        coordinates_layout.addRow("Height", self.h_spin)
        coordinates_layout.addRow("Line Width", self.line_width_spin)
        coordinates_layout.addRow("Exposure", self.exposure_spin)

        controls_layout.addWidget(files_group, 3)
        controls_layout.addWidget(boxes_group, 1)
        controls_layout.addWidget(coordinates_group)
        controls_layout.addWidget(self.export_button)
        controls_layout.addWidget(self.status_label)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(controls)
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([460, 760])
        self.setCentralWidget(splitter)

    def _button(self, text: str, standard_icon_name: str | None = None) -> QtWidgets.QPushButton:
        button = QtWidgets.QPushButton(text)
        if standard_icon_name is not None:
            icon_enum = getattr(QtWidgets.QStyle.StandardPixmap, standard_icon_name, None)
            if icon_enum is not None:
                button.setIcon(self.style().standardIcon(icon_enum))
        button.setMinimumHeight(34)
        return button

    def _list_widget(self, minimum_height: int) -> QtWidgets.QListWidget:
        list_widget = QtWidgets.QListWidget()
        list_widget.setMinimumHeight(minimum_height)
        list_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        list_widget.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        list_widget.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        list_widget.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        list_widget.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        list_widget.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
        list_widget.setUniformItemSizes(True)
        return list_widget

    def _path_label(self, text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setObjectName("pathLabel")
        label.setWordWrap(True)
        return label

    def _make_spinbox(self) -> QtWidgets.QSpinBox:
        spin = QtWidgets.QSpinBox()
        spin.setRange(0, 999999)
        spin.setMinimumHeight(30)
        return spin

    def add_files(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Select EXR files",
            str(self._default_input_dir()),
            "OpenEXR Images (*.exr *.EXR)",
        )
        if not paths:
            return

        existing = {path.resolve() for path in self.files}
        for raw_path in paths:
            path = Path(raw_path).resolve()
            if path in existing:
                continue
            self.files.append(path)
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.file_list.addItem(item)
            existing.add(path)

        self._refresh_file_list_labels()

        if self.file_list.currentRow() < 0:
            self.file_list.setCurrentRow(0)
        self._refresh_export_enabled()

    def remove_selected(self) -> None:
        row = self.file_list.currentRow()
        if row < 0:
            return
        removed = self.files.pop(row)
        self.file_list.takeItem(row)
        if self.ref_file == removed:
            self.ref_file = None
        self._refresh_file_list_labels()

        if self.files:
            self.file_list.setCurrentRow(min(row, len(self.files) - 1))
        else:
            self.preview.set_image(None)
            self.current_size = None
            self._refresh_box_controls()
        self._refresh_export_enabled()

    def set_selected_ref(self) -> None:
        row = self.file_list.currentRow()
        if row < 0 or row >= len(self.files):
            return
        self.ref_file = self.files[row]
        self._refresh_file_list_labels()
        self._refresh_export_enabled()

    def choose_output_dir(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select output folder",
            str(self._default_output_dir()),
        )
        if not path:
            return
        self.output_dir = Path(path)
        self.output_label.setText(str(self.output_dir))
        self.output_label.setToolTip(str(self.output_dir))
        self._refresh_export_enabled()

    def choose_box_color(self) -> None:
        box = self._active_box()
        if box is None:
            return
        dialog = self._color_dialog(box.color)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        color = dialog.selectedColor()
        if not color.isValid():
            return
        box.color = color
        self._refresh_box_ui()

    def add_box(self) -> None:
        if self.current_size is None:
            return
        image_width, image_height = self.current_size
        width = max(1, image_width // 3)
        height = max(1, image_height // 3)
        region = Region(
            max(0, (image_width - width) // 2),
            max(0, (image_height - height) // 2),
            width,
            height,
        )
        self.crop_boxes.append(
            CropBox(region, QtGui.QColor(DEFAULT_BOX_COLOR), DEFAULT_LINE_WIDTH)
        )
        self.active_box_index = len(self.crop_boxes) - 1
        self._refresh_box_ui()
        self._refresh_export_enabled()

    def remove_box(self) -> None:
        if not (0 <= self.active_box_index < len(self.crop_boxes)):
            return
        self.crop_boxes.pop(self.active_box_index)
        if self.crop_boxes:
            self.active_box_index = min(self.active_box_index, len(self.crop_boxes) - 1)
        else:
            self.active_box_index = -1
        self._refresh_box_ui()
        self._refresh_export_enabled()

    def select_box(self, row: int) -> None:
        if self._syncing_box_ui:
            return
        self.active_box_index = row if 0 <= row < len(self.crop_boxes) else -1
        self._refresh_box_controls()
        self.preview.set_boxes(self.crop_boxes, self.active_box_index)

    def load_current_preview(self, *_args: object) -> None:
        row = self.file_list.currentRow()
        if row < 0 or row >= len(self.files):
            return

        path = self.files[row]
        try:
            image = read_exr(path)
            rgb = rgb_from_channels(image.channels)
            preview_rgb = tonemap_rgb(rgb, exposure_stops=self.exposure_spin.value())
            self.preview.set_image(qimage_from_rgb8(preview_rgb))
            self.preview.set_boxes(self.crop_boxes, self.active_box_index)
            self.current_size = (image.width, image.height)
            self._refresh_box_controls()
            self.status_label.setText(f"Loaded {path.name} ({image.width}x{image.height})")
        except Exception as exc:
            self.preview.set_image(None)
            self.status_label.setText(str(exc))
            self.current_size = None
            self._refresh_box_controls()
        self._refresh_export_enabled()

    def preview_region_to_controls(self, region: Region) -> None:
        if self.current_size is not None:
            region = region.clamped(*self.current_size)

        box = self._active_box()
        if box is None:
            self.crop_boxes.append(
                CropBox(region, QtGui.QColor(DEFAULT_BOX_COLOR), DEFAULT_LINE_WIDTH)
            )
            self.active_box_index = len(self.crop_boxes) - 1
        else:
            box.region = region
        self._refresh_box_ui()
        self._refresh_export_enabled()

    def controls_to_box(self, *_args: object) -> None:
        if self.current_size is None:
            return
        box = self._active_box()
        if box is None:
            return

        box.region = Region(
            self.x_spin.value(),
            self.y_spin.value(),
            self.w_spin.value(),
            self.h_spin.value(),
        ).clamped(*self.current_size)
        box.line_width = self.line_width_spin.value()
        self._refresh_box_ui()
        self._refresh_export_enabled()

    def export_all(self) -> None:
        if self.output_dir is None or self.ref_file is None or not self.crop_boxes or not self.files:
            return

        failures: list[str] = []
        crop_pairs = 0
        for path in self.files:
            for index, box in enumerate(self.crop_boxes, start=1):
                try:
                    export_crop(
                        path,
                        self.output_dir,
                        box.region,
                        exposure_stops=self.exposure_spin.value(),
                        region_label=f"r{index:02d}",
                    )
                    crop_pairs += 1
                except Exception as exc:
                    failures.append(f"{path.name} r{index:02d}: {exc}")

        overlay_path: Path | None = None
        if self.ref_file is not None:
            try:
                overlay_path = save_reference_overlay(
                    self.ref_file,
                    self.output_dir,
                    [
                        (box.region, box.color_tuple(), box.line_width)
                        for box in self.crop_boxes
                    ],
                    exposure_stops=self.exposure_spin.value(),
                )
            except Exception as exc:
                failures.append(f"{self.ref_file.name} overlay: {exc}")

        if failures:
            self.status_label.setText(
                f"Exported {crop_pairs} crop pairs. Failed: " + " | ".join(failures)
            )
        elif overlay_path is not None:
            self.status_label.setText(
                f"Exported {crop_pairs} crop pairs and {overlay_path.name}"
            )
        else:
            self.status_label.setText(f"Exported {crop_pairs} crop pairs")

    def _refresh_box_ui(self) -> None:
        self._syncing_box_ui = True
        self.box_list.clear()
        for index, box in enumerate(self.crop_boxes, start=1):
            region = box.region
            item = QtWidgets.QListWidgetItem(
                f"r{index:02d}  x={region.x}, y={region.y}, w={region.width}, h={region.height}, line={box.line_width}"
            )
            item.setToolTip(box.color.name())
            self.box_list.addItem(item)
        if 0 <= self.active_box_index < len(self.crop_boxes):
            self.box_list.setCurrentRow(self.active_box_index)
        self._syncing_box_ui = False

        self._refresh_box_controls()
        self.preview.set_boxes(self.crop_boxes, self.active_box_index)

    def _refresh_box_controls(self) -> None:
        box = self._active_box()
        has_active = box is not None
        for widget in (self.x_spin, self.y_spin, self.w_spin, self.h_spin, self.line_width_spin):
            widget.setEnabled(has_active)
            widget.blockSignals(True)

        if box is not None:
            region = box.region
            self.x_spin.setValue(region.x)
            self.y_spin.setValue(region.y)
            self.w_spin.setValue(region.width)
            self.h_spin.setValue(region.height)
            self.line_width_spin.setValue(box.line_width)
        else:
            self.x_spin.setValue(0)
            self.y_spin.setValue(0)
            self.w_spin.setValue(0)
            self.h_spin.setValue(0)
            self.line_width_spin.setValue(DEFAULT_LINE_WIDTH)

        for widget in (self.x_spin, self.y_spin, self.w_spin, self.h_spin, self.line_width_spin):
            widget.blockSignals(False)

        self.add_box_button.setEnabled(self.current_size is not None)
        self.remove_box_button.setEnabled(has_active)
        self.color_button.setEnabled(has_active)
        self._refresh_color_button()

    def _refresh_file_list_labels(self) -> None:
        for index, path in enumerate(self.files):
            item = self.file_list.item(index)
            if item is None:
                continue
            is_ref = path == self.ref_file
            prefix = "[REF] " if is_ref else ""
            item.setText(prefix + path.name)
            font = item.font()
            font.setBold(is_ref)
            item.setFont(font)
            item.setToolTip(str(path))

        if self.ref_file is None:
            self.ref_label.setText("Ref: none")
            self.ref_label.setToolTip("")
        else:
            self.ref_label.setText(f"Ref: {self.ref_file.name}")
            self.ref_label.setToolTip(str(self.ref_file))

    def _refresh_color_button(self) -> None:
        box = self._active_box()
        color = box.color if box is not None else DEFAULT_BOX_COLOR
        self.color_button.setText(f"Box Color {color.name()}" if box is not None else "Box Color")
        self.color_button.setStyleSheet(
            f"QPushButton {{ border-color: {color.name()}; }}"
        )

    def _color_dialog(self, initial_color: QtGui.QColor) -> QtWidgets.QColorDialog:
        dialog = QtWidgets.QColorDialog(QtGui.QColor(initial_color), self)
        dialog.setWindowTitle("Select crop box color")
        dialog.setOption(QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel, False)
        dialog.setStyleSheet(COLOR_DIALOG_STYLESHEET)
        return dialog

    def _refresh_export_enabled(self) -> None:
        self.export_button.setEnabled(
            bool(self.files)
            and self.output_dir is not None
            and self.ref_file is not None
            and bool(self.crop_boxes)
        )

    def _active_box(self) -> CropBox | None:
        if 0 <= self.active_box_index < len(self.crop_boxes):
            return self.crop_boxes[self.active_box_index]
        return None

    def _default_input_dir(self) -> Path:
        candidate = Path.cwd() / "input_exr"
        return candidate if candidate.exists() else Path.cwd()

    def _default_output_dir(self) -> Path:
        candidate = Path.cwd() / "output"
        return candidate if candidate.exists() else Path.cwd()


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
