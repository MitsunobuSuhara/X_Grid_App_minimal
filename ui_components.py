# --- START OF FILE ui_components.py ---

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox, QListWidget, QGraphicsView, QMenu,
    QWidget, QFormLayout, QLineEdit, QPushButton, QHBoxLayout, QColorDialog, QFontComboBox,
    QSpinBox, QButtonGroup, QGridLayout
)
from PyQt6.QtCore import pyqtSignal, Qt, QPointF, QPoint, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QKeyEvent, QFont
from shapely.geometry import Point

from app_state import AppState

class TextAnnotationDialog(QDialog):
    """テキストの編集、フォント選択、色選択を一度に行うカスタムダイアログ"""
    def __init__(self, current_data, target_item, parent=None):
        super().__init__(parent)
        self.setWindowTitle("テキストのプロパティ編集")
        self.target_item = target_item

        # キャンセル時のために元のスタイルを保存
        self.original_text = self.target_item.toPlainText()
        self.original_font = self.target_item.font()
        self.original_color = self.target_item.defaultTextColor()
        
        self.layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # 1. テキスト入力
        self.text_edit = QLineEdit(current_data['text'])
        form_layout.addRow("テキスト:", self.text_edit)

        # 2. フォント選択
        font_widget = QWidget()
        font_layout = QHBoxLayout(font_widget)
        font_layout.setContentsMargins(0, 0, 0, 0)
        
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(current_data['font_family']))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 72)
        self.font_size_spin.setValue(current_data['font_size'])
        self.font_size_spin.setStyleSheet("background-color: #FFFFFF;")
        self.bold_check = QCheckBox("太字")
        self.bold_check.setChecked(current_data['font_bold'])
        self.italic_check = QCheckBox("斜体")
        self.italic_check.setChecked(current_data['font_italic'])
        
        font_layout.addWidget(self.font_combo)
        font_layout.addWidget(self.font_size_spin)
        font_layout.addWidget(self.bold_check)
        font_layout.addWidget(self.italic_check)
        form_layout.addRow("フォント:", font_widget)

        # 3. カラーパレット (拡充)
        color_widget = QWidget()
        self.color_layout = QGridLayout(color_widget)
        self.color_layout.setContentsMargins(0, 0, 0, 0)
        self.color_layout.setSpacing(4)
        self.color_group = QButtonGroup(self)
        
        colors = [
            '#000000', '#404040', '#808080', '#C0C0C0', '#FFFFFF', 
            '#A0522D', '#8B4513', '#D2691E',
            '#008000', '#2E8B57', '#0000FF', '#FF0000',
            '#FFFF00', '#FFA500', '#800080', '#FFC0CB'
        ]
        current_qcolor = QColor(*current_data['color_rgba'])
        
        row, col = 0, 0
        for color_hex in colors:
            btn = QPushButton()
            btn.setFixedSize(22, 22)
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{ background-color: {color_hex}; border: 1px solid #999; border-radius: 3px; }}
                QPushButton:checked {{ border: 2px solid #0078d7; }}
            """)
            btn.setProperty("color", QColor(color_hex))
            self.color_layout.addWidget(btn, row, col)
            self.color_group.addButton(btn)
            if QColor(color_hex) == current_qcolor:
                btn.setChecked(True)
            col += 1
            if col >= 8: # 8色で改行
                col = 0
                row += 1
        
        if not self.color_group.checkedButton():
             self.color_group.buttons()[0].setChecked(True)

        form_layout.addRow("文字色:", color_widget)
        self.layout.addLayout(form_layout)
        
        # OK / Cancel ボタン
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.layout.addWidget(button_box)

        # 信号を接続して動的プレビューを実現
        self.text_edit.textChanged.connect(self._update_preview)
        self.font_combo.currentFontChanged.connect(self._update_preview)
        self.font_size_spin.valueChanged.connect(self._update_preview)
        self.bold_check.stateChanged.connect(self._update_preview)
        self.italic_check.stateChanged.connect(self._update_preview)
        self.color_group.buttonClicked.connect(self._update_preview)

    def _update_preview(self):
        if not self.target_item: return
        
        new_text = self.text_edit.text()
        new_font = self.font_combo.currentFont()
        new_font.setPointSize(self.font_size_spin.value())
        new_font.setBold(self.bold_check.isChecked())
        new_font.setItalic(self.italic_check.isChecked())
        
        checked_button = self.color_group.checkedButton()
        new_color = checked_button.property("color") if checked_button else self.original_color

        self.target_item.setPlainText(new_text)
        self.target_item.setFont(new_font)
        self.target_item.setDefaultTextColor(new_color)

    def get_final_style(self):
        font = self.font_combo.currentFont()
        font.setPointSize(self.font_size_spin.value())
        font.setBold(self.bold_check.isChecked())
        font.setItalic(self.italic_check.isChecked())
        
        checked_button = self.color_group.checkedButton()
        color = checked_button.property("color") if checked_button else QColor("black")

        return {
            'text': self.text_edit.text(),
            'font': font,
            'color': color
        }

    def reject(self):
        # キャンセル時には元のスタイルに戻す
        if self.target_item:
            self.target_item.setPlainText(self.original_text)
            self.target_item.setFont(self.original_font)
            self.target_item.setDefaultTextColor(self.original_color)
        super().reject()


class LayerSelectionDialog(QDialog):
    def __init__(self, layer_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("レイヤを選択")
        self.layout = QVBoxLayout(self)
        self.checkboxes = []
        for name in layer_names:
            if name in ['layer_styles', 'gpkg_layer_styles']: continue
            cb = QCheckBox(name); cb.setChecked(True)
            self.checkboxes.append(cb); self.layout.addWidget(cb)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept); button_box.rejected.connect(self.reject)
        self.layout.addWidget(button_box)
        self.setStyleSheet("""
            QDialog { background-color: #F0F0F0; } 
            QCheckBox { color: #000000; }
            QCheckBox::indicator { border: 1px solid #000000; background-color: #FFFFFF; width: 13px; height: 13px; }
            QCheckBox::indicator:checked { border: 1px solid #000000; background-color: qradialgradient(cx: 0.5, cy: 0.5, radius: 0.5, fx: 0.5, fy: 0.5, stop: 0 #4287F5, stop: 0.4 #4287F5, stop: 0.41 #FFFFFF, stop: 1 #FFFFFF); }
        """)
    def get_selected_layers(self):
        return [cb.text() for cb in self.checkboxes if cb.isChecked()]


class DroppableListWidget(QListWidget):
    filesDropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(
            url.toLocalFile().lower().endswith(('.shp', '.gpkg'))
            for url in event.mimeData().urls()
        ):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        event.acceptProposedAction() if event.mimeData().hasUrls() else event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        valid_paths = [
            url.toLocalFile() for url in urls
            if url.toLocalFile().lower().endswith(('.shp', '.gpkg'))
        ]
        if valid_paths:
            self.filesDropped.emit(valid_paths)


class MyGraphicsView(QGraphicsView):
    sceneClicked = pyqtSignal(QPointF)
    sceneRightClicked = pyqtSignal()
    sceneMouseMoved = pyqtSignal(QPointF)
    viewZoomed = pyqtSignal()
    filesDropped = pyqtSignal(list)
    removeAnnotationRequested = pyqtSignal(object)
    editAnnotationPropertiesRequested = pyqtSignal(object)
    backspacePressed = pyqtSignal()

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self.main_window = parent
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

        # --- 状態管理フラグ ---
        self.is_panning = False
        self.is_dragging_item = False

        # --- 位置情報 ---
        self.last_pan_point = QPoint()
        self.right_click_press_pos = None
        self.drag_item = None
        self.drag_start_item_pos = QPointF()
        self.drag_start_mouse_pos = QPointF()

        # --- スナップ関連 ---
        self.snap_indicator = None
        self.snapped_point_scene = None
        self.snapped_on_geom_world = None
        self.SNAP_TOLERANCE_PIXELS = 10
        self.last_trace_geom = None

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Backspace:
            self.backspacePressed.emit()
        else:
            super().keyPressEvent(event)

    def clear_snap_indicator(self):
        if self.snap_indicator:
            if self.snap_indicator.scene():
                self.scene().removeItem(self.snap_indicator)
            self.snap_indicator = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(
            url.toLocalFile().lower().endswith(('.shp', '.gpkg')) for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        event.acceptProposedAction() if event.mimeData().hasUrls() else event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        valid_paths = [url.toLocalFile() for url in urls if url.toLocalFile().lower().endswith(('.shp', '.gpkg'))]
        if valid_paths:
            self.filesDropped.emit(valid_paths)

    def show_context_menu(self, pos):
        from renderer import DraggableLabelItem
        item_at_pos = self.itemAt(pos)
        if isinstance(item_at_pos, DraggableLabelItem):
            self.scene().clearSelection()
            item_at_pos.setSelected(True)
            if item_at_pos.is_annotation:
                menu = QMenu(self)
                menu.setStyleSheet("""
                    QMenu {
                        background-color: #2E2E2E;
                        color: #FFFFFF;
                        border: 1px solid #555555;
                        padding: 5px;
                    }
                    QMenu::item {
                        padding: 8px 25px;
                        border-radius: 4px;
                    }
                    QMenu::item:selected {
                        background-color: #505050;
                    }
                    QMenu::separator {
                        height: 1px;
                        background: #555555;
                        margin: 4px 0px;
                    }
                """)
                edit_action = menu.addAction("プロパティ")
                delete_action = menu.addAction("このテキストを削除")
                action = menu.exec(self.mapToGlobal(pos))
                if action == edit_action:
                    self.editAnnotationPropertiesRequested.emit(item_at_pos.unique_id)
                elif action == delete_action:
                    self.removeAnnotationRequested.emit(item_at_pos.unique_id)
        elif self.main_window.project.app_state == AppState.DRAWING_SPLIT_LINE:
            self.sceneRightClicked.emit()

    def _update_snap_indicator(self):
        self.clear_snap_indicator()
        if self.snapped_point_scene:
            size = self.SNAP_TOLERANCE_PIXELS
            rect = QRectF(-size / 2, -size / 2, size, size)
            pen = QPen(QColor("magenta"), 1.5)
            self.snap_indicator = self.scene().addEllipse(rect, pen, QBrush(QColor(255, 0, 255, 100)))
            self.snap_indicator.setPos(self.snapped_point_scene)
            self.snap_indicator.setZValue(9999)
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        elif self.main_window and self.main_window.project.app_state in [AppState.DRAWING_SPLIT_LINE, AppState.AWAITING_ANNOTATION_POINT]:
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)

    def mousePressEvent(self, event):
        from renderer import DraggableLabelItem
        item_at_pos = self.itemAt(event.pos())

        if event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                self.is_panning = True
                self.last_pan_point = event.pos()
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                super().mousePressEvent(event)
                return

            if self.main_window and self.main_window.project.tracing_enabled and \
               self.main_window.project.app_state == AppState.DRAWING_SPLIT_LINE and \
               self.main_window.project.current_split_line_points and self.snapped_point_scene:
                
                last_point_scene = self.main_window.project.current_split_line_points[-1]
                last_point_world_coords = self.main_window.renderer.scene_to_world(last_point_scene)
                current_point_world_coords = self.main_window.renderer.scene_to_world(self.snapped_point_scene)

                if self.last_trace_geom and last_point_world_coords and current_point_world_coords:
                    trace_points = self.main_window.renderer.find_trace_points(
                        self.last_trace_geom,
                        Point(last_point_world_coords),
                        Point(current_point_world_coords)
                    )
                    if trace_points:
                        self.main_window.project.current_split_line_points.extend(trace_points)
            
            # アイテム上でのクリックでない場合、またはトレース機能が有効な場合にシグナルを発行
            if not isinstance(item_at_pos, DraggableLabelItem):
                pos_to_emit = self.snapped_point_scene if self.snapped_point_scene else self.mapToScene(event.pos())
                self.sceneClicked.emit(pos_to_emit)
                self.last_trace_geom = self.snapped_on_geom_world

        elif event.button() == Qt.MouseButton.RightButton:
            self.right_click_press_pos = event.pos()
            if isinstance(item_at_pos, DraggableLabelItem):
                self.is_dragging_item = True
                self.drag_item = item_at_pos
                self.drag_start_item_pos = item_at_pos.pos()
                self.drag_start_mouse_pos = self.mapToScene(event.pos())
        
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_dragging_item:
            if self.right_click_press_pos and (event.pos() - self.right_click_press_pos).manhattanLength() > 4:
                self.right_click_press_pos = None # ドラッグ開始
            
            delta = self.mapToScene(event.pos()) - self.drag_start_mouse_pos
            self.drag_item.setPos(self.drag_start_item_pos + delta)
            return

        if self.is_panning:
            delta = event.pos() - self.last_pan_point
            if self.main_window:
                self.main_window.project.map_offset_x += delta.x()
                self.main_window.project.map_offset_y += delta.y()
                self.main_window.renderer.full_redraw(hide_pointers=True, hide_calc_results=True)
            self.last_pan_point = event.pos()
            return
        
        scene_pos = self.mapToScene(event.pos())
        self.snapped_point_scene = None
        if self.main_window and self.main_window.project.snapping_enabled and self.main_window.project.app_state == AppState.DRAWING_SPLIT_LINE:
            self.snapped_point_scene, self.snapped_on_geom_world = self.main_window.renderer.find_snap_point(scene_pos, self.SNAP_TOLERANCE_PIXELS)
        self._update_snap_indicator()

        if self.main_window and self.main_window.project.app_state == AppState.DRAWING_SPLIT_LINE and self.main_window.project.current_split_line_points:
            mouse_pos_for_preview = self.snapped_point_scene if self.snapped_point_scene else scene_pos
            self.main_window.renderer.draw_splitting_line(self.main_window.project.current_split_line_points, mouse_pos_for_preview)

        self.sceneMouseMoved.emit(scene_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_panning:
                self.is_panning = False
                self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
                if self.main_window and self.main_window.renderer:
                    self.main_window.renderer.full_redraw()
                    self.main_window.update_area_display()

        elif event.button() == Qt.MouseButton.RightButton:
            if self.is_dragging_item:
                self.is_dragging_item = False
                if self.drag_item.pos() != self.drag_start_item_pos:
                    self.drag_item.positionChanged.emit(self.drag_item.unique_id, self.drag_item.pos())
                self.drag_item = None

            if self.right_click_press_pos is not None:
                self.show_context_menu(self.right_click_press_pos)
            
            self.right_click_press_pos = None

        super().mouseReleaseEvent(event)
        
    def wheelEvent(self, event):
        zoom_factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(zoom_factor, zoom_factor)
        self.viewZoomed.emit()

    def auto_fit_view(self):
        all_items_rect = self.scene().itemsBoundingRect()
        if self.main_window and self.main_window.renderer:
             grid_rect = self.main_window.renderer.get_grid_rect()
             bounding_rect = all_items_rect.united(grid_rect)
             if bounding_rect.isValid():
                self.fitInView(bounding_rect.adjusted(-20, -20, 20, 20), Qt.AspectRatioMode.KeepAspectRatio)