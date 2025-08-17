# --- START OF FILE ui_components.py ---

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox, QListWidget, QGraphicsView, QMenu
)
from PyQt6.QtCore import pyqtSignal, Qt, QPointF, QPoint, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QKeyEvent
from shapely.geometry import Point

from app_state import AppState

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
    addTextRequested = pyqtSignal(QPointF)
    removeAnnotationRequested = pyqtSignal(object)
    removeAllAnnotationsRequested = pyqtSignal()
    backspacePressed = pyqtSignal()

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self.is_panning = False
        self.last_pan_point = QPoint()
        self.main_window = parent
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.right_click_press_pos = None

        self.snap_indicator = None
        self.snapped_point_scene = None
        self.snapped_on_geom_world = None
        self.SNAP_TOLERANCE_PIXELS = 10
        self.last_trace_geom = None

    def keyPressEvent(self, event: QKeyEvent):
        """キープレスイベントを処理する。"""
        if event.key() == Qt.Key.Key_Backspace:
            self.backspacePressed.emit()
        else:
            super().keyPressEvent(event)

    def clear_snap_indicator(self):
        """スナップインジケータを安全に削除し、変数をリセットする。"""
        if self.snap_indicator:
            if self.snap_indicator.scene():
                self.scene().removeItem(self.snap_indicator)
            self.snap_indicator = None


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

    def show_context_menu(self, pos):
        menu = QMenu(self)
        item_at_pos = self.itemAt(pos)
        
        from renderer import DraggableLabelItem
        if isinstance(item_at_pos, DraggableLabelItem) and item_at_pos.is_annotation:
            delete_action = menu.addAction("この注釈を削除")
            action = menu.exec(self.mapToGlobal(pos))
            if action == delete_action:
                self.removeAnnotationRequested.emit(item_at_pos.unique_id)
        else:
            if self.main_window.project.app_state == AppState.DRAWING_SPLIT_LINE:
                self.sceneRightClicked.emit()
                return

            add_text_action = menu.addAction("テキストを追加")
            
            if self.main_window and (self.main_window.project.text_annotations or self.main_window.project.label_positions):
                menu.addSeparator()
                delete_all_action = menu.addAction("すべての注釈とラベル位置をリセット")
            else:
                delete_all_action = None

            action = menu.exec(self.mapToGlobal(pos))

            if action == add_text_action:
                scene_pos = self.mapToScene(pos)
                self.addTextRequested.emit(scene_pos)
            elif action == delete_all_action:
                self.removeAllAnnotationsRequested.emit()
    
    def _update_snap_indicator(self):
        self.clear_snap_indicator()

        if self.snapped_point_scene:
            size = self.SNAP_TOLERANCE_PIXELS
            rect = QRectF(-size/2, -size/2, size, size)
            pen = QPen(QColor("magenta"), 1.5)
            self.snap_indicator = self.scene().addEllipse(rect, pen, QBrush(QColor(255, 0, 255, 100)))
            self.snap_indicator.setPos(self.snapped_point_scene)
            self.snap_indicator.setZValue(9999) # Always on top
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        elif self.main_window and self.main_window.project.app_state == AppState.DRAWING_SPLIT_LINE:
             self.viewport().setCursor(Qt.CursorShape.CrossCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.right_click_press_pos = event.pos()
            super().mousePressEvent(event)
            return
        
        if event.button() == Qt.MouseButton.LeftButton:
            item_at_pos = self.itemAt(event.pos())
            if item_at_pos and item_at_pos.data(0) == "draggable_label":
                super().mousePressEvent(event)
                return

            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                if self.main_window and self.main_window.project.app_state not in [AppState.IDLE, AppState.READY_TO_START]:
                    self.main_window.reset_for_repositioning()
                self.is_panning = True
                self.last_pan_point = event.pos()
                self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            else:
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
                
                pos_to_emit = self.snapped_point_scene if self.snapped_point_scene else self.mapToScene(event.pos())
                self.sceneClicked.emit(pos_to_emit)
                self.last_trace_geom = self.snapped_on_geom_world

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.RightButton:
            self.right_click_press_pos = None
        
        if self.is_panning:
            delta = event.pos() - self.last_pan_point
            if self.main_window:
                self.main_window.project.map_offset_x += delta.x()
                self.main_window.project.map_offset_y += delta.y()
                self.main_window.renderer.full_redraw(hide_pointers=True, hide_calc_results=True)
            self.last_pan_point = event.pos()
        else:
            self.snapped_point_scene = None
            self.snapped_on_geom_world = None
            scene_pos = self.mapToScene(event.pos())
            
            if self.main_window and self.main_window.project.snapping_enabled and self.main_window.project.app_state == AppState.DRAWING_SPLIT_LINE:
                self.snapped_point_scene, self.snapped_on_geom_world = self.main_window.renderer.find_snap_point(scene_pos, self.SNAP_TOLERANCE_PIXELS)
            
            self._update_snap_indicator()

            if self.main_window and self.main_window.project.app_state == AppState.DRAWING_SPLIT_LINE and self.main_window.project.current_split_line_points:
                mouse_pos_for_preview = self.snapped_point_scene if self.snapped_point_scene else scene_pos
                trace_points = None

                if self.main_window.project.tracing_enabled and self.last_trace_geom and self.snapped_on_geom_world and \
                   self.snapped_on_geom_world.equals(self.last_trace_geom):
                    
                    last_point_scene = self.main_window.project.current_split_line_points[-1]
                    last_point_world_coords = self.main_window.renderer.scene_to_world(last_point_scene)
                    current_point_world_coords = self.main_window.renderer.scene_to_world(mouse_pos_for_preview)

                    if last_point_world_coords and current_point_world_coords:
                        trace_points = self.main_window.renderer.find_trace_points(
                            self.last_trace_geom,
                            Point(last_point_world_coords),
                            Point(current_point_world_coords)
                        )
                
                self.main_window.renderer.draw_splitting_line(
                    self.main_window.project.current_split_line_points,
                    mouse_pos_for_preview,
                    trace_points
                )
            self.sceneMouseMoved.emit(scene_pos)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton and self.right_click_press_pos is not None:
            if (event.pos() - self.right_click_press_pos).manhattanLength() < 4:
                self.show_context_menu(event.pos())
            self.right_click_press_pos = None
        
        if event.button() == Qt.MouseButton.LeftButton and self.is_panning:
            self.is_panning = False
            
            current_app_state = self.main_window.project.app_state if self.main_window else AppState.IDLE
            if current_app_state in [AppState.AWAITING_LANDING_POINT, AppState.DRAWING_SPLIT_LINE]:
                self.viewport().setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.viewport().setCursor(Qt.CursorShape.ArrowCursor)

            if self.main_window and self.main_window.renderer:
                self.main_window.renderer.full_redraw()
                self.main_window.update_area_display()

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