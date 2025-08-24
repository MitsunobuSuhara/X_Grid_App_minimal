import uuid
from PyQt6.QtGui import QPageLayout, QFont, QColor
from shapely.geometry import shape, Polygon, MultiPolygon, LineString
from shapely.ops import unary_union, polygonize
from shapely.affinity import rotate, scale

from app_state import AppState

class Project:
    def __init__(self):
        # --- 基本設定 ---
        self.layers = []
        self.k_value = 25.0
        self.cell_size_on_screen = 25
        self.grid_rows_a4, self.grid_cols_a4 = 45, 31
        self.grid_rows_a3, self.grid_cols_a3 = 45, 73
        self.grid_rows, self.grid_cols = self.grid_rows_a4, self.grid_cols_a4
        self.page_orientation = QPageLayout.Orientation.Portrait
        
        # --- 状態管理 ---
        self.app_state = AppState.IDLE
        self.display_mode = 'summary'
        self.title_is_displayed = False
        self.calculator = None
        self.snapping_enabled = False
        self.tracing_enabled = False

        # --- 地図制御 ---
        self.master_bbox = None
        self.map_rotation = 0
        # MODIFIED: 地図のパン操作によるオフセット値を追加
        self.map_offset_x = 0
        self.map_offset_y = 0
        
        # --- 計算設定 (リセット対象) ---
        self.is_split_mode = False
        self.calculation_data = None
        
        self.split_lines = []
        self.current_split_line_points = []
        
        self.sub_area_data = []

        self.default_calc_mode = None
        self.default_landing_cell = None
        self.default_additional_distance = 0.0
        
        self.configuring_area_index = None

        self.label_positions = {}
        self.text_annotations = {}


    def reset_calculation_settings(self):
        self.is_split_mode = False
        self.calculation_data = None
        self.display_mode = 'summary'
        self.title_is_displayed = False
        self.split_lines = []
        self.current_split_line_points = []
        self.sub_area_data = []
        self.default_calc_mode = None
        self.default_landing_cell = None
        self.default_additional_distance = 0.0
        self.configuring_area_index = None
        # MODIFIED: 設定クリア時にオフセットもリセット
        self.map_offset_x = 0
        self.map_offset_y = 0
    
    def get_label_position(self, unique_feature_id):
        return self.label_positions.get(unique_feature_id)

    def set_label_position(self, unique_feature_id, world_coords):
        self.label_positions[unique_feature_id] = world_coords

    def add_text_annotation(self, text, world_pos, font=None, color=None):
        new_id = uuid.uuid4()
        
        if font is None:
            font = QFont("游ゴシック", 10)
            font.setBold(True)
        if color is None:
            color = QColor("black")

        self.text_annotations[new_id] = {
            'text': text, 
            'world_pos': world_pos,
            'font_family': font.family(),
            'font_size': font.pointSize(),
            'font_bold': font.bold(),
            'font_italic': font.italic(),
            'color_rgba': color.getRgb()
        }
        return new_id

    def update_text_annotation_style(self, annotation_id, new_text, new_font, new_color):
        if annotation_id in self.text_annotations:
            self.text_annotations[annotation_id].update({
                'text': new_text,
                'font_family': new_font.family(),
                'font_size': new_font.pointSize(),
                'font_bold': new_font.bold(),
                'font_italic': new_font.italic(),
                'color_rgba': new_color.getRgb()
            })

    def update_text_annotation_position(self, annotation_id, new_world_pos):
        if annotation_id in self.text_annotations:
            self.text_annotations[annotation_id]['world_pos'] = new_world_pos
            
    def remove_text_annotation(self, annotation_id):
        if annotation_id in self.text_annotations:
            del self.text_annotations[annotation_id]

    def remove_all_annotations(self):
        self.text_annotations.clear()
        self.label_positions.clear()
    
    def reset_split_settings(self):
        self.split_lines = []
        self.current_split_line_points = []

    def prepare_sub_areas(self):
        combined_geom = self._get_combined_calculable_geom()
        if combined_geom is None or combined_geom.is_empty:
            raise ValueError("計算対象のポリゴンが見つかりません。")

        if not combined_geom.is_valid:
            combined_geom = combined_geom.buffer(0)
            if not combined_geom.is_valid:
                raise ValueError("計算対象のポリゴンジオメトリが無効です。")

        if not self.split_lines:
            raise ValueError("有効な分割線がありません。")

        splitter = unary_union(self.split_lines)
        
        union_of_lines = unary_union([combined_geom.boundary, splitter])
        
        polygons = list(polygonize(union_of_lines))

        valid_polygons = [p for p in polygons if combined_geom.contains(p.representative_point()) and not p.is_empty]
        
        final_polygons = []
        for poly in valid_polygons:
            if isinstance(poly, MultiPolygon):
                final_polygons.extend(list(poly.geoms))
            elif isinstance(poly, Polygon):
                final_polygons.append(poly)

        if not final_polygons or len(final_polygons) <= 1:
            raise ValueError(
                "区域が正しく分割されませんでした。\n"
                "・分割線は区域を完全に横断していますか？\n"
                "・分割線が区域の境界線と複雑に交差していませんか？"
            )

        final_polygons.sort(key=lambda p: (-p.centroid.y, p.centroid.x))
        self.sub_area_data = []
        for i, poly in enumerate(final_polygons):
            area_name = f'{chr(ord("A") + i)}区域'
            self.sub_area_data.append({
                'id': i + 1, 'name': area_name, 'geom': poly,
                'calc_mode': 'default', 'landing_cell': None,
                'additional_distance': 0.0, 'result': None
            })

    def add_layer(self, layer_info):
        self.layers.insert(0, layer_info)

    def remove_layer(self, index):
        if 0 <= index < len(self.layers):
            layer_to_remove = self.layers[index]
            keys_to_delete = [
                key for key in self.label_positions
                if key[0] == layer_to_remove['path'] and key[1] == layer_to_remove['layer_name']
            ]
            for key in keys_to_delete:
                del self.label_positions[key]
            self.layers.pop(index)

    def move_layer_up(self, index):
        if index > 0: self.layers.insert(index - 1, self.layers.pop(index))

    def move_layer_down(self, index):
        if 0 <= index < len(self.layers) - 1: self.layers.insert(index + 1, self.layers.pop(index))
            
    def set_calc_target_status(self, index, is_target):
        if 0 <= index < len(self.layers): self.layers[index]['is_calc_target'] = is_target

    def update_master_bbox(self):
        self.master_bbox = None
        all_geoms_for_bbox = []
        
        for layer in self.layers:
            if 'features' not in layer or not layer['features']:
                continue

            for feature in layer['features']:
                if 'geometry' not in feature or not feature['geometry']:
                    continue
                try:
                    geom = shape(feature['geometry'])
                    if not geom.is_valid:
                        geom = geom.buffer(0)
                    if geom and not geom.is_empty:
                        all_geoms_for_bbox.append(geom)
                except Exception:
                    continue

        if not all_geoms_for_bbox:
            return

        try:
            master_geom = unary_union(all_geoms_for_bbox)
            if not master_geom.is_empty:
                self.master_bbox = list(master_geom.bounds)
        except Exception as e:
            print(f"マスターBBox結合エラー: {e}")
            self.master_bbox = None

    def determine_layout(self):
        if not self.master_bbox:
            self.grid_rows, self.grid_cols, self.page_orientation, self.map_rotation = self.grid_rows_a4, self.grid_cols_a4, QPageLayout.Orientation.Portrait, 0
            return False, ""
        master_geom = self._get_combined_all_layers_geom()
        info_message, layout_found = "", False
        final_grid_rows, final_grid_cols, final_page_orientation, final_map_rotation = self.grid_rows, self.grid_cols, self.page_orientation, self.map_rotation
        
        if master_geom and not master_geom.is_empty:
            a4_width_m, a4_height_m = self.grid_cols_a4 * self.k_value, self.grid_rows_a4 * self.k_value
            a3_width_m, a3_height_m = self.grid_cols_a3 * self.k_value, self.grid_rows_a3 * self.k_value
            
            optimal_angle_a4 = self._find_optimal_rotation(master_geom, a4_width_m, a4_height_m)
            
            if optimal_angle_a4 is not None:
                final_grid_rows, final_grid_cols, final_page_orientation, final_map_rotation = self.grid_rows_a4, self.grid_cols_a4, QPageLayout.Orientation.Portrait, optimal_angle_a4
                info_message = f"A4縦に収めるため、{optimal_angle_a4}°回転しました。" if optimal_angle_a4 != 0 else "A4縦に収まります。"
                layout_found = True
            else:
                optimal_angle_a3 = self._find_optimal_rotation(master_geom, a3_width_m, a3_height_m)
                if optimal_angle_a3 is not None:
                    final_grid_rows, final_grid_cols, final_page_orientation, final_map_rotation = self.grid_rows_a3, self.grid_cols_a3, QPageLayout.Orientation.Landscape, optimal_angle_a3
                    info_message = "A4サイズに収まらないため、A3モードに切り替えます。"
                    layout_found = True
                else:
                    final_grid_rows, final_grid_cols, final_page_orientation, final_map_rotation = self.grid_rows_a3, self.grid_cols_a3, QPageLayout.Orientation.Landscape, 0
                    info_message = "A3モードでも最適な回転が見つかりませんでした。データの一部が切れて表示される可能性があります。"
                    layout_found = False

        layout_changed = (self.grid_rows != final_grid_rows or self.grid_cols != final_grid_cols or self.map_rotation != final_map_rotation or self.page_orientation != final_page_orientation)
        # MODIFIED: レイアウトが変更されたらパンをリセット
        if layout_changed:
            self.map_offset_x = 0
            self.map_offset_y = 0
            
        self.grid_rows, self.grid_cols, self.page_orientation, self.map_rotation = final_grid_rows, final_grid_cols, final_page_orientation, final_map_rotation
        
        return layout_changed, info_message if layout_changed else ""
        
    def _get_combined_calculable_geom(self):
        all_shapely_polygons = []
        calculable_layers = [layer for layer in self.layers if layer.get('is_calc_target') and layer.get('is_calculable')]
        if not calculable_layers: return None
        for layer in calculable_layers:
            for feature in layer['features']:
                geom_dict = feature.get('geometry')
                if not geom_dict: continue
                try:
                    shapely_geom = shape(geom_dict)
                    if not shapely_geom.is_valid: shapely_geom = shapely_geom.buffer(0)
                    if shapely_geom and not shapely_geom.is_empty:
                        all_shapely_polygons.append(shapely_geom)
                except Exception: continue
        if not all_shapely_polygons: return None
        return unary_union(all_shapely_polygons)

    def _get_combined_all_layers_geom(self):
        all_geoms = []
        for layer in self.layers:
            for feature in layer['features']:
                geom_dict = feature.get('geometry')
                if not geom_dict: continue
                try:
                    shapely_geom = shape(geom_dict)
                    if not shapely_geom.is_valid: shapely_geom = shapely_geom.buffer(0)
                    if shapely_geom and not shapely_geom.is_empty:
                        all_geoms.append(shapely_geom)
                except Exception: continue
        if not all_geoms: return None
        return unary_union(all_geoms)

    def _find_optimal_rotation(self, geom, target_width, target_height):
        if geom is None or geom.is_empty: return None
        for angle in [0, 90] + list(range(5, 90, 5)):
            rotated_geom = rotate(geom, angle, origin='center', use_radians=False)
            min_x, min_y, max_x, max_y = rotated_geom.bounds
            width, height = max_x - min_x, max_y - min_y
            if width <= target_width and height <= target_height: return angle
        return None