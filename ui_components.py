# --- START OF FILE ui_components.py ---

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox, QListWidget, QGraphicsView, QMenu
)
from PyQt6.QtCore import pyqtSignal, Qt, QPointF, QPoint
from PyQt6.QtGui import QPainter

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
    # --- ▼▼▼ デバッグ用シグナルを削除 ▼▼▼ ---
    # exportDebugInfoRequested = pyqtSignal()
    # --- ▲▲▲ ---

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
            
            # --- ▼▼▼ デバッグメニューを削除 ▼▼▼ ---
            # menu.addSeparator()
            # debug_action = menu.addAction("デバッグ情報をエクスポート")
            # --- ▲▲▲ ---

            action = menu.exec(self.mapToGlobal(pos))

            if action == add_text_action:
                scene_pos = self.mapToScene(pos)
                self.addTextRequested.emit(scene_pos)
            elif action == delete_all_action:
                self.removeAllAnnotationsRequested.emit()
            # --- ▼▼▼ デバッグアクションの処理を削除 ▼▼▼ ---
            # elif action == debug_action:
            #     self.exportDebugInfoRequested.emit()
            # --- ▲▲▲ ---
    
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
                self.sceneClicked.emit(self.mapToScene(event.pos()))
    
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
            if self.main_window and self.main_window.project.app_state == AppState.DRAWING_SPLIT_LINE and self.main_window.project.current_split_line_points:
                self.main_window.renderer.draw_splitting_line(
                    self.main_window.project.current_split_line_points,
                    self.mapToScene(event.pos())
                )
            self.sceneMouseMoved.emit(self.mapToScene(event.pos()))

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