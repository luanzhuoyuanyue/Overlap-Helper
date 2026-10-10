"""The original Overlap-page layout, using Maya 2025–2027's Qt6."""
import traceback

from maya import cmds, OpenMayaUI
from PySide6 import QtCore, QtWidgets
from shiboken6 import wrapInstance

from . import overlap

WINDOW = 'overlapMotionWindow'
_window = None


class NumberBox(QtWidgets.QDoubleSpinBox):
    def textFromValue(self, value):
        text = ('%.3f' % value).rstrip('0').rstrip('.')
        return text if '.' in text else text + '.0'


class SliderRow(QtWidgets.QWidget):
    def __init__(self, label, value, minimum, maximum, slider_maximum=None):
        super().__init__()
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QtWidgets.QLabel(label)
        title.setFixedWidth(74)
        self.field = NumberBox()
        self.field.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.field.setDecimals(3)
        self.field.setRange(minimum, maximum)
        self.field.setFixedWidth(48)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.setRange(round(minimum * 1000), round((slider_maximum or maximum) * 1000))
        layout.addWidget(title)
        layout.addWidget(self.field)
        layout.addWidget(self.slider, 1)
        self.field.valueChanged.connect(self._field_changed)
        self.slider.valueChanged.connect(lambda v: self.field.setValue(v / 1000.0))
        self.set_value(value)

    def _field_changed(self, value):
        blocked = QtCore.QSignalBlocker(self.slider)
        if round(value * 1000) > self.slider.maximum():
            self.slider.setMaximum(round(value * 1000))
        self.slider.setValue(round(value * 1000))
        del blocked

    def value(self):
        return self.field.value()

    def set_value(self, value):
        self.field.setValue(value)


class Window(QtWidgets.QDialog):
    def __init__(self):
        parent = wrapInstance(int(OpenMayaUI.MQtUtil.mainWindow()), QtWidgets.QWidget)
        super().__init__(parent)
        self.setObjectName(WINDOW)
        self.setWindowTitle('重叠动画助手')
        self.setWindowFlags(QtCore.Qt.WindowType.Window)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumWidth(310)
        self.resize(310, 370)
        self.last_layer = None
        self.last_error = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 16)
        layout.setSpacing(12)
        heading = QtWidgets.QPushButton('重叠动画')
        heading.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        heading.setToolTip('重叠动画功能独立重写版 · Maya 2025–2027')
        layout.addWidget(heading)
        layout.addSpacing(10)

        mode_row = QtWidgets.QHBoxLayout()
        self.rotat = QtWidgets.QRadioButton('旋转')
        self.trans = QtWidgets.QRadioButton('位移')
        self.cus = QtWidgets.QCheckBox('自定义')
        self.physics = QtWidgets.QCheckBox('物理解算')
        self.rotat.setChecked(True)
        for widget in (self.rotat, self.trans, self.cus, self.physics):
            mode_row.addWidget(widget)
        layout.addLayout(mode_row)
        axis_row = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel('轴向')
        label.setFixedWidth(74)
        axis_row.addWidget(label)
        self.axes = {}
        for axis in ('X', 'Y', 'Z'):
            box = QtWidgets.QCheckBox(axis)
            box.setChecked(True)
            self.axes[axis] = box
            axis_row.addWidget(box, 1)
        layout.addLayout(axis_row)

        self.smoothness = SliderRow('平滑度', 3.0, 0.1, 1000000, 6)
        self.scale = SliderRow('比例', 1.0, 0.1, 1000000, 6)
        self.overshoot = SliderRow('回弹强度', 10.0, 1, 1000000, 10)
        for widget in (self.smoothness, self.scale, self.overshoot):
            layout.addWidget(widget)
        self.ignore_first = QtWidgets.QCheckBox('忽略首个控制器')
        self.hierarchy = QtWidgets.QCheckBox('包含子层级')
        self.loop = QtWidgets.QCheckBox('循环')
        self.add_to_layer = QtWidgets.QCheckBox('添加到动画层')
        self.add_to_layer.setChecked(True)
        for widget in (self.ignore_first, self.hierarchy, self.loop, self.add_to_layer):
            layout.addWidget(widget)
        layout.addSpacing(2)
        self.create_button = QtWidgets.QPushButton('生成动画')
        self.create_button.setMinimumHeight(28)
        layout.addWidget(self.create_button)

        self.rotat.toggled.connect(self.update_mode)
        self.cus.toggled.connect(self.custom_changed)
        self.physics.toggled.connect(self.physics_changed)
        self.create_button.clicked.connect(self.generate)
        self.rotat.setToolTip('为当前选择生成旋转重叠动画。')
        self.trans.setToolTip('为当前选择生成位移重叠动画。')
        self.cus.setToolTip('轴向表示局部偏移方向，默认 Y；多选时按原版 X、Y、Z 顺序，最后选中的轴生效。')
        self.physics.setToolTip('使用与 Maya 2023 原版一致的 nParticle 目标跟随；关闭时使用关键帧偏移。')
        self.smoothness.setToolTip('关闭物理解算：关键帧延迟帧数。开启物理解算：2–9，默认 8，控制解算时间比例。')
        self.scale.setToolTip('原版比例参数：缩短目标偏移距离并调整旋转关键帧延迟；最小 0.1。')
        self.overshoot.setToolTip('控制粒子目标跟随的平滑程度，默认 10，最小 1；仅物理解算启用。')
        self.hierarchy.setToolTip('选择根控制器，处理下面的控制器链；曲线控制器的偏移组会跳过。')
        self.ignore_first.setToolTip('保持所选链的首控制器原动画。')
        self.loop.setToolTip('循环烘焙；播放范围结束帧应为下一周期的第一帧。')
        self.add_to_layer.setToolTip('勾选：生成 OverlapHelper 动画层。关闭：直接替换范围内所选通道关键帧。')
        self.create_button.setToolTip('读取 Maya 当前选择和播放范围。计算期间暂停视口显示，结束后恢复。Ctrl+Z 撤销整次生成。')
        self.update_mode()

    def custom_changed(self, checked):
        for axis, box in self.axes.items():
            box.setChecked(axis == 'Y' if checked else True)
        self.update_mode()

    def physics_changed(self, checked):
        self.smoothness.field.setRange(2 if checked else 0.1, 9 if checked else 1000000)
        self.smoothness.slider.setRange(2000 if checked else 100, 9000 if checked else 6000)
        self.smoothness.set_value(8 if checked else 3)
        self.update_mode()

    def update_mode(self, *_):
        rotation = self.rotat.isChecked()
        self.cus.setEnabled(rotation)
        if not rotation:
            self.cus.setChecked(False)
            for box in self.axes.values():
                box.setChecked(True)
        self.scale.setEnabled(rotation)
        self.overshoot.setEnabled(self.physics.isChecked())
        self.ignore_first.setEnabled(rotation and not self.cus.isChecked())

    def generate(self, *_):
        self.create_button.setEnabled(False)
        self.last_error = None
        try:
            self.last_layer = overlap.create(
                rotation=self.rotat.isChecked(), custom=self.cus.isChecked(),
                physics=self.physics.isChecked(),
                axes=tuple(a for a, box in self.axes.items() if box.isChecked()),
                smoothness=self.smoothness.value(), scale=self.scale.value(),
                overshoot=self.overshoot.value(),
                ignore_first=self.ignore_first.isEnabled() and self.ignore_first.isChecked(),
                hierarchy=self.hierarchy.isChecked(), loop=self.loop.isChecked(),
                add_to_layer=self.add_to_layer.isChecked())
            message = '已生成：' + (self.last_layer or '当前动画曲线')
            cmds.inViewMessage(amg=message, pos='topCenter', fade=True)
            return self.last_layer
        except (ValueError, RuntimeError) as error:
            self.last_error = str(error)
            cmds.warning(str(error))
            cmds.inViewMessage(amg=str(error), pos='topCenter', fade=True)
        except Exception:
            self.last_error = traceback.format_exc()
            traceback.print_exc()
            cmds.warning('生成失败，已撤销本次修改；请查看脚本编辑器。')
        finally:
            self.create_button.setEnabled(True)


def show():
    global _window
    if _window is not None:
        try:
            _window.close()
        except RuntimeError:
            pass
    _window = Window()
    _window.show()
    return _window
