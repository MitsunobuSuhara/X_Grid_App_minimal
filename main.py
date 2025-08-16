# --- START OF FILE main.py ---

import sys
import os
import fiona
from fiona.errors import FionaError
import math
import re
from shapely.geometry import shape, LineString
import io
from PyPDF2 import PdfWriter

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QFileDialog, QMessageBox, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QListWidgetItem, QFrame, QLineEdit, QGraphicsScene,
    QInputDialog, QComboBox
)
from PyQt6.QtCore import Qt, QRectF, QMarginsF, QPointF, QSize, QPoint, QSizeF, QBuffer
from PyQt6.QtGui import QFont, QColor, QPainter, QPageLayout, QPageSize, QPdfWriter, QPen
from PyQt6.QtPrintSupport import QPrinter

from app_state import AppState 
from project import Project
from renderer import MapRenderer
from calculator import Calculator
from ui_components import LayerSelectionDialog, DroppableListWidget, MyGraphicsView

class X_Grid(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("X_Grid - 平均集材距離計算システム")
        self.setGeometry(50, 50, 1800, 1000)
        self.project = Project()
        self.scene = QGraphicsScene(self)
        self.renderer = MapRenderer(self.scene, self.project)
        self.calculator = Calculator(self.project, self.renderer)
        self.project.calculator = self.calculator
        self.previous_app_state = AppState.IDLE
        self.init_ui()
        self.renderer.draw_grid()
        self._update_ui_for_state(AppState.IDLE)
    
    def init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        top_level_layout = QHBoxLayout(central_widget)
        left_panel_widget = QWidget()
        left_panel_widget.setFixedWidth(380)
        left_panel_layout = QVBoxLayout(left_panel_widget)
        left_panel_layout.setSpacing(10)
        left_panel_layout.setContentsMargins(15, 15, 15, 15)
        
        guide_panel_widget = QWidget()
        guide_panel_layout = QVBoxLayout(guide_panel_widget)
        guide_panel_layout.setContentsMargins(0, 0, 0, 0)
        guide_panel_layout.setSpacing(0)

        guide_header_label = QLabel("ⓘ 操作ガイド")
        guide_header_label.setStyleSheet(
            """
            QLabel {
                color: #ffffff;
                background-color: #007bff;
                font-weight: bold;
                font-size: 14pt;
                padding: 12px 18px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            """
        )
        
        self.guide_content_label = QLabel()
        self.guide_content_label.setTextFormat(Qt.TextFormat.RichText)
        self.guide_content_label.setStyleSheet(
            """
            QLabel {
                color: #004085;
                background-color: #e7f3fe;
                font-size: 11pt;
                font-weight: bold;
                padding: 20px;
                border: 1px solid #b8daff;
                border-top: none;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
            """)
        self.guide_content_label.setWordWrap(True)
        
        guide_panel_layout.addWidget(guide_header_label)
        guide_panel_layout.addWidget(self.guide_content_label)
        
        layer_management_label = QLabel("<b>レイヤ管理 (計算対象のポリゴンを選択)</b>")
        self.layer_list_widget = DroppableListWidget()
        
        settings_button_layout = QVBoxLayout()
        settings_button_layout.setSpacing(8)
        
        self.start_single_button = QPushButton("① 区域全体で計算")
        self.start_single_button.setStyleSheet("font-size: 11pt; padding: 8px; font-weight: bold; background-color: #cce5ff;")
        
        self.start_split_button = QPushButton("② 区域を分割して計算")
        self.start_split_button.setStyleSheet("font-size: 11pt; padding: 8px;")
        
        self.clear_settings_button = QPushButton("設定クリア")
        
        settings_button_layout.addWidget(self.start_single_button)
        settings_button_layout.addWidget(self.start_split_button)
        settings_button_layout.addWidget(self.clear_settings_button)
        
        layer_buttons_layout = QHBoxLayout()
        self.add_layer_button = QPushButton("レイヤ追加")
        self.remove_layer_button = QPushButton("削除")
        self.layer_up_button = QPushButton("↑")
        self.layer_down_button = QPushButton("↓")
        layer_buttons_layout.addWidget(self.add_layer_button)
        layer_buttons_layout.addWidget(self.remove_layer_button)
        layer_buttons_layout.addStretch(1)
        layer_buttons_layout.addWidget(self.layer_up_button)
        layer_buttons_layout.addWidget(self.layer_down_button)

        left_panel_layout.addWidget(layer_management_label)
        left_panel_layout.addWidget(self.layer_list_widget)
        left_panel_layout.addLayout(layer_buttons_layout)
        
        left_panel_layout.addLayout(settings_button_layout)
        
        left_panel_layout.addWidget(guide_panel_widget)
        
        left_panel_layout.addStretch(1)

        right_panel_widget = QWidget()
        right_panel_layout = QVBoxLayout(right_panel_widget)
        right_panel_layout.setContentsMargins(0, 10, 10, 10)
        
        action_panel = QHBoxLayout()
        self.calculate_button = QPushButton("計算を実行")
        self.subtitle_input = QLineEdit()
        self.subtitle_input.setMinimumWidth(350)
        self.subtitle_input.setPlaceholderText("例：〇〇〇林小班、〇〇伐区")
        self.update_title_button = QPushButton("見出し表示")
        self.export_button = QPushButton("PDFエクスポート")
        self.display_mode_combo = QComboBox()
        
        action_panel.addWidget(self.calculate_button)
        action_panel.addSpacing(20)
        action_panel.addWidget(QLabel("見出し:"))
        action_panel.addWidget(self.subtitle_input)
        action_panel.addWidget(self.update_title_button)
        action_panel.addStretch(1)
        
        self.area_label = QLabel("面積: - ha")
        self.area_label.setStyleSheet("font-weight: bold; font-size: 11pt; margin-right: 10px;")
        action_panel.addWidget(self.area_label)

        action_panel.addWidget(self.display_mode_combo)
        action_panel.addWidget(self.export_button)
        right_panel_layout.addLayout(action_panel)
        
        self.view = MyGraphicsView(self.scene, self)
        self.scene.setBackgroundBrush(QColor("#FFFFFF"))
        right_panel_layout.addWidget(self.view)
        
        top_level_layout.addWidget(left_panel_widget)
        top_level_layout.addWidget(right_panel_widget, 1)
        
        self.setStyleSheet(
            """
            QWidget { background-color: #F0F0F0; color: #000000; } 
            QPushButton { background-color: #E1E1E1; border: 1px solid #ADADAD; padding: 5px 12px; border-radius: 3px; } 
            QPushButton:hover { background-color: #E9E9E9; } 
            QPushButton:pressed { background-color: #D6D6D6; } 
            QPushButton:disabled { background-color: #F5F5F5; color: #ADADAD; border-color: #C1C1C1; } 
            QListWidget { background-color: #FFFFFF; border: 1px solid #ABADB3; } 
            QListWidget::item:selected { background-color: #D9E8FB; color: #000000; } 
            QListWidget::indicator { border: 1px solid #000000; background-color: #FFFFFF; width: 13px; height: 13px; } 
            QListWidget::indicator:checked { border: 1px solid #000000; background-color: qradialgradient(cx: 0.5, cy: 0.5, radius: 0.5, fx: 0.5, fy: 0.5, stop: 0 #4287F5, stop: 0.4 #4287F5, stop: 0.41 #FFFFFF, stop: 1 #FFFFFF); } 
            QGraphicsView { border: 1px solid #767676; } 
            QLineEdit { background-color: #FFFFFF; border: 1px solid #ABADB3; border-radius: 3px; padding: 2px 4px; } 
            QComboBox { background-color: #FFFFFF; border: 1px solid #ABADB3; border-radius: 3px; padding: 2px 4px; }
            QFrame[frameShape="4"] { border: none; height: 1px; background-color: #D1D1D1; }
            """
        )
        
        self.display_mode_combo.setStyleSheet(
            """
            QComboBox {
                background-color: #e7f3fe;
                border: 1px solid #007bff;
                padding: 4px 8px;
                font-weight: bold;
                border-radius: 3px;
            }
            QComboBox:hover {
                background-color: #d0e8fd;
            }
            QComboBox QAbstractItemView {
                background-color: white;
                border: 1px solid #007bff;
                selection-background-color: #D9E8FB;
                selection-color: black;
            }
            """)

        self.add_layer_button.clicked.connect(self.prompt_add_layer); self.remove_layer_button.clicked.connect(self.remove_selected_layer); self.layer_up_button.clicked.connect(self.move_layer_up); self.layer_down_button.clicked.connect(self.move_layer_down); self.layer_list_widget.itemChanged.connect(self.on_layer_item_changed); self.layer_list_widget.currentItemChanged.connect(self.on_layer_item_changed); self.view.filesDropped.connect(self.handle_dropped_files); self.layer_list_widget.filesDropped.connect(self.handle_dropped_files)
        
        self.start_single_button.clicked.connect(self._start_single_area_workflow)
        self.start_split_button.clicked.connect(self._start_split_area_workflow)
        self.clear_settings_button.clicked.connect(self.clear_all_calculation_settings)
        
        self.calculate_button.clicked.connect(self.run_calculation_and_draw); 
        self.export_button.clicked.connect(self.export_results); self.update_title_button.clicked.connect(self.update_title_display); self.subtitle_input.returnPressed.connect(self.update_title_display); self.view.sceneClicked.connect(self.on_scene_clicked); self.view.sceneRightClicked.connect(self.on_scene_right_clicked); self.display_mode_combo.currentIndexChanged.connect(self.on_display_mode_changed)
        self.view.addTextRequested.connect(self.add_text_annotation)
        self.view.removeAnnotationRequested.connect(self.remove_text_annotation)
        self.view.removeAllAnnotationsRequested.connect(self.remove_all_text_annotations)
        self.view.exportDebugInfoRequested.connect(self.export_debug_info)
        
        self._update_ui_for_state(AppState.IDLE)

    def export_debug_info(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "デバッグ情報を保存", "debug_geometries.txt", "Text Files (*.txt)")
        if not file_path:
            return

        try:
            with open(file_path, 'w') as f:
                f.write("--- Calculation Target Geometry (WKT) ---\n")
                calc_geom = self.project._get_combined_calculable_geom()
                if calc_geom:
                    f.write(calc_geom.wkt)
                else:
                    f.write("None")
                f.write("\n\n")

                f.write("--- Split Lines (WKT) ---\
")
                if self.project.split_lines:
                    from shapely.ops import unary_union
                    splitter = unary_union(self.project.split_lines)
                    f.write(splitter.wkt)
                else:
                    f.write("None")
                f.write("\n")
            QMessageBox.information(self, "成功", f"デバッグ情報を保存しました:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"デバッグ情報の保存中にエラーが発生しました: {e}")

    def _set_guide_text(self, text):
        rich_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        self.guide_content_label.setText(rich_text)

    def update_area_display(self):
        in_area_cells = self.calculator.get_in_area_cells()
        cell_count = len(in_area_cells)
        if cell_count > 0:
            area_ha = cell_count * (self.project.k_value ** 2) / 10000
            self.area_label.setText(f"面積: {area_ha:.2f} ha ({cell_count}セル)")
        else:
            self.area_label.setText("面積: - ha")

    def _update_ui_for_state(self, new_state):
        self.project.app_state = new_state
        
        self.start_single_button.setEnabled(False)
        self.start_split_button.setEnabled(False)

        self.calculate_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.display_mode_combo.setVisible(False)
        self.view.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        
        has_settings = bool(self.project.default_landing_cell or any(a.get('landing_cell') for a in self.project.sub_area_data) or self.project.split_lines or self.project.calculation_data)
        is_interactive_mode = new_state in [AppState.AWAITING_LANDING_POINT, AppState.DRAWING_SPLIT_LINE]
        self.clear_settings_button.setEnabled(has_settings or is_interactive_mode)

        if new_state == AppState.IDLE:
            initial_guide_text = (
                "**ファイルをドラッグ＆ドロップ**するか、\n"
                "**「レイヤ追加」**ボタンを押して、\n"
                "ベクターレイヤを読み込んでください。\n\n"
                "(対応形式: .gpkg, .shp, .zip)"
            )
            self._set_guide_text(initial_guide_text)
        elif new_state == AppState.READY_TO_START:
            ready_guide_text = (
                "**「レイヤ管理」**で計算対象のポリゴンに\n"
                "チェックが入っていることを確認し、\n"
                "**「区域全体」**または**「区域を分割」**ボタンで\n"
                "計算を開始してください。"
                "<br><br><small>※ 地図はCtrlキーを押しながらドラッグで移動できます。</small>"
            )
            self._set_guide_text(ready_guide_text)
            self.start_single_button.setEnabled(True)
            self.start_split_button.setEnabled(True)
        elif new_state == AppState.AWAITING_LANDING_POINT:
            self.view.viewport().setCursor(Qt.CursorShape.CrossCursor)
        elif new_state == AppState.DRAWING_SPLIT_LINE:
            self._set_guide_text("地図上で区域を分割する線を描画し、\n完了したら**右クリック**します。")
            self.view.viewport().setCursor(Qt.CursorShape.CrossCursor)
        elif new_state == AppState.CONFIGURING_SUB_AREAS:
             self._set_guide_text("分割後の各区域の設定を行います。\nダイアログの指示に従ってください。")
        elif new_state == AppState.READY_TO_CALCULATE:
            self._set_guide_text("全ての設定が完了しました。\n**「計算を実行」**ボタンを押してください。")
            self.calculate_button.setEnabled(True)
        elif new_state == AppState.RESULTS_DISPLAYED:
            self._set_guide_text("計算が完了しました。\n見出しを入力して「表示」後、\n**「PDFエクスポート」**が可能です。")
            self.calculate_button.setEnabled(True)
            self.export_button.setEnabled(self.project.title_is_displayed)
            if self.project.is_split_mode and len(self.project.sub_area_data) > 1:
                self.display_mode_combo.setVisible(True)
        
        self.update_area_display()

    def _start_single_area_workflow(self):
        self.clear_all_calculation_settings()
        self.project.is_split_mode = False
        self.project.configuring_area_index = None
        self._ask_base_calc_mode()

    def _start_split_area_workflow(self):
        self.clear_all_calculation_settings()
        self.project.is_split_mode = True
        self._update_ui_for_state(AppState.DRAWING_SPLIT_LINE)

    def _ask_base_calc_mode(self, area_index=None):
        area_name = "計算区域" if area_index is None else self.project.sub_area_data[area_index]['name']
        
        msg_box = QMessageBox(self)
        msg_box.setStyleSheet("QLabel{min-width: 400px; font-size: 11pt;}")
        msg_box.setWindowTitle("計算方法の選択")
        
        msg_box.setText(f"<div style='font-size: 14pt;'><b>【{area_name}】</b></div><br>土場の位置を選択してください。")
        msg_box.setTextFormat(Qt.TextFormat.RichText)

        internal_button = msg_box.addButton("集材区域内に土場がある", QMessageBox.ButtonRole.YesRole)
        external_button = msg_box.addButton("集材区域外に土場がある", QMessageBox.ButtonRole.NoRole)
        
        guide_global_pos = self.guide_content_label.mapToGlobal(QPoint(0, 0))
        msg_box.move(guide_global_pos.x() + self.guide_content_label.width() + 20, guide_global_pos.y())
        msg_box.exec()
        
        if msg_box.clickedButton() is None:
             if self.project.is_split_mode:
                 self._update_ui_for_state(AppState.CONFIGURING_SUB_AREAS)
             else:
                 self._evaluate_and_set_readiness_state()
             return

        is_internal = msg_box.clickedButton() == internal_button
        mode = "internal" if is_internal else "external"
        guide_text_base = "『土場』" if is_internal else "『区域の入口』"
        
        guide_text = f"**【{area_name}】**の**{guide_text_base}**の位置を\n**左クリック**で指定してください。"
        self._set_guide_text(guide_text)

        self.project.configuring_area_index = area_index
        
        if area_index is None:
            self.project.default_calc_mode = mode
        else:
            self.project.sub_area_data[area_index]['calc_mode'] = mode
        
        self._update_ui_for_state(AppState.AWAITING_LANDING_POINT)

    def _get_external_distance(self):
        area_index = self.project.configuring_area_index
        area_name = "計算区域" if area_index is None else self.project.sub_area_data[area_index]['name']
        prompt_title = f"【{area_name}】の追加距離L"

        dialog = QInputDialog(self)
        dialog.setWindowTitle(prompt_title)
        dialog.setLabelText("区域入口から土場までの水平距離 L (m):")
        dialog.setInputMode(QInputDialog.InputMode.DoubleInput)
        dialog.setDoubleRange(0, 99999)
        dialog.setDoubleDecimals(1)
        
        dialog.setStyleSheet(
            """
            QDoubleSpinBox {
                selection-background-color: #CCCCCC;
                selection-color: black;
            }
            """)
        guide_global_pos = self.guide_content_label.mapToGlobal(QPoint(0, 0))
        dialog.move(guide_global_pos.x() + self.guide_content_label.width() + 20, guide_global_pos.y())
        
        ok = dialog.exec()
        distance = dialog.doubleValue()

        if ok:
            if area_index is None:
                self.project.default_additional_distance = distance
                self._update_ui_for_state(AppState.READY_TO_CALCULATE)
            else:
                self.project.sub_area_data[area_index]['additional_distance'] = distance
                self._configure_next_sub_area()
        else:
            QMessageBox.information(self, "やり直し", "距離の入力がキャンセルされました。もう一度、計算方法から指定してください。")
            self._ask_base_calc_mode(area_index)

    def _configure_next_sub_area(self):
        current_index = self.project.configuring_area_index
        next_index = current_index + 1
        
        if next_index < len(self.project.sub_area_data):
            self.project.configuring_area_index = next_index
            self._ask_base_calc_mode(next_index)
        else:
            self._update_ui_for_state(AppState.READY_TO_CALCULATE)

    def _is_ready_to_start(self):
        return any(l.get('is_calc_target') for l in self.project.layers if l.get('is_calculable'))

    def _evaluate_and_set_readiness_state(self):
        if self.project.app_state in [AppState.AWAITING_TEXT_POINT]: return
        if self._is_ready_to_start(): self._update_ui_for_state(AppState.READY_TO_START)
        else: self._update_ui_for_state(AppState.IDLE)
        
    def on_layer_item_changed(self, item=None):
        for i in range(self.layer_list_widget.count()):
            list_item = self.layer_list_widget.item(i)
            is_checked = (list_item.checkState() == Qt.CheckState.Checked) if list_item.flags() & Qt.ItemFlag.ItemIsUserCheckable else False
            self.project.set_calc_target_status(i, is_checked)
        self.update_layout_and_redraw()
        self._evaluate_and_set_readiness_state()
        self.update_area_display()
        self.renderer.update_area_outline()
    
    def add_text_annotation(self, scene_pos):
        text, ok = QInputDialog.getText(self, "テキスト入力", "表示するテキストを入力してください:")
        if ok and text:
            world_pos = self.renderer.scene_to_world(scene_pos)
            if world_pos:
                self.project.add_text_annotation(text, world_pos)
                self.renderer.full_redraw()

    def remove_text_annotation(self, annotation_id):
        reply = QMessageBox.question(self, "注釈の削除", "この注釈を削除しますか？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.project.remove_text_annotation(annotation_id)
            self.renderer.full_redraw()

    def remove_all_text_annotations(self):
        reply = QMessageBox.question(self, "すべての注釈を削除", "すべての注釈と移動したラベル位置をリセットしますか？\nこの操作は元に戻せません。",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.project.remove_all_annotations()
            self.renderer.full_redraw()

    def on_scene_clicked(self, scene_pos):
        current_state = self.project.app_state
        
        if self.project.is_split_mode and current_state == AppState.RESULTS_DISPLAYED:
            QMessageBox.information(self, "情報", "分割モードの計算結果です。\n設定を変更する場合は「設定クリア」を押してください。")
            return

        if current_state in [AppState.AWAITING_LANDING_POINT, AppState.READY_TO_CALCULATE, AppState.RESULTS_DISPLAYED]:
            if current_state != AppState.AWAITING_LANDING_POINT:
                self.reset_for_repositioning()
                return

            grid_rect = self.renderer.get_grid_rect()
            if grid_rect.contains(scene_pos):
                col, row = int((scene_pos.x() - self.renderer.grid_offset_x) / self.project.cell_size_on_screen), int((scene_pos.y() - self.renderer.grid_offset_y) / self.project.cell_size_on_screen)
                if 0 <= row < self.project.grid_rows and 0 <= col < self.project.grid_cols:
                    area_index = self.project.configuring_area_index
                    
                    if area_index is None:
                        calc_mode = self.project.default_calc_mode
                        target_geom = self.project._get_combined_calculable_geom()
                    else:
                        calc_mode = self.project.sub_area_data[area_index]['calc_mode']
                        target_geom = self.project.sub_area_data[area_index]['geom']

                    if calc_mode == 'internal':
                        is_valid_click = self.calculator.is_cell_in_area((row, col), target_geom)
                        if not is_valid_click:
                            QMessageBox.warning(self, "入力エラー", "土場は、計算対象区域内のセルをクリックして指定してください。")
                            return
                    elif calc_mode == 'external':
                        is_valid_click = self.renderer.is_cell_on_boundary(row, col, target_geom)
                        if not is_valid_click:
                            QMessageBox.warning(self, "入力エラー", "区域の入口は、対象区域の境界線上のセルをクリックしてください。")
                            return

                    if area_index is None:
                        self.project.default_landing_cell = (row, col)
                    else:
                        self.project.sub_area_data[area_index]['landing_cell'] = (row, col)
                    
                    self.renderer.draw_all_pointers()

                    if calc_mode == "internal":
                        if area_index is None:
                            self._update_ui_for_state(AppState.READY_TO_CALCULATE)
                        else:
                            self._configure_next_sub_area()
                    elif calc_mode == "external": 
                        self._get_external_distance()

        elif current_state == AppState.DRAWING_SPLIT_LINE:
            self.project.current_split_line_points.append(scene_pos)
            self.renderer.draw_splitting_line(self.project.current_split_line_points, None)
    
    def on_scene_right_clicked(self):
        if self.project.app_state == AppState.DRAWING_SPLIT_LINE:
            if len(self.project.current_split_line_points) > 1:
                world_points = []
                for p in self.project.current_split_line_points:
                    world_coord = self.renderer.scene_to_world(p)
                    if world_coord:
                        world_points.append(world_coord)
                
                if len(world_points) > 1:
                    line = LineString(world_points)
                    self.project.split_lines.append(line)

            self.project.current_split_line_points = []
            self.renderer.clear_temporary_splitting_line()
            self.renderer.draw_split_lines()

            if self.project.split_lines:
                try:
                    self.project.prepare_sub_areas()
                    self.renderer.full_redraw()
                    self.project.configuring_area_index = -1
                    self._update_ui_for_state(AppState.CONFIGURING_SUB_AREAS)
                    self._configure_next_sub_area()
                except Exception as e: 
                    QMessageBox.critical(self, "分割エラー", f"{e}")
                    self.project.reset_split_settings()
                    self.renderer.full_redraw()
                    self._update_ui_for_state(AppState.DRAWING_SPLIT_LINE)
            else: 
                QMessageBox.warning(self, "情報", "分割線が描画されませんでした。")
                self._update_ui_for_state(AppState.DRAWING_SPLIT_LINE)

    def on_display_mode_changed(self, index):
        if index == -1: return
        mode = self.display_mode_combo.itemData(index)
        if self.project.display_mode != mode: 
            self.project.display_mode = mode
            self.renderer.full_redraw()
            self.view.auto_fit_view()

    def prompt_add_layer(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "ベクターファイルを選択", "", "ベクターファイル (*.gpkg *.shp *.zip)");
        if not file_path: return
        self._handle_file_addition(file_path)

    def handle_dropped_files(self, file_paths):
        valid_paths = [
            path for path in file_paths
            if path.lower().endswith(('.shp', '.gpkg', '.zip'))
        ]
        for file_path in valid_paths:
             self._handle_file_addition(file_path)

    def _handle_file_addition(self, file_path):
        layer_names_to_add = []
        try:
            if file_path.lower().endswith('.zip'):
                layer_names_to_add = [name for name in fiona.listlayers(f"zip://{file_path}") if name.lower().endswith('.shp')]
                if not layer_names_to_add:
                    QMessageBox.warning(self, "読み込みエラー", "ZIPファイル内にシェープファイル (.shp) が見つかりませんでした。")
                    return
            elif file_path.lower().endswith('.shp'):
                layer_names_to_add = [None]
            elif file_path.lower().endswith('.gpkg'):
                all_layer_names = fiona.listlayers(file_path)
                dialog = LayerSelectionDialog(all_layer_names, self)
                if dialog.exec():
                    layer_names_to_add = dialog.get_selected_layers()
                else:
                    return
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"ファイルからレイヤリストを取得できませんでした。\n\n詳細: {e}"); return
        if not layer_names_to_add: return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            if self.add_layers_from_file(file_path, layer_names_to_add):
                self.project.map_offset_x = 0.0
                self.project.map_offset_y = 0.0
                self.update_layout_and_redraw()
        finally:
            QApplication.restoreOverrideCursor()

    def add_layers_from_file(self, file_path, layer_names):
        new_layers_added = False
        self.layer_list_widget.blockSignals(True)
        
        is_zip = file_path.lower().endswith('.zip')
        
        for layer_name in layer_names:
            try:
                open_path = f"zip://{file_path}" if is_zip else file_path
                
                features, geom_type, crs = [], 'Unknown', None
                try:
                    with fiona.open(open_path, 'r', layer=layer_name, encoding='utf-8') as c:
                        features, geom_type, crs = list(c), c.schema.get('geometry','Unknown'), c.crs
                except (FionaError, UnicodeDecodeError):
                    with fiona.open(open_path, 'r', layer=layer_name, encoding='cp932') as c:
                        features, geom_type, crs = list(c), c.schema.get('geometry','Unknown'), c.crs
                if not features: continue
                if crs and crs.get('proj') == 'longlat':
                    QMessageBox.warning(self, "座標系の警告", "地理座標系の可能性があります。平面直角座標系のデータを使用してください。")
                
                is_calculable = "Polygon" in geom_type

                if is_zip:
                    display_name = os.path.splitext(layer_name)[0]
                    item_text = f"{os.path.basename(file_path)} ({display_name})"
                    internal_name = display_name
                elif layer_name is None:
                    internal_name = os.path.splitext(os.path.basename(file_path))[0]
                    item_text = os.path.basename(file_path)
                else:
                    internal_name = layer_name
                    item_text = f"{os.path.basename(file_path)} ({layer_name})"

                layer_info = {'path': file_path, 'layer_name': internal_name, 'geom_type': geom_type, 'features': features, 'graphics_items': [], 'is_calculable': is_calculable, 'is_calc_target': is_calculable}
                self.project.add_layer(layer_info)
                list_item = QListWidgetItem(item_text)
                if is_calculable:
                    list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    list_item.setCheckState(Qt.CheckState.Checked)
                else:
                    list_item.setFlags(list_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                self.layer_list_widget.insertItem(0, list_item)
                new_layers_added = True
            except FionaError as e:
                error_str = str(e).lower()
                if 'failed to open dataset' in error_str or 'does not exist in zip file' in error_str:
                     QMessageBox.warning(self, "読み込みエラー", 
                        f"シェープファイルの読み込みに失敗しました。\n\n"
                        f"・関連ファイル (.shp, .shx, .dbf 等) は全て揃っていますか？\n"
                        f"・ZIPファイルに圧縮して読み込むと解決する場合があります。\n\n"
                        f"詳細: {e}")
                else:
                    QMessageBox.warning(self, "読み込みエラー", f"レイヤ '{layer_name}' の読み込みに失敗しました。\n詳細: {e}")
                continue
            except Exception as e:
                QMessageBox.warning(self, "読み込みエラー", f"予期せぬエラーが発生しました。\n詳細: {e}")
                continue
                
        self.layer_list_widget.blockSignals(False); self.layer_list_widget.setCurrentRow(0)
        self.on_layer_item_changed()
        self._evaluate_and_set_readiness_state()
        return new_layers_added
    
    def remove_selected_layer(self):
        current_row = self.layer_list_widget.currentRow()
        if current_row < 0: return

        self.project.remove_layer(current_row)
        self.layer_list_widget.takeItem(current_row)
        
        self.clear_all_calculation_settings()
        
        self.on_layer_item_changed()

    def move_layer_up(self):
        current_row = self.layer_list_widget.currentRow()
        if current_row > 0: self.project.move_layer_up(current_row); item = self.layer_list_widget.takeItem(current_row); self.layer_list_widget.insertItem(current_row - 1, item); self.layer_list_widget.setCurrentRow(current_row - 1); self.renderer.redraw_all_layers()

    def move_layer_down(self):
        current_row = self.layer_list_widget.currentRow()
        if 0 <= current_row < self.layer_list_widget.count() - 1: self.project.move_layer_down(current_row); item = self.layer_list_widget.takeItem(current_row); self.layer_list_widget.insertItem(current_row + 1, item); self.layer_list_widget.setCurrentRow(current_row + 1); self.renderer.redraw_all_layers()

    def clear_all_calculation_settings(self):
        self.project.reset_calculation_settings()
        self.project.remove_all_annotations()
        self.renderer.clear_all_calculation_graphics()
        self.renderer.full_redraw()
        self._evaluate_and_set_readiness_state()
        self.update_area_display()
        
    def reset_for_repositioning(self):
        if self.project.is_split_mode and self.project.app_state == AppState.RESULTS_DISPLAYED:
            QMessageBox.information(self, "情報", "分割モードの計算結果です。\n設定を変更する場合は「設定クリア」を押してください。")
            return

        # 既存のグラフィッククリア処理
        self.project.calculation_data = None
        self.renderer.clear_all_pointers()
        for item_list in [self.renderer.calculation_items, self.renderer.title_items]:
            for item in item_list:
                if item.scene(): self.renderer.scene.removeItem(item)
            item_list.clear()
        
        # 関連する設定を完全にリセット
        if self.project.is_split_mode:
            for area_data in self.project.sub_area_data:
                area_data['landing_cell'] = None
                area_data['result'] = None
                area_data['calc_mode'] = 'default'
                area_data['additional_distance'] = 0.0
            
            self.project.configuring_area_index = -1
            self._update_ui_for_state(AppState.CONFIGURING_SUB_AREAS)
            self._configure_next_sub_area() # これで最初のエリアから設定をやり直す
        else:
            # 単一モードの場合、デフォルト設定を完全にリセット
            self.project.default_landing_cell = None
            self.project.default_calc_mode = None
            self.project.default_additional_distance = 0.0
            
            # 再度、計算方法の選択から開始させる
            self._ask_base_calc_mode()
        
        self.update_area_display()

    def update_layout_and_redraw(self):
        self.project.update_master_bbox(); layout_changed, info_message = self.project.determine_layout()
        if layout_changed and info_message: QMessageBox.information(self, "レイアウト情報", info_message)
        self.renderer.full_redraw()
        self.view.auto_fit_view()

    def update_title_display(self):
        subtitle_text = self.subtitle_input.text().strip()
        if not subtitle_text: QMessageBox.warning(self, "入力エラー", "見出しを入力してください。"); return
        if not self.project.calculation_data: self.project.calculation_data = {}
        self.project.calculation_data['subtitle_text'] = subtitle_text
        self.project.title_is_displayed = True
        self.renderer.full_redraw()
        self.export_button.setEnabled(self.project.title_is_displayed)
    
    def run_calculation_and_draw(self):
        self._update_ui_for_state(AppState.CALCULATION_RUNNING); QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            calc_data = self.calculator.run_calculation()
            if not calc_data: 
                QMessageBox.warning(self, "計算エラー", "計算対象となるエリアが見つかりませんでした。")
                self._update_ui_for_state(AppState.READY_TO_CALCULATE)
                QApplication.restoreOverrideCursor()
                return
            
            self.project.calculation_data = calc_data
            self.display_mode_combo.blockSignals(True)
            self.display_mode_combo.clear()
            
            if self.project.is_split_mode and len(self.project.sub_area_data) > 1:
                self.display_mode_combo.addItem("加重平均（総括）", "summary")
                for area_data in self.project.sub_area_data: 
                    self.display_mode_combo.addItem(f"{area_data['name']} の詳細", f"area_{area_data['id']}")
            
            self.display_mode_combo.blockSignals(False)
            self.project.display_mode = 'summary'
            
            self.renderer.full_redraw()
            self.view.auto_fit_view()

        except Exception as e: 
            QMessageBox.critical(self, "エラー", f"計算または描画中にエラーが発生しました: {e}")
        finally: 
            QApplication.restoreOverrideCursor()
            self._update_ui_for_state(AppState.RESULTS_DISPLAYED)

    def export_results(self):
        if not self.project.title_is_displayed:
            QMessageBox.warning(self, "入力エラー", "見出しが入力・表示されていません。\n入力して「見出し表示」ボタンを押してから、再度エクスポートしてください。")
            return
        if not self.project.calculation_data:
            QMessageBox.warning(self, "エラー", "エクスポートする内容がありません。「計算を実行」してください。")
            return

        is_split_mode_multi_area = self.project.is_split_mode and len(self.project.sub_area_data) > 1

        if is_split_mode_multi_area:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setWindowTitle("エクスポート方法の選択")
            msg_box.setText("複数ページの出力方法を選択してください。")
            
            single_file_button = msg_box.addButton("1つのPDFファイルにまとめる", QMessageBox.ButtonRole.YesRole)
            multiple_files_button = msg_box.addButton("ページごとに個別のPDFファイルで保存", QMessageBox.ButtonRole.NoRole)
            current_page_button = msg_box.addButton("現在表示中のページのみ", QMessageBox.ButtonRole.ActionRole)
            cancel_button = msg_box.addButton("キャンセル", QMessageBox.ButtonRole.RejectRole)

            msg_box.exec()

            clicked_button = msg_box.clickedButton()
            if clicked_button == single_file_button:
                self._export_multi_page_pdf()
            elif clicked_button == multiple_files_button:
                self._export_multiple_individual_pdfs()
            elif clicked_button == current_page_button:
                self._export_single_page_pdf()
            else:
                return
        else:
            self._export_single_page_pdf()
            
    def _export_single_page_pdf(self):
        subtitle = self.subtitle_input.text().strip()
        
        if self.project.is_split_mode:
            display_mode_str = self.project.display_mode if self.project.display_mode != 'summary' else '総括'
            default_filename = f"X-Grid_{subtitle}_{display_mode_str}.pdf"
        else:
            default_filename = f"X-Grid_{subtitle}.pdf"

        file_path, _ = QFileDialog.getSaveFileName(self, "結果をPDFにエクスポート", default_filename, "PDF Document (*.pdf)")
        if not file_path:
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.renderer.pointer_items_visible(False)
        try:
            is_split_summary = self.project.is_split_mode and self.project.display_mode == 'summary'
            if is_split_summary:
                page_size_id = QPageSize.PageSizeId.A4
                orientation = QPageLayout.Orientation.Portrait
            else:
                is_a3_mode = self.project.page_orientation == QPageLayout.Orientation.Landscape and self.project.grid_cols > self.project.grid_cols_a4
                page_size_id = QPageSize.PageSizeId.A3 if is_a3_mode else QPageSize.PageSizeId.A4
                orientation = self.project.page_orientation

            pdf_data = self._render_page_to_memory(self.project.display_mode, page_size_id, orientation)
            
            with open(file_path, "wb") as f:
                f.write(pdf_data)

            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("成功")
            msg.setText(f"結果をPDFとして保存しました:\n{file_path}")
            msg.setInformativeText(
                "<b>【印刷時の重要事項】</b><br>"
                "PDFはAdobe社の仕様に準拠して正確に作成されていますが、"
                "Webブラウザ等で表示・印刷すると、ごくわずかな寸法の誤差が生じる場合があります。<br><br>"
                "最も正確に印刷するには、<b>Adobe Acrobat Reader</b>で開き、"
                "印刷設定で<b>「実際のサイズ」</b>を選択することを推奨します。"
            )
            msg.exec()

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"エクスポート中にエラーが発生しました: {e}")
        finally:
            self.renderer.pointer_items_visible(True)
            QApplication.restoreOverrideCursor()

    def _export_multi_page_pdf(self):
        subtitle = self.subtitle_input.text().strip()
        default_filename = f"X-Grid_{subtitle}_一括.pdf"
        file_path, _ = QFileDialog.getSaveFileName(self, "結果をPDFにエクスポート", default_filename, "PDF Document (*.pdf)")
        if not file_path:
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.renderer.pointer_items_visible(False)
        
        merger = PdfWriter()
        
        try:
            is_a3_mode = self.project.page_orientation == QPageLayout.Orientation.Landscape and self.project.grid_cols > self.project.grid_cols_a4
            map_page_size_id = QPageSize.PageSizeId.A3 if is_a3_mode else QPageSize.PageSizeId.A4
            map_page_orientation = self.project.page_orientation

            summary_pdf_data = self._render_page_to_memory('summary', QPageSize.PageSizeId.A4, QPageLayout.Orientation.Portrait)
            merger.append(io.BytesIO(summary_pdf_data))

            for area_data in self.project.sub_area_data:
                display_mode = f"area_{area_data['id']}"
                area_pdf_data = self._render_page_to_memory(display_mode, map_page_size_id, map_page_orientation)
                merger.append(io.BytesIO(area_pdf_data))

            with open(file_path, "wb") as f:
                merger.write(f)
            
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("成功")
            msg.setText(f"結果をPDFとして保存しました:\n{file_path}")
            msg.setInformativeText(
                "<b>【印刷時の重要事項】</b><br>"
                "このPDFにはA4とA3など、異なるサイズのページが含まれている場合があります。<br>"
                "PDFの寸法はAdobe社の仕様に準拠して正確に作成されていますが、"
                "Webブラウザ等で表示・印刷すると、ごくわずかな寸法の誤差が生じることがあります。<br><br>"
                "最も正確に印刷するには、以下の方法を推奨します。<br>"
                "1. <b>(推奨)</b> Adobe Acrobat Readerで開き、印刷設定で<b>「PDFのページサイズに合わせて用紙を選択」</b>にチェックを入れてください。<br><br>"
                "2. <b>(代替案)</b> 上記設定ができない場合、印刷ダイアログで<b>ページ範囲を指定</b>し、サイズごとに分けて（例: 1ページ目をA4、2-3ページ目をA3で）印刷してください。"
            )
            msg.exec()

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"一括エクスポート中にエラーが発生しました: {e}")
        finally:
            merger.close()
            self.renderer.pointer_items_visible(True)
            QApplication.restoreOverrideCursor()

    def _export_multiple_individual_pdfs(self):
        subtitle = self.subtitle_input.text().strip()
        folder_path = QFileDialog.getExistingDirectory(self, "保存先フォルダを選択")
        if not folder_path:
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.renderer.pointer_items_visible(False)
        
        try:
            summary_filename = os.path.join(folder_path, f"X-Grid_{subtitle}_総括.pdf")
            summary_pdf_data = self._render_page_to_memory('summary', QPageSize.PageSizeId.A4, QPageLayout.Orientation.Portrait)
            with open(summary_filename, "wb") as f:
                f.write(summary_pdf_data)

            is_a3_mode = self.project.page_orientation == QPageLayout.Orientation.Landscape and self.project.grid_cols > self.project.grid_cols_a4
            map_page_size_id = QPageSize.PageSizeId.A3 if is_a3_mode else QPageSize.PageSizeId.A4
            map_page_orientation = self.project.page_orientation
            
            for area_data in self.project.sub_area_data:
                display_mode = f"area_{area_data['id']}"
                area_name = area_data['name']
                area_filename = os.path.join(folder_path, f"X-Grid_{subtitle}_{area_name}.pdf")
                
                area_pdf_data = self._render_page_to_memory(display_mode, map_page_size_id, map_page_orientation)
                with open(area_filename, "wb") as f:
                    f.write(area_pdf_data)

            QMessageBox.information(self, "成功", f"全ページを個別のPDFとして保存しました:\n{folder_path}")

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"個別ファイルのエクスポート中にエラーが発生しました: {e}")
        finally:
            self.renderer.pointer_items_visible(True)
            QApplication.restoreOverrideCursor()

    def _render_page_to_memory(self, display_mode, page_size_id, orientation):
        buffer = QBuffer()
        buffer.open(QBuffer.OpenModeFlag.ReadWrite)
        
        pdf_writer = QPdfWriter(buffer)
        
        page_layout = QPageLayout()
        page_size = QPageSize(page_size_id)
        page_layout.setPageSize(page_size)
        page_layout.setOrientation(orientation)
        page_layout.setMargins(QMarginsF(0, 0, 0, 0))
        pdf_writer.setPageLayout(page_layout)
        pdf_writer.setResolution(300)

        temp_project = Project()
        temp_project.layers = self.project.layers
        temp_project.k_value = self.project.k_value
        temp_project.cell_size_on_screen = self.project.cell_size_on_screen
        temp_project.calculation_data = self.project.calculation_data
        temp_project.is_split_mode = self.project.is_split_mode
        temp_project.sub_area_data = self.project.sub_area_data
        temp_project.map_rotation = self.project.map_rotation
        temp_project.master_bbox = self.project.master_bbox
        temp_project.text_annotations = self.project.text_annotations
        temp_project.label_positions = self.project.label_positions
        temp_project.title_is_displayed = self.project.title_is_displayed
        temp_project.display_mode = display_mode
        
        is_split_summary_page = self.project.is_split_mode and display_mode == 'summary'
        if is_split_summary_page:
            temp_project.grid_rows = temp_project.grid_rows_a4
            temp_project.grid_cols = temp_project.grid_cols_a4
        else:
            temp_project.grid_rows = self.project.grid_rows
            temp_project.grid_cols = self.project.grid_cols
        
        temp_project.grid_rows_a4 = self.project.grid_rows_a4
        temp_project.grid_cols_a4 = self.project.grid_cols_a4
        temp_project.grid_rows_a3 = self.project.grid_rows_a3
        temp_project.grid_cols_a3 = self.project.grid_cols_a3
        
        temp_scene = QGraphicsScene()
        temp_renderer = MapRenderer(temp_scene, temp_project, for_pdf=True)
        temp_calculator = Calculator(temp_project, temp_renderer)
        temp_project.calculator = temp_calculator
        
        temp_renderer.full_redraw(hide_pointers=True, for_pdf=True)
        
        source_rect = temp_renderer.get_full_content_rect()
        if not source_rect.isValid():
            raise Exception(f"ページ '{display_mode}' のコンテンツ描画範囲が無効です。")
        
        painter = QPainter(pdf_writer)
        try:
            # 1. 単位換算の定義
            scene_cell_size = temp_project.cell_size_on_screen
            physical_cell_size_mm = 5.0
            scene_units_per_mm = scene_cell_size / physical_cell_size_mm

            resolution = pdf_writer.resolution()
            mm_per_inch = 25.4
            dots_per_mm = resolution / mm_per_inch

            # 2. 描画内容の物理的なサイズを計算
            target_width_mm = source_rect.width() / scene_units_per_mm
            target_height_mm = source_rect.height() / scene_units_per_mm

            # 3. 用紙サイズとマージンを計算
            # page_sizeからではなく、ページの向きが反映されたpage_layoutから寸法を取得する
            page_rect_mm = page_layout.fullRect(QPageLayout.Unit.Millimeter)
            
            # コンテンツを用紙の中央に配置するためのマージン (mm)
            margin_x_mm = (page_rect_mm.width() - target_width_mm) / 2.0
            margin_y_mm = (page_rect_mm.height() - target_height_mm) / 2.0

            # 4. 最終的な描画領域をPDFの描画単位(dot)で定義
            target_rect_in_dots = QRectF(
                margin_x_mm * dots_per_mm,
                margin_y_mm * dots_per_mm,
                target_width_mm * dots_per_mm,
                target_height_mm * dots_per_mm
            )

            # 5. 固定スケールでレンダリング
            temp_scene.render(painter, target_rect_in_dots, source_rect)

        finally:
            painter.end()

        pdf_data = buffer.data()
        buffer.close()
        return bytes(pdf_data)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("游ゴシック", 10))
    window = X_Grid()
    window.show()
    sys.exit(app.exec())