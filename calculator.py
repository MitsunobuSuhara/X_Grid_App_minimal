from shapely.geometry import Polygon, MultiPolygon, box
import math

class Calculator:
    def __init__(self, project, renderer):
        self.project = project
        self.renderer = renderer

    def run_calculation(self):
        """
        計算のメインロジック。単一モードと分割モードを処理する。
        """
        if self.project.is_split_mode:
            return self._run_split_calculation()
        else:
            return self._run_single_calculation()

    def _run_single_calculation(self):
        """単一エリアの計算を実行する"""
        world_geom = self.project._get_combined_calculable_geom()
        if world_geom is None or world_geom.is_empty:
            return None
        
        self.project.sub_area_data = [{
            'id': 1, 'name': '計算区域', 'geom': world_geom,
            'calc_mode': self.project.default_calc_mode,
            'landing_cell': self.project.default_landing_cell,
            'additional_distance': self.project.default_additional_distance,
            'result': None
        }]
        
        area_data = self.project.sub_area_data[0]
        result = self._calculate_for_area(area_data)
        if not result: return None
        area_data['result'] = result
        
        return {'summary_result': result}

    def _run_split_calculation(self):
        """分割エリアの計算を実行し、加重平均を算出する"""
        if not self.project.sub_area_data:
            return None

        total_weighted_distance_sum = 0
        total_cells = 0
        
        summary_total_product_v = 0
        summary_total_product_h = 0
        summary_row_counts = {r: 0 for r in range(self.project.grid_rows)}
        summary_col_counts = {c: 0 for c in range(self.project.grid_cols)}
        
        for area_data in self.project.sub_area_data:
            result = self._calculate_for_area(area_data)
            if not result: continue
            area_data['result'] = result
            
            if result['total_degree'] > 0:
                total_weighted_distance_sum += result['final_distance'] * result['total_degree']
                total_cells += result['total_degree']
                
                summary_total_product_v += result['total_product_v']
                summary_total_product_h += result['total_product_h']
                for r, count in result['row_counts'].items():
                    summary_row_counts[r] += count
                for c, count in result['col_counts'].items():
                    summary_col_counts[c] += count

        final_weighted_distance = total_weighted_distance_sum / total_cells if total_cells > 0 else 0
        
        summary_result = {
            'final_distance': final_weighted_distance,
            'total_degree': total_cells,
            'total_product_v': summary_total_product_v,
            'total_product_h': summary_total_product_h,
            'row_counts': summary_row_counts,
            'col_counts': summary_col_counts,
            'landing_row': -1,
            'landing_col': -1,
            'is_summary': True
        }
        
        return {'summary_result': summary_result}

    def _calculate_for_area(self, area_data):
        """指定されたエリアのデータに基づいて平均集材距離を計算する"""
        world_geom = area_data['geom']
        
        calc_mode = area_data['calc_mode']
        landing_cell = area_data['landing_cell']
        additional_distance = area_data.get('additional_distance', 0.0)

        if not landing_cell:
            return None
        
        landing_row, landing_col = landing_cell
        
        in_area_cells = self.get_cells_for_geom(world_geom)
        if not in_area_cells: return None

        row_counts = {r: 0 for r in range(self.project.grid_rows)}
        col_counts = {c: 0 for c in range(self.project.grid_cols)}
        for r, c in in_area_cells:
            row_counts[r] += 1
            col_counts[c] += 1
        
        total_product_v = sum(abs(r - landing_row) * count for r, count in row_counts.items())
        total_product_h = sum(abs(c - landing_col) * count for c, count in col_counts.items())
        total_degree = len(in_area_cells)
        
        internal_distance = (total_product_v + total_product_h) / total_degree * self.project.k_value if total_degree > 0 else 0
        
        final_distance = internal_distance
        if calc_mode == "external":
            final_distance += additional_distance
        
        all_rows = [r for r, c in in_area_cells] if in_area_cells else []
        all_cols = [c for r, c in in_area_cells] if in_area_cells else []

        return {
            "final_distance": final_distance, "internal_distance": internal_distance,
            "additional_distance": additional_distance if calc_mode == "external" else 0.0,
            "calc_mode": calc_mode, "landing_row": landing_row, "landing_col": landing_col,
            "row_counts": row_counts, "col_counts": col_counts,
            "total_product_v": total_product_v, "total_product_h": total_product_h,
            "total_degree": total_degree, "in_area_cells": in_area_cells,
            "min_row": min(all_rows) if all_rows else 0, "max_row": max(all_rows) if all_rows else 0,
            "min_col": min(all_cols) if all_cols else 0, "max_col": max(all_cols) if all_cols else 0,
            "is_summary": False
        }

    def is_cell_in_area(self, cell, world_geom):
        """指定されたセルが、指定されたジオメトリの計算対象エリア内に含まれるかを判定する"""
        if not cell or not world_geom:
            return False
        
        all_valid_cells = self.get_cells_for_geom(world_geom)
        return cell in all_valid_cells

    def get_in_area_cells(self):
        """現在表示対象となっているエリアのセルを取得する"""
        world_geom = None
        if self.project.display_mode == 'summary':
            world_geom = self.project._get_combined_calculable_geom()
        elif 'area_' in self.project.display_mode:
            try:
                area_id = int(self.project.display_mode.split('_')[1])
                area_data = next((item for item in self.project.sub_area_data if item["id"] == area_id), None)
                if area_data:
                    world_geom = area_data['geom']
            except (ValueError, IndexError):
                world_geom = None
        else:
            world_geom = self.project._get_combined_calculable_geom()

        if world_geom is None or world_geom.is_empty:
            return []

        return self.get_cells_for_geom(world_geom)

    def get_cells_for_geom(self, world_geom):
        """指定されたワールドジオメトリに含まれるセルを取得する"""
        if not self.project.master_bbox: return []
        if world_geom is None or world_geom.is_empty: return []

        scene_geom = self.renderer.world_geom_to_scene_geom(world_geom)
        if not scene_geom: return []

        return self._get_cells_in_scene_geom(scene_geom)

    def _get_cells_in_scene_geom(self, scene_geom):
        if not scene_geom or scene_geom.is_empty: return []
        in_area_cells, area_threshold = [], 0.5 * (self.project.cell_size_on_screen ** 2)
        grid_offset_x, grid_offset_y = self.renderer.grid_offset_x, self.renderer.grid_offset_y
        min_x, min_y, max_x, max_y = scene_geom.bounds
        start_col = max(0, int((min_x - grid_offset_x) / self.project.cell_size_on_screen))
        end_col = min(self.project.grid_cols, int((max_x - grid_offset_x) / self.project.cell_size_on_screen) + 1)
        start_row = max(0, int((min_y - grid_offset_y) / self.project.cell_size_on_screen))
        end_row = min(self.project.grid_rows, int((max_y - grid_offset_y) / self.project.cell_size_on_screen) + 1)
        for r in range(start_row, end_row):
            for c in range(start_col, end_col):
                cell_poly = box(grid_offset_x + c * self.project.cell_size_on_screen, grid_offset_y + r * self.project.cell_size_on_screen, grid_offset_x + (c + 1) * self.project.cell_size_on_screen, grid_offset_y + (r + 1) * self.project.cell_size_on_screen)
                
                if scene_geom.intersects(cell_poly) and scene_geom.intersection(cell_poly).area >= area_threshold:
                    in_area_cells.append((r, c))
        return in_area_cells