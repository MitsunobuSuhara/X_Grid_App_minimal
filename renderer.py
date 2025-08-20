import math
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import (
    QColor, QPen, QBrush, QFont, QPolygonF, QPainterPath, QFontMetrics
)
from PyQt6.QtWidgets import QGraphicsTextItem, QGraphicsSceneMouseEvent
from shapely.geometry import box, shape, Polygon, MultiPolygon, LineString, MultiLineString, Point
from shapely.ops import unary_union, nearest_points

from utils import DEFAULT_STYLE_INFO, _parse_any_color_string
from report_generator import ReportGenerator # NEW: ReportGeneratorをインポート


class DraggableLabelItem(QGraphicsTextItem):
    positionChanged = pyqtSignal(object, QPointF)

    def __init__(self, text, unique_id, is_annotation=False, parent=None):
        super().__init__(text, parent)
        self.unique_id = unique_id
        self.is_annotation = is_annotation
        self.setFlags(
            self.flags() | 
            QGraphicsTextItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setData(0, "draggable_label")

    def paint(self, painter, option, widget):
        if self.isSelected():
            painter.setPen(QPen(QColor("cyan"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())
        
        super().paint(painter, option, widget)


class MapRenderer:
    def __init__(self, scene, project, for_pdf=False):
        self.scene = scene
        self.project = project
        self.for_pdf = for_pdf
        
        if self.for_pdf:
            self.grid_offset_x, self.grid_offset_y = 80, 150
        else:
            self.grid_offset_x, self.grid_offset_y = 60, 40

        self.Z_GRID, self.Z_DATA_LAYERS_BASE, self.Z_AREA_OUTLINE, self.Z_OVERLAYS_BASE = 0, 1, 50, 100
        
        self.grid_items, self.compass_items, self.calculation_items, self.title_items, self.pointer_items, self.annotation_items = [], [], [], [], [], []
        self.in_area_cells_outline, self.temp_splitting_line_item, self.fixed_split_line_items = None, None, []
        self.trace_preview_item = None

        self._setup_drawing_styles()
        self.report_generator = ReportGenerator() # NEW: インスタンスを作成

    def scene_to_world(self, scene_pos):
        params = self._get_transform_parameters()
        if not params:
            return None

        pos_no_offset = scene_pos - QPointF(self.project.map_offset_x, self.project.map_offset_y)
        relative_x = pos_no_offset.x() - params['grid_center_x']
        relative_y = -(pos_no_offset.y() - params['grid_center_y'])
        world_dx = relative_x / params['scale']
        world_dy = relative_y / params['scale']
        unrotated_world_x = params['center_x'] + world_dx
        unrotated_world_y = params['center_y'] + world_dy
        final_world_coords = self._apply_rotation_to_coords([(unrotated_world_x, unrotated_world_y)], inverse=True)
        return final_world_coords[0]

    def world_geom_to_scene_geom(self, world_geom):
        params = self._get_transform_parameters()
        if not params: return None
        def transform_geom_coords(coords):
            rotated_coords = self._apply_rotation_to_coords(coords)
            return [(params['grid_center_x'] + (p[0] - params['center_x']) * params['scale'] + self.project.map_offset_x, params['grid_center_y'] - (p[1] - params['center_y']) * params['scale'] + self.project.map_offset_y) for p in rotated_coords]
        try:
            if isinstance(world_geom, Polygon):
                return Polygon(transform_geom_coords(world_geom.exterior.coords), [transform_geom_coords(i.coords) for i in world_geom.interiors])
            elif isinstance(world_geom, MultiPolygon):
                polys = [Polygon(transform_geom_coords(p.exterior.coords), [transform_geom_coords(i.coords) for i in p.interiors]) for p in world_geom.geoms if p.exterior]
                return MultiPolygon(polys)
            elif isinstance(world_geom, LineString):
                return LineString(transform_geom_coords(world_geom.coords))
            elif isinstance(world_geom, MultiLineString):
                lines = [LineString(transform_geom_coords(line.coords)) for line in world_geom.geoms]
                return MultiLineString(lines)
            elif world_geom.geom_type == 'Point':
                coords = transform_geom_coords([world_geom.coords[0]])
                return shape({'type': 'Point', 'coordinates': coords[0]})

        except Exception as e:
            print(f"シーンジオメトリ変換エラー: {e}")
            return None
        return None
    
    def _get_snap_geometries(self):
        snap_geoms = []
        for layer in self.project.layers:
            for feature in layer['features']:
                geom_dict = feature.get('geometry')
                if not geom_dict: continue
                try:
                    shapely_geom = shape(geom_dict)
                    if not shapely_geom or shapely_geom.is_empty: continue

                    if "Polygon" in shapely_geom.geom_type:
                        snap_geoms.append(shapely_geom.boundary)
                    elif "LineString" in shapely_geom.geom_type or "Point" in shapely_geom.geom_type:
                        snap_geoms.append(shapely_geom)
                except Exception:
                    continue
        return snap_geoms

    def find_snap_point(self, scene_pos, scene_tolerance):
        if not self.project.layers: return None, None
        params = self._get_transform_parameters()
        if not params or params.get('scale') == 0: return None, None

        world_tolerance = scene_tolerance / params['scale']
        mouse_world_coords = self.scene_to_world(scene_pos)
        if not mouse_world_coords: return None, None
        
        mouse_world_point = Point(mouse_world_coords)
        
        snap_geoms = self._get_snap_geometries()
        if not snap_geoms: return None, None
        
        try:
            combined_geoms = unary_union(snap_geoms)
            if combined_geoms.is_empty: return None, None
        except Exception:
            return None, None 

        p1, p2 = nearest_points(combined_geoms, mouse_world_point)
        
        if p1.distance(p2) < world_tolerance:
            scene_snap_geom = self.world_geom_to_scene_geom(p1)
            if scene_snap_geom:
                snapped_on_geom = None
                min_dist = float('inf')
                for geom in snap_geoms:
                    dist = p1.distance(geom)
                    if dist < min_dist:
                        min_dist = dist
                        snapped_on_geom = geom
                
                return QPointF(scene_snap_geom.x, scene_snap_geom.y), snapped_on_geom
        
        return None, None

    def find_trace_points(self, trace_geom, start_point_world, end_point_world):
        if not isinstance(trace_geom, (LineString, MultiLineString)):
            return None

        lines_to_trace = list(trace_geom.geoms) if isinstance(trace_geom, MultiLineString) else [trace_geom]

        for line in lines_to_trace:
            try:
                start_dist = line.project(start_point_world)
                end_dist = line.project(end_point_world)

                if abs(start_dist - end_dist) < 1e-9: continue

                coords = list(line.coords)
                
                if start_dist > end_dist:
                    start_dist, end_dist = end_dist, start_dist
                    coords.reverse()

                trace_coords = []
                in_segment = False
                for i in range(len(coords)):
                    p_dist = line.project(Point(coords[i]))
                    
                    if p_dist >= start_dist and p_dist <= end_dist:
                        if not in_segment:
                            trace_coords.append(start_point_world.coords[0])
                            if p_dist > start_dist:
                                trace_coords.append(coords[i])
                            in_segment = True
                        else:
                            trace_coords.append(coords[i])
                    elif in_segment:
                        break
                
                trace_coords.append(end_point_world.coords[0])

                if len(trace_coords) >= 2:
                    if Point(trace_coords[0]).equals(start_point_world):
                        trace_coords.pop(0)

                    return [QPointF(p.x, p.y) for p in [self.world_geom_to_scene_geom(Point(c)) for c in trace_coords] if p]

            except Exception as e:
                print(f"Trace error: {e}")
                continue

        return None
    
    def is_cell_on_boundary(self, row, col, target_geom):
        if not target_geom: return False
        
        cell_world_poly = self._get_cell_world_polygon(row, col)
        if not cell_world_poly: return False

        return cell_world_poly.intersects(target_geom.boundary)

    def _get_cell_world_polygon(self, row, col):
        params = self._get_transform_parameters()
        if not params: return None

        cs = self.project.cell_size_on_screen
        scene_x1 = self.grid_offset_x + col * cs
        scene_y1 = self.grid_offset_y + row * cs
        scene_poly = box(scene_x1, scene_y1, scene_x1 + cs, scene_y1 + cs)
        
        world_coords = []
        for sx, sy in list(scene_poly.exterior.coords):
            world_coord = self.scene_to_world(QPointF(sx, sy))
            if world_coord:
                world_coords.append(world_coord)
        
        if len(world_coords) < 4: return None
        return Polygon(world_coords)

    def _handle_label_moved(self, unique_id, new_scene_pos):
        item_rect = QFontMetrics(self.fonts['data_bold']).boundingRect("Dummy")
        center_pos = new_scene_pos + QPointF(item_rect.width() / 2, item_rect.height() / 2)
        world_pos = self.scene_to_world(center_pos)
        if world_pos:
            self.project.set_label_position(unique_id, world_pos)
            
    def _handle_text_annotation_moved(self, unique_id, new_scene_pos):
        item = next((item for item in self.annotation_items if hasattr(item, 'unique_id') and item.unique_id == unique_id), None)
        if item:
            item_rect = item.boundingRect()
            center_pos = new_scene_pos + QPointF(item_rect.width() / 2, item_rect.height() / 2)
            world_pos = self.scene_to_world(center_pos)
            if world_pos:
                self.project.update_text_annotation_position(unique_id, world_pos)

    def get_grid_rect(self):
        width = self.project.grid_cols * self.project.cell_size_on_screen
        height = self.project.grid_rows * self.project.cell_size_on_screen
        return QRectF(self.grid_offset_x, self.grid_offset_y, width, height)

    def get_full_content_rect(self):
        if not self.scene or not self.scene.items():
            grid_width = self.project.grid_cols * self.project.cell_size_on_screen
            grid_height = self.project.grid_rows * self.project.cell_size_on_screen
            min_x = self.grid_offset_x - 80
            min_y = self.grid_offset_y - 150
            width = grid_width + 150
            height = grid_height + 300
            return QRectF(min_x, min_y, width, height)

        content_rect = self.scene.itemsBoundingRect()
        
        grid_rect = self.get_grid_rect()
        if grid_rect.isValid():
            content_rect = content_rect.united(grid_rect)
        
        return content_rect.adjusted(-20, -20, 20, 20)
        
    def full_redraw(self, hide_pointers=False, hide_calc_results=False, for_pdf=False):
        self.for_pdf = for_pdf
        self.clear_all_graphics_items()

        is_summary_mode = (self.project.is_split_mode and 
                           self.project.display_mode == 'summary' and 
                           self.project.calculation_data is not None)

        if is_summary_mode:
            self.draw_summary_view(for_pdf=for_pdf)
        else:
            self.draw_map_view(hide_pointers, hide_calc_results, for_pdf)

    def draw_map_view(self, hide_pointers=False, hide_calc_results=False, for_pdf=False):
        self.draw_grid()
        self.redraw_all_layers()
        self.draw_text_annotations()
        if not hide_pointers:
            self.draw_all_pointers()
        if self.project.calculation_data and not hide_calc_results:
            self.draw_calculation_results()
        self.draw_split_lines()
        self.update_area_outline()
        if self.project.title_is_displayed:
            subtitle = self.project.calculation_data.get('subtitle_text', '')
            self.draw_title(subtitle)
            
    def draw_summary_view(self, for_pdf=False):
        self.draw_summary_page_contents(for_pdf=for_pdf)

    def clear_all_graphics_items(self):
        self.scene.clear()
        
        if not self.for_pdf and self.scene.views():
            view = self.scene.views()[0]
            view.clear_snap_indicator()
            view.last_trace_geom = None

        self.grid_items.clear()
        self.compass_items.clear()
        self.calculation_items.clear()
        self.title_items.clear()
        self.pointer_items.clear()
        self.annotation_items.clear()
        self.in_area_cells_outline, self.temp_splitting_line_item = None, None
        self.fixed_split_line_items.clear()
        
        for layer in self.project.layers:
            layer['graphics_items'] = []
            
    def clear_all_calculation_graphics(self):
        for item_list in [self.calculation_items, self.title_items]:
            for item in item_list:
                if item.scene(): self.scene.removeItem(item)
            item_list.clear()
        if self.in_area_cells_outline and self.in_area_cells_outline.scene():
            self.scene.removeItem(self.in_area_cells_outline)
        self.in_area_cells_outline = None
        
        self.clear_all_pointers()
        self.clear_temporary_splitting_line()
        for item in self.fixed_split_line_items:
            if item.scene(): self.scene.removeItem(item)
        self.fixed_split_line_items.clear()

        self.project.calculation_data = None
        self.project.title_is_displayed = False
        self.draw_grid()

    def redraw_all_layers(self):
        for layer in self.project.layers:
            for item in layer.get('graphics_items', []):
                if item and item.scene():
                    self.scene.removeItem(item)
            layer['graphics_items'] = []
        
        if not self.project.master_bbox:
            self.draw_compass()
            return
        
        for i, layer in enumerate(reversed(self.project.layers)):
            z_value = self.Z_DATA_LAYERS_BASE + i
            for feature in layer['features']:
                geom_dict = feature.get('geometry')
                if not geom_dict: continue
                shapely_geom = shape(geom_dict)
                if shapely_geom.is_empty: continue
                self._draw_feature(feature, shapely_geom, layer, z_value)

        self.draw_compass()
        self.draw_area_labels()

    def _draw_feature(self, feature, shapely_geom, layer_info, z_value):
        try:
            style = self._get_feature_style(feature, layer_info)
            
            pen = QPen()
            pen.setColor(style['line_color'])
            pen.setStyle(style['pen_style'])

            pen_width_in_scene_units = style['line_width'] * 5.0
            pen.setWidthF(pen_width_in_scene_units)
            pen.setCosmetic(False)

            brush = QBrush(style['fill_color'])
            
            scene_geom = self.world_geom_to_scene_geom(shapely_geom)
            if not scene_geom or scene_geom.is_empty: return

            def create_path(geom):
                path = QPainterPath()
                if geom.geom_type == 'Polygon':
                    path.addPolygon(QPolygonF([QPointF(x,y) for x,y in geom.exterior.coords]))
                    for interior in geom.interiors: path.addPolygon(QPolygonF([QPointF(x,y) for x,y in interior.coords]))
                elif geom.geom_type == 'MultiPolygon':
                    for poly in geom.geoms:
                        path.addPolygon(QPolygonF([QPointF(x,y) for x,y in poly.exterior.coords]))
                        for interior in poly.interiors: path.addPolygon(QPolygonF([QPointF(x,y) for x,y in interior.coords]))
                elif geom.geom_type == 'LineString':
                    q_points = [QPointF(x,y) for x,y in geom.coords]
                    if len(q_points) > 1: path.moveTo(q_points[0]); [path.lineTo(p) for p in q_points[1:]]
                elif geom.geom_type == 'MultiLineString':
                    for line in geom.geoms:
                        q_points = [QPointF(x,y) for x,y in line.coords]
                        if len(q_points) > 1: path.moveTo(q_points[0]); [path.lineTo(p) for p in q_points[1:]]
                return path

            path = create_path(scene_geom)
            if 'Polygon' in shapely_geom.geom_type:
                path.setFillRule(Qt.FillRule.OddEvenFill)
                item = self.scene.addPath(path, pen, brush)
            else:
                item = self.scene.addPath(path, pen)
            if item:
                item.setZValue(z_value)
                layer_info['graphics_items'].append(item)

                props = feature.get('properties', {})
                meter_value = props.get('meter')

                if meter_value is not None and ('LineString' in shapely_geom.geom_type or 'MultiLineString' in shapely_geom.geom_type):
                    try:
                        geoms_to_label = shapely_geom.geoms if shapely_geom.geom_type == 'MultiLineString' else [shapely_geom]
                        
                        for i, single_line_geom in enumerate(geoms_to_label):
                            if single_line_geom.is_empty: continue
                            
                            unique_id = (layer_info['path'], layer_info['layer_name'], feature.get('id', -1), i)
                            world_pos = self.project.get_label_position(unique_id)
                            
                            if world_pos is None:
                                world_pos = (single_line_geom.centroid.x, single_line_geom.centroid.y)

                            scene_label_pos = self.world_geom_to_scene_geom(shape({'type': 'Point', 'coordinates': world_pos}))
                            if not scene_label_pos: continue

                            label_text = f"{meter_value}m"
                            text_item = DraggableLabelItem(label_text, unique_id, is_annotation=False)
                            text_item.setDefaultTextColor(self.colors['dark'])
                            text_item.setFont(self.fonts['data_bold'])
                            
                            text_rect = text_item.boundingRect()
                            text_item.setPos(scene_label_pos.x - text_rect.width() / 2, scene_label_pos.y - text_rect.height() / 2)
                            
                            text_item.setZValue(z_value + 1)
                            self.scene.addItem(text_item)
                            
                            text_item.positionChanged.connect(self._handle_label_moved)

                            layer_info['graphics_items'].append(text_item)
                            
                    except Exception as text_e:
                        print(f"警告: メートル属性テキスト描画をスキップ。理由: {text_e}")

        except Exception as e:
            print(f"警告: フィーチャ描画をスキップ。理由: {e}")

    def draw_text_annotations(self):
        for item in self.annotation_items:
            if item.scene():
                self.scene.removeItem(item)
        self.annotation_items.clear()
        
        for unique_id, data in self.project.text_annotations.items():
            world_pos = data['world_pos']
            text = data['text']
            
            scene_pos_geom = self.world_geom_to_scene_geom(shape({'type': 'Point', 'coordinates': world_pos}))
            if not scene_pos_geom: continue

            font = QFont(data['font_family'], data['font_size'])
            font.setBold(data['font_bold'])
            font.setItalic(data['font_italic'])
            color = QColor(*data['color_rgba'])
            
            text_item = DraggableLabelItem(text, unique_id, is_annotation=True)
            text_item.setDefaultTextColor(color)
            text_item.setFont(font)
            
            text_rect = text_item.boundingRect()
            text_item.setPos(scene_pos_geom.x - text_rect.width() / 2, scene_pos_geom.y - text_rect.height() / 2)
            
            text_item.setZValue(self.Z_OVERLAYS_BASE + 10)
            self.scene.addItem(text_item)
            
            text_item.positionChanged.connect(self._handle_text_annotation_moved)
            self.annotation_items.append(text_item)

    def _setup_drawing_styles(self, for_summary_pdf=False):
        if for_summary_pdf:
            self.fonts = {
                'title': QFont("游ゴシック", 20, QFont.Weight.Bold), 
                'result': QFont("游ゴシック", 16, QFont.Weight.Bold),
                'section_header': QFont("游ゴシック", 16, QFont.Weight.Bold),
                'data': QFont("游ゴシック", 13), 
                'data_bold': QFont("游ゴシック", 13, QFont.Weight.Bold),
                'note': QFont("游ゴシック", 12, QFont.Weight.Normal),
                'total': QFont("游ゴシック", 10, QFont.Weight.Bold), 
                'scale': QFont("游ゴシック", 10), 
                'highlight': QFont("游ゴシック", 10, QFont.Weight.Bold)
            }
        else:
            self.fonts = {
                'title': QFont("游ゴシック", 16, QFont.Weight.Bold), 
                'result': QFont("游ゴシック", 12, QFont.Weight.Bold),
                'section_header': QFont("游ゴシック", 12, QFont.Weight.Bold),
                'header': QFont("游ゴシック", 9, QFont.Weight.Bold), 
                'data': QFont("游ゴシック", 9), 
                'data_bold': QFont("游ゴシック", 9, QFont.Weight.Bold),
                'note': QFont("游ゴシック", 9, QFont.Weight.Normal),
                'total': QFont("游ゴシック", 9, QFont.Weight.Bold), 
                'scale': QFont("游ゴシック", 10), 
                'highlight': QFont("游ゴシック", 9, QFont.Weight.Bold)
            }
        self.colors = {'normal': QColor("#333333"), 'dark': QColor("black"), 'highlight': QColor("red")}

    def draw_grid(self):
        for item in self.grid_items:
            if item.scene(): self.scene.removeItem(item)
        self.grid_items.clear()
        pen = QPen(QColor(220, 220, 222))
        end_x, end_y = self.grid_offset_x + self.project.grid_cols * self.project.cell_size_on_screen, self.grid_offset_y + self.project.grid_rows * self.project.cell_size_on_screen
        for r in range(self.project.grid_rows + 1):
            y = self.grid_offset_y + r * self.project.cell_size_on_screen
            line = self.scene.addLine(self.grid_offset_x, y, end_x, y, pen); line.setZValue(self.Z_GRID); self.grid_items.append(line)
        for c in range(self.project.grid_cols + 1):
            x = self.grid_offset_x + c * self.project.cell_size_on_screen
            line = self.scene.addLine(x, self.grid_offset_y, x, end_y, pen); line.setZValue(self.Z_GRID); self.grid_items.append(line)

    def draw_compass(self):
        for item in self.compass_items:
            if item.scene(): self.scene.removeItem(item)
        self.compass_items.clear()
        if not self.project.layers: return
        center_x, center_y, size = self.grid_offset_x + 60, self.grid_offset_y + 60, 35
        
        group = self.scene.createItemGroup([])
        
        ns_poly = QPolygonF([QPointF(0, -size / 2), QPointF(size / 10, 0), QPointF(0, size / 2), QPointF(-size / 10, 0)])
        ew_poly = QPolygonF([QPointF(size / 2, 0), QPointF(0, size / 10), QPointF(-size / 2, 0), QPointF(0, -size / 10)])
        group.addToGroup(self.scene.addPolygon(ew_poly, QPen(Qt.PenStyle.NoPen), QBrush(QColor(150, 150, 150))))
        group.addToGroup(self.scene.addPolygon(ns_poly, QPen(Qt.PenStyle.NoPen), QBrush(QColor(50, 50, 50))))

        text_item = self.scene.addText("N", QFont("游ゴシック", 10, QFont.Weight.Bold))
        text_item.setDefaultTextColor(self.colors['dark'])
        group.addToGroup(text_item)

        text_rect = text_item.boundingRect()
        text_item.setPos(-text_rect.width() / 2, -size / 2 - text_rect.height() + 3)

        group.setPos(center_x, center_y)
        group.setRotation(-self.project.map_rotation)
        group.setZValue(self.Z_OVERLAYS_BASE + 1)
        
        self.compass_items.append(group)

    def draw_splitting_line(self, points, current_mouse_pos=None, trace_points=None):
        self.clear_temporary_splitting_line()
        if not points: return
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)

        if trace_points:
            pen = QPen(QColor("cyan"), 3, Qt.PenStyle.SolidLine)
            pen.setCosmetic(True)
            trace_path = QPainterPath(points[-1])
            for p in trace_points:
                trace_path.lineTo(p)
            self.trace_preview_item = self.scene.addPath(trace_path, pen)
            self.trace_preview_item.setZValue(self.Z_OVERLAYS_BASE + 52)
            
            if current_mouse_pos:
                path.lineTo(trace_points[-1])

        elif current_mouse_pos:
            path.lineTo(current_mouse_pos)
            
        pen = QPen(QColor("magenta"), 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        self.temp_splitting_line_item = self.scene.addPath(path, pen)
        self.temp_splitting_line_item.setZValue(self.Z_OVERLAYS_BASE + 51)
    
    def clear_temporary_splitting_line(self):
        if self.temp_splitting_line_item and self.temp_splitting_line_item.scene():
            self.scene.removeItem(self.temp_splitting_line_item)
        if self.trace_preview_item and self.trace_preview_item.scene():
            self.scene.removeItem(self.trace_preview_item)
        self.temp_splitting_line_item = None
        self.trace_preview_item = None

    def draw_split_lines(self):
        for item in self.fixed_split_line_items:
            if item.scene(): self.scene.removeItem(item)
        self.fixed_split_line_items.clear()
        if not self.project.split_lines: return
        pen = QPen(QColor(255, 193, 7), 3, Qt.PenStyle.SolidLine)
        pen.setCosmetic(True)
        world_geom = self.project._get_combined_calculable_geom()
        if not world_geom: return
        for line in self.project.split_lines:
            try: clipped_line = line.intersection(world_geom)
            except Exception as e: print(f"分割線のクリッピングエラー: {e}"); clipped_line = line
            
            scene_line = self.world_geom_to_scene_geom(clipped_line)
            if not scene_line or scene_line.is_empty: continue

            geoms_to_draw = scene_line.geoms if hasattr(scene_line, 'geoms') else [scene_line]
            for geom in geoms_to_draw:
                q_points = [QPointF(x, y) for x, y in geom.coords]
                if len(q_points) > 1:
                    path = QPainterPath(q_points[0])
                    for p in q_points[1:]: path.lineTo(p)
                    item = self.scene.addPath(path, pen)
                    item.setZValue(self.Z_OVERLAYS_BASE + 50); self.fixed_split_line_items.append(item)

    def draw_area_labels(self):
        if not self.project.is_split_mode or not self.project.sub_area_data: return
        for area in self.project.sub_area_data:
            centroid_world = area['geom'].centroid
            centroid_scene_geom = self.world_geom_to_scene_geom(centroid_world)
            if not centroid_scene_geom: continue
            
            font = QFont("游ゴシック", 12, QFont.Weight.Bold)
            text_item = self._add_aligned_text(area['name'], font, QColor("black"), QPointF(centroid_scene_geom.x, centroid_scene_geom.y), Qt.AlignmentFlag.AlignCenter)
            text_item.setZValue(self.Z_OVERLAYS_BASE + 5)
            self.calculation_items.append(text_item)
            bg_item = self.scene.addRect(text_item.boundingRect(), QPen(Qt.PenStyle.NoPen), QBrush(QColor(255, 255, 255, 180)))
            bg_item.setPos(text_item.pos()); bg_item.setZValue(text_item.zValue() - 0.1); self.calculation_items.append(bg_item)

    def update_area_outline(self):
        if self.in_area_cells_outline and self.in_area_cells_outline.scene():
            self.scene.removeItem(self.in_area_cells_outline)
        self.in_area_cells_outline = None
        
        in_area_cells = self.project.calculator.get_in_area_cells()
        if not in_area_cells: return

        cell_polygons = [box(self.grid_offset_x + c * self.project.cell_size_on_screen, self.grid_offset_y + r * self.project.cell_size_on_screen, self.grid_offset_x + (c + 1) * self.project.cell_size_on_screen, self.grid_offset_y + (r + 1) * self.project.cell_size_on_screen) for r, c in in_area_cells]
        if not cell_polygons: return
        
        merged_cells_geom, outline_path = unary_union(cell_polygons), QPainterPath()
        boundary = merged_cells_geom.boundary
        geoms_to_draw = boundary.geoms if hasattr(boundary, 'geoms') else [boundary]
        for line in geoms_to_draw:
            coords = list(line.coords)
            if len(coords) > 1:
                q_points = [QPointF(p[0], p[1]) for p in coords]
                outline_path.moveTo(q_points[0])
                for p in q_points[1:]:
                    outline_path.lineTo(p)

        outline_pen = QPen(QColor(0, 80, 200, 150), 3, Qt.PenStyle.DashDotLine)
        
        self.in_area_cells_outline = self.scene.addPath(outline_path, outline_pen)
        if self.in_area_cells_outline:
            self.in_area_cells_outline.setZValue(self.Z_AREA_OUTLINE)

    def draw_landing_pointer(self, landing_cell, area_index, is_default_single_mode=False):
        row, col = landing_cell
        
        point_size = self.project.cell_size_on_screen * (0.15 if self.for_pdf else 0.5)

        center_x = self.grid_offset_x + col * self.project.cell_size_on_screen + self.project.cell_size_on_screen / 2
        center_y = self.grid_offset_y + row * self.project.cell_size_on_screen + self.project.cell_size_on_screen / 2
        
        color = QColor("red")
        if not self.for_pdf:
            if not is_default_single_mode and area_index is not None:
                colors = [QColor("blue"), QColor("green"), QColor("purple"), QColor(255, 165, 0), QColor(139, 69, 19)]
                color = colors[area_index % len(colors)]
            
        pointer_item = self.scene.addEllipse(center_x - point_size / 2, center_y - point_size / 2, point_size, point_size, QPen(color, 1), QBrush(color))
        pointer_item.setZValue(self.Z_OVERLAYS_BASE + 2); self.pointer_items.append(pointer_item)

    def clear_all_pointers(self):
        for item in self.pointer_items:
            if item.scene(): self.scene.removeItem(item)
        self.pointer_items.clear()

    def pointer_items_visible(self, visible):
        for item in self.pointer_items:
            item.setVisible(visible)

    def draw_all_pointers(self):
        self.clear_all_pointers()
        
        if not self.project.is_split_mode:
             if self.project.default_landing_cell:
                self.draw_landing_pointer(self.project.default_landing_cell, None, is_default_single_mode=True)
        elif self.project.is_split_mode:
            if self.project.display_mode == 'summary':
                for i, area in enumerate(self.project.sub_area_data):
                    if area['landing_cell']:
                        self.draw_landing_pointer(area['landing_cell'], area['id'] - 1)
            elif 'area_' in self.project.display_mode:
                try:
                    area_id = int(self.project.display_mode.split('_')[1])
                    area_data = next((item for item in self.project.sub_area_data if item["id"] == area_id), None)
                    if area_data and area_data.get('landing_cell'):
                        self.draw_landing_pointer(area_data['landing_cell'], area_data['id'] - 1)
                except (ValueError, IndexError):
                    pass

    def draw_title(self, subtitle_text):
        for item in self.title_items:
            if item.scene(): self.scene.removeItem(item)
        self.title_items.clear()
        
        if not subtitle_text: return False

        y_pos = self.grid_offset_y - 145
        title_font = self.fonts['title']
        
        if self.project.display_mode == 'summary':
            is_split_mode = self.project.is_split_mode and len(self.project.sub_area_data) > 1
            title_text = f"{subtitle_text}  平均集材距離計算表 (総括)" if is_split_mode else f"{subtitle_text}  平均集材距離計算表"
        elif 'area_' in self.project.display_mode:
            try:
                area_id = int(self.project.display_mode.split('_')[1])
                area_name = next((area['name'] for area in self.project.sub_area_data if area['id'] == area_id), f"エリア{area_id}")
                title_text = f"{subtitle_text} - {area_name}  平均集材距離計算表"
            except (ValueError, IndexError):
                title_text = f"{subtitle_text}  平均集材距離計算表"
        else:
            title_text = f"{subtitle_text}  平均集材距離計算表"
            
        title_item = self._add_aligned_text(title_text, title_font, self.colors['dark'], QPointF(self.grid_offset_x, y_pos), Qt.AlignmentFlag.AlignLeft)
        title_item.setZValue(self.Z_OVERLAYS_BASE + 100)
        self.title_items.append(title_item)
        
        metrics = QFontMetrics(title_font)
        underline_text = title_text
        if " (総括)" in underline_text: underline_text = underline_text.replace(" (総括)", "")
        if "  平均集材距離計算表" in underline_text: underline_text = underline_text.replace("  平均集材距離計算表", "")
        
        subtitle_width = metrics.horizontalAdvance(underline_text)
        underline_y = y_pos + title_item.boundingRect().height()
        
        line1 = self.scene.addLine(self.grid_offset_x, underline_y + 1, self.grid_offset_x + subtitle_width, underline_y + 1, QPen(self.colors['dark']))
        line2 = self.scene.addLine(self.grid_offset_x, underline_y + 3, self.grid_offset_x + subtitle_width, underline_y + 3, QPen(self.colors['dark']))
        line1.setZValue(self.Z_OVERLAYS_BASE + 100)
        line2.setZValue(self.Z_OVERLAYS_BASE + 100)
        self.title_items.extend([line1, line2])
        
        return True

    def draw_calculation_results(self):
        for item in self.calculation_items:
            if item.scene(): self.scene.removeItem(item)
        self.calculation_items = []
        if not self.project.calculation_data: return
        data_to_draw = None
        if self.project.display_mode == 'summary':
            data_to_draw = self.project.calculation_data.get('summary_result')
        elif 'area_' in self.project.display_mode:
            try:
                area_id = int(self.project.display_mode.split('_')[1])
                area_data = next((item for item in self.project.sub_area_data if item["id"] == area_id), None)
                if area_data: data_to_draw = area_data['result']
            except (ValueError, IndexError):
                data_to_draw = None

        if not data_to_draw: return
        self._draw_dots()
        self._draw_calculation_tables(data_to_draw)
        self._draw_calculation_header()
        self._draw_final_result(data_to_draw)
        for item in self.calculation_items: 
            item.setZValue(item.zValue() + self.Z_OVERLAYS_BASE)

    def _draw_dots(self):
        split_colors, default_color, cells_to_draw = [QColor(255,0,0,150), QColor(0,128,0,150), QColor(0,0,255,150), QColor(255,165,0,150), QColor(128,0,128,150), QColor(0,128,128,150)], QColor(160,160,160,150), []
        if self.project.is_split_mode and self.project.display_mode == 'summary':
            for area_data in self.project.sub_area_data:
                color = split_colors[(area_data['id'] - 1) % len(split_colors)]
                if area_data.get('result'): cells_to_draw.extend([(cell, color) for cell in area_data['result']['in_area_cells']])
        else:
            area_data_list = []
            if self.project.is_split_mode:
                try:
                    area_id = int(self.project.display_mode.split('_')[1])
                    area = next((item for item in self.project.sub_area_data if item["id"] == area_id), None)
                    if area: area_data_list.append(area)
                except (ValueError, IndexError):
                    pass 
            else: 
                area_data_list = self.project.sub_area_data
            
            for area_data in area_data_list:
                if area_data and area_data.get('result'): cells_to_draw.extend([(cell, default_color) for cell in area_data['result']['in_area_cells']])
        
        for (r, c), color in cells_to_draw:
            pen, brush = QPen(color), QBrush(color)
            center_x, center_y, dot_size = self.grid_offset_x + c*self.project.cell_size_on_screen + self.project.cell_size_on_screen/2, self.grid_offset_y + r*self.project.cell_size_on_screen + self.project.cell_size_on_screen/2, self.project.cell_size_on_screen * 0.15
            dot_item = self.scene.addEllipse(center_x - dot_size/2, center_y - dot_size/2, dot_size, dot_size, pen, brush)
            dot_item.setZValue(self.Z_OVERLAYS_BASE - 1); self.calculation_items.append(dot_item)

    def _draw_calculation_tables(self, calc_data):
        v_table_x, col_widths_v, h_table_y, row_heights_h = self.grid_offset_x + self.project.grid_cols*self.project.cell_size_on_screen + 0, [40, 35, 45], self.grid_offset_y + self.project.grid_rows*self.project.cell_size_on_screen + 5, [50, 40, 50]
        pen, v_table_y_end, h_table_x_end = QPen(QColor(180, 180, 180)), self.grid_offset_y + self.project.grid_rows*self.project.cell_size_on_screen, self.grid_offset_x + self.project.grid_cols*self.project.cell_size_on_screen
        self.calculation_items.append(self.scene.addRect(v_table_x, self.grid_offset_y, sum(col_widths_v), v_table_y_end-self.grid_offset_y, pen))
        self.calculation_items.append(self.scene.addRect(self.grid_offset_x, h_table_y, h_table_x_end-self.grid_offset_x, sum(row_heights_h), pen))
        self.calculation_items.append(self.scene.addRect(v_table_x, h_table_y, sum(col_widths_v), sum(row_heights_h), pen))
        current_x = v_table_x
        for w in col_widths_v[:-1]: current_x += w; self.calculation_items.append(self.scene.addLine(current_x, self.grid_offset_y, current_x, v_table_y_end, pen))
        for r in range(self.project.grid_rows): self.calculation_items.append(self.scene.addLine(v_table_x, self.grid_offset_y + r*self.project.cell_size_on_screen, v_table_x+sum(col_widths_v), self.grid_offset_y + r*self.project.cell_size_on_screen, pen))
        current_y = h_table_y
        for h in row_heights_h[:-1]: current_y += h; self.calculation_items.append(self.scene.addLine(self.grid_offset_x, current_y, h_table_x_end, current_y, pen))
        for c in range(self.project.grid_cols): self.calculation_items.append(self.scene.addLine(self.grid_offset_x + c*self.project.cell_size_on_screen, h_table_y, self.grid_offset_x + c*self.project.cell_size_on_screen, h_table_y + sum(row_heights_h), pen))
        self.calculation_items.append(self.scene.addLine(v_table_x + col_widths_v[0], h_table_y, v_table_x + col_widths_v[0], h_table_y + sum(row_heights_h), pen))
        self.calculation_items.append(self.scene.addLine(v_table_x + col_widths_v[0] + col_widths_v[1], h_table_y, v_table_x + col_widths_v[0] + col_widths_v[1], h_table_y + sum(row_heights_h), pen))
        self.calculation_items.append(self.scene.addLine(v_table_x, h_table_y + row_heights_h[0], v_table_x + sum(col_widths_v), h_table_y + row_heights_h[0], pen))
        self.calculation_items.append(self.scene.addLine(v_table_x, h_table_y + row_heights_h[0] + row_heights_h[1], v_table_x + sum(col_widths_v), h_table_y + row_heights_h[0] + row_heights_h[1], pen))
        headers_v_data, current_x = [("①", "走行\n(縦)\n距離"), ("②", "度数"), ("③", "①×②")], v_table_x
        for i, (num, text) in enumerate(headers_v_data): self.calculation_items.append(self._add_aligned_text(num, self.fonts['header'], self.colors['normal'], QPointF(current_x + col_widths_v[i]/2, self.grid_offset_y - 110 + 15), Qt.AlignmentFlag.AlignHCenter)); self.calculation_items.append(self._add_aligned_text(text, self.fonts['header'], self.colors['normal'], QPointF(current_x + col_widths_v[i]/2, self.grid_offset_y - 110 + 45), Qt.AlignmentFlag.AlignHCenter)); current_x += col_widths_v[i]
        
        landing_row = calc_data.get('landing_row', -1)
        row_counts = calc_data.get('row_counts', {})
        
        active_rows = [r for r, count in row_counts.items() if count > 0]
        if landing_row != -1 and landing_row not in active_rows:
            active_rows.append(landing_row)

        if active_rows:
            min_r, max_r = min(active_rows), max(active_rows)
            
            for r in range(min_r, max_r + 1):
                is_hl = (r == landing_row)
                count = row_counts.get(r, 0)
                font = self.fonts['highlight'] if is_hl else self.fonts['data']
                color = self.colors['highlight'] if is_hl else self.colors['normal']
                
                distance = abs(r - landing_row)
                vals = [distance, count, distance * count]
                
                current_x = v_table_x
                for i, val in enumerate(vals):
                    self.calculation_items.append(self._add_aligned_text(
                        str(val), 
                        font, 
                        color, 
                        QPointF(
                            current_x + col_widths_v[i]/2,
                            self.grid_offset_y + r*self.project.cell_size_on_screen + self.project.cell_size_on_screen/2
                        )
                    ))
                    current_x += col_widths_v[i]

                headers_h_data, current_y = [("④", "横取\n(横)\n距離"), ("⑤", "度数"), ("⑥", "④×⑤")], h_table_y
        for i, (num, text) in enumerate(headers_h_data): self.calculation_items.append(self._add_aligned_text(num, self.fonts['header'], self.colors['normal'], QPointF(self.grid_offset_x - 65, current_y + row_heights_h[i]/2), Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)); self.calculation_items.append(self._add_aligned_text(text, self.fonts['header'], self.colors['normal'], QPointF(self.grid_offset_x - 60, current_y + row_heights_h[i]/2), Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)); current_y += row_heights_h[i]
        
        landing_col = calc_data.get('landing_col', -1)
        col_counts = calc_data.get('col_counts', {})
        
        active_cols = [c for c, count in col_counts.items() if count > 0]
        if landing_col != -1 and landing_col not in active_cols:
            active_cols.append(landing_col)

        if active_cols:
            min_c, max_c = min(active_cols), max(active_cols)
            
            for c in range(min_c, max_c + 1):
                is_hl = (c == landing_col)
                count = col_counts.get(c, 0)
                font = self.fonts['highlight'] if is_hl else self.fonts['data']
                color = self.colors['highlight'] if is_hl else self.colors['normal']
                
                distance = abs(c - landing_col)
                vals = [distance, count, distance * count]
                
                current_y = h_table_y
                for i, val in enumerate(vals):
                    self.calculation_items.append(self._add_aligned_text(
                        str(val), 
                        font, 
                        color, 
                        QPointF(
                            self.grid_offset_x + c * self.project.cell_size_on_screen + self.project.cell_size_on_screen / 2,
                            current_y + row_heights_h[i] / 2
                        )
                    ))
                    current_y += row_heights_h[i]

        total_cells_data = [("合計", None, v_table_x, h_table_y, col_widths_v[0], row_heights_h[0]), ("⑧", str(calc_data['total_degree']), v_table_x, h_table_y + row_heights_h[0], col_widths_v[0], row_heights_h[1]), ("⑦", str(calc_data['total_product_h']), v_table_x, h_table_y + sum(row_heights_h[:2]), col_widths_v[0], row_heights_h[2]), ("⑧", str(calc_data['total_degree']), v_table_x + col_widths_v[0], h_table_y, col_widths_v[1], row_heights_h[0]), ("⑨", str(calc_data['total_product_v']), v_table_x + sum(col_widths_v[:2]), h_table_y, col_widths_v[2], row_heights_h[0])]
        for symbol, value, x, y, w, h in total_cells_data:
            if value is None: self.calculation_items.append(self._add_aligned_text(symbol, self.fonts['total'], self.colors['normal'], QPointF(x + w/2, y + h/2)))
            else: self.calculation_items.append(self._add_aligned_text(symbol, self.fonts['total'], self.colors['normal'], QPointF(x + w/2, y + h/3))); self.calculation_items.append(self._add_aligned_text(value, self.fonts['total'], self.colors['normal'], QPointF(x + w/2, y + h*2/3)))

    def _draw_final_result(self, calc_data):
        if calc_data.get('total_degree', 0) <= 0: return
        result_area_x, result_area_y = self.grid_offset_x, self.grid_offset_y - 70
        dist_str = f"{calc_data['final_distance']:.1f} m"
        font, color = self.fonts['result'], self.colors['normal']
        
        formula_prefix, formula_body_left = "平均集材距離 = ", "((⑨ + ⑦) ÷ ⑧ × K)"
        if calc_data['calc_mode'] == 'external': 
            formula_body_left += " + L"
        
        add_dist_str = f"{calc_data['additional_distance']:.0f}"
        formula_body_right = f" = (({calc_data['total_product_v']}+{calc_data['total_product_h']}) ÷ {calc_data['total_degree']} × {self.project.k_value:.0f})"
        if calc_data['calc_mode'] == 'external': 
            formula_body_right += f" + {add_dist_str}"
        
        full_formula_str = f"{formula_prefix}{formula_body_left}{formula_body_right} = {dist_str}"
        
        self.calculation_items.append(self._add_aligned_text(full_formula_str, font, color, QPointF(result_area_x, result_area_y), Qt.AlignmentFlag.AlignLeft))
        
        metrics = QFontMetrics(font)
        rounded_dist = int(round(calc_data['final_distance']))
        rounded_str = f"≒ {rounded_dist} m"
        
        pre_equal_part = full_formula_str.rsplit('=', 1)[0]
        align_x = result_area_x + metrics.horizontalAdvance(pre_equal_part)
        
        rounded_y_pos = result_area_y + metrics.height()

        self.calculation_items.append(self._add_aligned_text(rounded_str, font, color, QPointF(align_x, rounded_y_pos), Qt.AlignmentFlag.AlignLeft))

        if calc_data['calc_mode'] == 'external':
            note_font = self.fonts['data']
            note_y = rounded_y_pos + metrics.height() + 5
            note_text = "※ L: 集材区域入口から土場までの水平距離"
            self.calculation_items.append(self._add_aligned_text(note_text, note_font, color, QPointF(result_area_x + 20, note_y), Qt.AlignmentFlag.AlignLeft))

    def _draw_calculation_header(self):
        legend_y = self.grid_offset_y - 145 + 4
        col_widths_v = [40, 35, 45]
        v_table_width = sum(col_widths_v)
        content_right_edge = self.grid_offset_x + self.project.grid_cols*self.project.cell_size_on_screen + v_table_width
        
        k_part_offset_width = self.project.cell_size_on_screen + 65
        scale_text_width = QFontMetrics(self.fonts['scale']).horizontalAdvance("縮尺: 1/5000")
        
        legend_block_width = k_part_offset_width + scale_text_width
        legend_x = content_right_edge - legend_block_width - 5
        
        legend_pen = QPen(self.colors['dark'], 1.0)
        
        self.calculation_items.append(self.scene.addRect(legend_x, legend_y, self.project.cell_size_on_screen, self.project.cell_size_on_screen, legend_pen))
        
        dim_pen = QPen(self.colors['dark'], 0.8)
        tick_size = 2
        
        h_dim_y = legend_y + self.project.cell_size_on_screen + 5
        self.calculation_items.extend([
            self.scene.addLine(legend_x, h_dim_y, legend_x + self.project.cell_size_on_screen, h_dim_y, dim_pen),
            self.scene.addLine(legend_x, h_dim_y - tick_size, legend_x, h_dim_y + tick_size, dim_pen),
            self.scene.addLine(legend_x + self.project.cell_size_on_screen, h_dim_y - tick_size, legend_x + self.project.cell_size_on_screen, h_dim_y + tick_size, dim_pen)
        ])
        
        v_dim_x = legend_x + self.project.cell_size_on_screen + 5
        self.calculation_items.extend([
            self.scene.addLine(v_dim_x, legend_y, v_dim_x, legend_y + self.project.cell_size_on_screen, dim_pen),
            self.scene.addLine(v_dim_x - tick_size, legend_y, v_dim_x + tick_size, legend_y, dim_pen),
            self.scene.addLine(v_dim_x - tick_size, legend_y + self.project.cell_size_on_screen, v_dim_x + tick_size, legend_y + self.project.cell_size_on_screen, dim_pen)
        ])
        
        k_value_text = f"K ({self.project.k_value:.0f}m)"
        self.calculation_items.append(self._add_aligned_text(k_value_text, self.fonts['data'], self.colors['dark'], QPointF(legend_x + self.project.cell_size_on_screen + 32, legend_y + self.project.cell_size_on_screen/2), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter))
        self.calculation_items.append(self._add_aligned_text(k_value_text, self.fonts['data'], self.colors['dark'], QPointF(legend_x + self.project.cell_size_on_screen/2, legend_y + self.project.cell_size_on_screen + 20), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter))
        self.calculation_items.append(self._add_aligned_text("縮尺: 1/5000", self.fonts['scale'], self.colors['dark'], QPointF(legend_x + self.project.cell_size_on_screen + 65, legend_y + 4), Qt.AlignmentFlag.AlignLeft))

    # MODIFIED: This entire method is replaced to use the ReportGenerator
    def draw_summary_page_contents(self, for_pdf=False):
        if not self.project.calculation_data:
            return

        report_data = self.report_generator.generate_summary_data(self.project)
        if not report_data:
            return

        items = []
        x_start = 0 if for_pdf else 20
        y_start = 0 if for_pdf else 20
        
        if not for_pdf:
            grid_width = self.project.grid_cols * self.project.cell_size_on_screen
            x_start = self.grid_offset_x + (grid_width - 780) / 2 
            y_start = self.grid_offset_y + 50

        y_pos = y_start
        self._setup_drawing_styles(for_summary_pdf=True)
        
        # --- Metrics for layout ---
        metrics = {
            'title': QFontMetrics(self.fonts['title']),
            'result': QFontMetrics(self.fonts['result']),
            'section_header': QFontMetrics(self.fonts['section_header']),
            'data': QFontMetrics(self.fonts['data']),
            'data_bold': QFontMetrics(self.fonts['data_bold']),
            'note': QFontMetrics(self.fonts['note']),
        }
        line_heights = {
            'title': metrics['title'].height() + 15,
            'section_header': metrics['section_header'].height() + 10,
            'default': metrics['data'].height() + 8
        }

        for block in report_data:
            block_type = block.get('type')
            
            if block_type == 'title':
                item = self._add_aligned_text(block['text'], self.fonts['title'], self.colors['dark'], QPointF(x_start, y_pos), Qt.AlignmentFlag.AlignLeft)
                items.append(item)
                y_pos += line_heights['title']
            
            elif block_type == 'section_header':
                item = self._add_aligned_text(block['text'], self.fonts['section_header'], self.colors['dark'], QPointF(x_start, y_pos), Qt.AlignmentFlag.AlignLeft)
                items.append(item)
                y_pos += line_heights['section_header']

            elif block_type == 'spacer':
                y_pos += block['size']

            elif block_type in ['formula_line', 'calculation_line', 'note']:
                font = self.fonts['note'] if block_type == 'note' else self.fonts['data']
                offset = 40 if block_type == 'note' else 20
                item = self._add_aligned_text(block['text'], font, self.colors['normal'], QPointF(x_start + offset, y_pos), Qt.AlignmentFlag.AlignLeft)
                items.append(item)
                y_pos += line_heights['default']

            elif block_type == 'complex_formula_line':
                font = self.fonts['data']
                item1 = self._add_aligned_text(block['formula_part1'], font, self.colors['normal'], QPointF(x_start + 20, y_pos), Qt.AlignmentFlag.AlignLeft)
                items.append(item1)
                
                align_x = x_start + 20 + metrics['data'].horizontalAdvance(block['formula_part1'])
                item2 = self._add_aligned_text(block['result_part1'], font, self.colors['normal'], QPointF(align_x, y_pos), Qt.AlignmentFlag.AlignLeft)
                items.append(item2)
                item3 = self._add_aligned_text(block['result_part2'], font, self.colors['normal'], QPointF(align_x, y_pos + metrics['data'].height()), Qt.AlignmentFlag.AlignLeft)
                items.append(item3)
                y_pos += metrics['data'].height() + line_heights['default']
            
            elif block_type == 'table':
                table_x, table_y = x_start + 20, y_pos
                col_widths = [120, 140, 140, 180]
                row_height = 35
                pen = QPen(self.colors['dark'])

                for i, h_text in enumerate(block['headers']):
                    x = table_x + sum(col_widths[:i])
                    items.append(self.scene.addRect(x, table_y, col_widths[i], row_height, pen, QBrush(QColor("#F0F0F0"))))
                    items.append(self._add_aligned_text(h_text, self.fonts['data_bold'], self.colors['dark'], QPointF(x + col_widths[i]/2, table_y + row_height/2)))
                
                y_pos = table_y + row_height
                
                for row_data in block['rows']:
                    for j, d_text in enumerate(row_data):
                        x = table_x + sum(col_widths[:j])
                        items.append(self.scene.addRect(x, y_pos, col_widths[j], row_height, pen))
                        items.append(self._add_aligned_text(d_text, self.fonts['data'], self.colors['normal'], QPointF(x + col_widths[j]/2, y_pos + row_height/2)))
                    y_pos += row_height
                
                for j, d_text in enumerate(block['total_row']):
                    x = table_x + sum(col_widths[:j])
                    items.append(self.scene.addRect(x, y_pos, col_widths[j], row_height, pen, QBrush(QColor("#F0F0F0"))))
                    items.append(self._add_aligned_text(d_text, self.fonts['data_bold'], self.colors['dark'], QPointF(x + col_widths[j]/2, y_pos + row_height/2)))
                y_pos += row_height

            elif block_type == 'final_calculation':
                prefix_width = metrics['data'].horizontalAdvance(block['prefix'])
                align_x = x_start + 20 + prefix_width + 20

                items.append(self._add_aligned_text(block['prefix'], self.fonts['data'], self.colors['normal'], QPointF(x_start + 20, y_pos), Qt.AlignmentFlag.AlignLeft))
                items.append(self._add_aligned_text("=", self.fonts['data'], self.colors['normal'], QPointF(align_x, y_pos), Qt.AlignmentFlag.AlignLeft))
                items.append(self._add_aligned_text(block['line1'], self.fonts['data'], self.colors['normal'], QPointF(align_x + metrics['data'].horizontalAdvance("= "), y_pos), Qt.AlignmentFlag.AlignLeft))
                y_pos += metrics['data'].height() + 5

                items.append(self._add_aligned_text("=", self.fonts['data'], self.colors['normal'], QPointF(align_x, y_pos), Qt.AlignmentFlag.AlignLeft))
                items.append(self._add_aligned_text(block['line2'], self.fonts['data'], self.colors['normal'], QPointF(align_x + metrics['data'].horizontalAdvance("= "), y_pos), Qt.AlignmentFlag.AlignLeft))
                y_pos += metrics['data'].height() + 5
                
                equal_width = metrics['data'].horizontalAdvance("=")
                approx_width = metrics['data'].horizontalAdvance("≒")
                offset = (equal_width - approx_width) / 2
                items.append(self._add_aligned_text("≒", self.fonts['data'], self.colors['normal'], QPointF(align_x + offset, y_pos), Qt.AlignmentFlag.AlignLeft))
                items.append(self._add_aligned_text(block['line3'], self.fonts['data'], self.colors['normal'], QPointF(align_x + metrics['data'].horizontalAdvance("= "), y_pos), Qt.AlignmentFlag.AlignLeft))
                y_pos += metrics['data'].height()

            elif block_type == 'final_result':
                item = self._add_aligned_text(block['text'], self.fonts['result'], self.colors['dark'], QPointF(x_start, y_pos), Qt.AlignmentFlag.AlignLeft)
                items.append(item)
                
                bg_rect = item.boundingRect()
                bg_item = self.scene.addRect(bg_rect, QPen(Qt.PenStyle.NoPen), QBrush(QColor(255, 255, 204)))
                bg_item.setPos(item.pos())
                bg_item.setZValue(item.zValue() - 1)
                items.append(bg_item)
                
        self.calculation_items.extend(items)
        self._setup_drawing_styles()

    def _get_transform_parameters(self):
        if not self.project.master_bbox: return None
        rotated_corners = self._apply_rotation_to_coords([(self.project.master_bbox[0], self.project.master_bbox[1]),(self.project.master_bbox[2], self.project.master_bbox[3]),(self.project.master_bbox[2], self.project.master_bbox[1]),(self.project.master_bbox[0], self.project.master_bbox[3])])
        xs, ys = [p[0] for p in rotated_corners], [p[1] for p in rotated_corners]
        bbox_to_use, scale = (min(xs), min(ys), max(xs), max(ys)), self.project.cell_size_on_screen / self.project.k_value
        center_x, center_y = bbox_to_use[0] + (bbox_to_use[2] - bbox_to_use[0])/2, bbox_to_use[1] + (bbox_to_use[3] - bbox_to_use[1])/2
        grid_center_x, grid_center_y = self.grid_offset_x + (self.project.grid_cols*self.project.cell_size_on_screen)/2, self.grid_offset_y + (self.project.grid_rows*self.project.cell_size_on_screen)/2
        return {'scale': scale, 'center_x': center_x, 'center_y': center_y, 'grid_center_x': grid_center_x, 'grid_center_y': grid_center_y}
    
    def _apply_rotation_to_coords(self, coords, inverse=False):
        if self.project.map_rotation == 0 or not self.project.master_bbox: return coords
        orig_center_x, orig_center_y = self.project.master_bbox[0] + (self.project.master_bbox[2]-self.project.master_bbox[0])/2, self.project.master_bbox[1] + (self.project.master_bbox[3]-self.project.master_bbox[1])/2
        angle, theta = -self.project.map_rotation if inverse else self.project.map_rotation, math.radians(-self.project.map_rotation if inverse else self.project.map_rotation)
        cos_theta, sin_theta = math.cos(theta), math.sin(theta)
        return [((p_x-orig_center_x)*cos_theta - (p_y-orig_center_y)*sin_theta + orig_center_x, (p_x-orig_center_x)*sin_theta + (p_y-orig_center_y)*cos_theta + orig_center_y) for p_x, p_y in coords]

    def _get_feature_style(self, feature, layer_info):
        props = feature.get('properties', {})
        final_style = DEFAULT_STYLE_INFO.copy()
        fill_color_prop = props.get('fill_color')
        if fill_color_prop and str(fill_color_prop).strip():
            new_color = _parse_any_color_string(str(fill_color_prop))
            if new_color.isValid(): final_style['fill_color'] = new_color
        else: final_style['fill_color'] = QColor(0,0,0,0)
        pen_style_map = {"none": Qt.PenStyle.NoPen, "solid": Qt.PenStyle.SolidLine, "dash": Qt.PenStyle.DashLine, "dot": Qt.PenStyle.DotLine, "dashdot": Qt.PenStyle.DashDotLine, "dashdotdot": Qt.PenStyle.DashDotDotLine, "custom": Qt.PenStyle.CustomDashLine}
        style_key = props.get('strk_style')
        if style_key and str(style_key).lower() in pen_style_map: final_style['pen_style'] = pen_style_map[str(style_key).lower()]
        if final_style['pen_style'] != Qt.PenStyle.NoPen:
            line_color_prop = props.get('strk_color')
            if line_color_prop and str(line_color_prop).strip():
                new_line_color = _parse_any_color_string(str(line_color_prop), default_color=QColor("black"))
                if new_line_color.isValid(): final_style['line_color'] = new_line_color
            line_width_prop = props.get('strk_width')
            if line_width_prop is not None:
                try: final_style['line_width'] = float(line_width_prop)
                except (ValueError, TypeError): pass
        current_fill_color = final_style['fill_color']
        if current_fill_color.alpha() == 255: current_fill_color.setAlpha(150); final_style['fill_color'] = current_fill_color
        return final_style
    
    def _add_aligned_text(self, text, font, color, point, alignment=Qt.AlignmentFlag.AlignCenter):
        item = self.scene.addText(text, font)
        item.setDefaultTextColor(color)
        text_rect = item.boundingRect()
        item_x = point.x()
        item_y = point.y()
        if alignment & Qt.AlignmentFlag.AlignHCenter:
            item_x -= text_rect.width() / 2
        elif alignment & Qt.AlignmentFlag.AlignRight:
            item_x -= text_rect.width()
        if alignment & Qt.AlignmentFlag.AlignVCenter:
            item_y -= text_rect.height() / 2
        elif alignment & Qt.AlignmentFlag.AlignBottom:
            item_y -= text_rect.height()
        item.setPos(item_x, item_y)
        return item