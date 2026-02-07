# --- START OF FILE report_generator.py ---
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN

class ReportGenerator:
    """
    総括表の表示内容を、表示形式（画面/Excel）に依存しない
    中間データ構造として生成するためのクラス。
    このクラスが帳票内容の「Single Source of Truth」となる。
    """
    def generate_summary_data(self, project):
        """
        プロジェクトオブジェクトから総括表の全データを生成し、
        ブロックのリストとして返す。
        """
        report_blocks = []
        
        # --- データ取得 ---
        subtitle = project.calculation_data.get('subtitle_text', '')
        sub_area_data = project.sub_area_data
        summary_result = project.calculation_data.get('summary_result')
        if not summary_result:
            return []

        # --- 1. メインタイトル ---
        title_text = f"{subtitle} 平均集材距離計算表 (総括)"
        report_blocks.append({'type': 'title', 'text': title_text})
        report_blocks.append({'type': 'spacer', 'size': 20})

        # --- 2. 各区域の計算結果 ---
        report_blocks.append({'type': 'section_header', 'text': "【各区域の計算結果】"})

        has_l_note = False
        for area in sub_area_data:
            res = area.get('result')
            if not res: continue

            formula_left = f"{area['name']}: 平均集材距離 = ((⑨+⑦)÷⑧×K)"
            if res['calc_mode'] == 'external':
                formula_left += " + L"
                has_l_note = True
            
            formula_right_base = f" = (({res['total_product_v']}+{res['total_product_h']})÷{res['total_degree']}×{project.k_value:.0f})"
            if res['calc_mode'] == 'external':
                formula_right_base += f" + {res['additional_distance']:.0f}"
            
            final_dist_dec = Decimal(str(res['final_distance']))
            if final_dist_dec % 1 == 0:
                result_str = f" = {int(final_dist_dec)} m"
            else:
                # 0.1m単位の中間表示は「切り捨て」
                truncated_val = final_dist_dec.quantize(Decimal('0.1'), rounding=ROUND_DOWN)
                result_str_1 = f" = {truncated_val:.1f} m"
                # 整数値は「四捨五入」
                rounded_val = final_dist_dec.quantize(Decimal('0'), rounding=ROUND_HALF_UP)
                result_str_2 = f"≒ {int(rounded_val)} m"
                
                # アプリ表示とExcelで改行の扱いが違うため、データを分ける
                report_blocks.append({
                    'type': 'complex_formula_line',
                    'formula_part1': f"{formula_left}{formula_right_base}",
                    'result_part1': result_str_1,
                    'result_part2': result_str_2,
                })
                continue
            
            full_formula_str = f"{formula_left}{formula_right_base}{result_str}"
            report_blocks.append({'type': 'formula_line', 'text': full_formula_str})
        
        if has_l_note:
            report_blocks.append({'type': 'note', 'text': "※ L: 集材区域入口から土場までの水平距離"})

        report_blocks.append({'type': 'spacer', 'size': 20})
        
        # --- 3. 面積按分による計算 ---
        report_blocks.append({'type': 'section_header', 'text': "【面積按分による計算】"})
        report_blocks.append({'type': 'note', 'text': "※ 区域面積は、集材区域に含まれるセルの数から算出しています。"})

        sub_results = [a['result'] for a in sub_area_data if a.get('result')]
        
        # MODIFIED: 面積計算にDecimalを使用し、小数第3位を四捨五入する
        quantizer = Decimal('0.01')
        areas_ha_raw = [res['total_degree'] * (project.k_value**2) / 10000 for res in sub_results]
        areas_ha_rounded = [
            Decimal(str(ha)).quantize(quantizer, rounding=ROUND_HALF_UP) for ha in areas_ha_raw
        ]
        total_ha_rounded = sum(areas_ha_rounded) if areas_ha_rounded else Decimal('0.00')

        report_blocks.append({'type': 'spacer', 'size': 10})

        # --- 4. 面積割合の算出と丸め (合計が1.00になるように調整) ---
        ratios = []
        if total_ha_rounded > 0:
            # 各区域の比率を一旦計算
            raw_ratios = [ha / total_ha_rounded for ha in areas_ha_rounded]
            # 小数第2位に丸める (0.01単位)
            ratios = [r.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) for r in raw_ratios]
            
            # 合計が1.00になるように、最後の項目で微調整する
            if ratios:
                diff = Decimal('1.00') - sum(ratios)
                ratios[-1] += diff

        # --- 5. 集計表 ---
        table_headers = ["区域", "セル数", "面積\n(ha)", "面積割合", "平均集材距離\n(m)"]
        table_rows = []
        total_cells = 0
        if total_ha_rounded > 0:
            for i, res in enumerate(sub_results):
                area_ha = areas_ha_rounded[i]
                ratio = ratios[i]
                cell_count = res['total_degree']
                total_cells += cell_count
                table_rows.append([
                    sub_area_data[i]['name'],
                    f"{cell_count}",
                    f"{area_ha:.2f}",
                    f"{ratio:.2f}", # MODIFIED: ユーザー要望により小数第2位に
                    f"{int(round(res['final_distance']))}"
                ])
        
        total_ratio_str = "1.00" if total_ha_rounded > 0 else "0.00"
        table_total_row = ["合計", f"{total_cells}", f"{total_ha_rounded:.2f}", total_ratio_str, ""]
        
        report_blocks.append({
            'type': 'table',
            'headers': table_headers,
            'rows': table_rows,
            'total_row': table_total_row
        })
        report_blocks.append({'type': 'spacer', 'size': 20})

        # --- 6. 最終計算式 ---
        if total_ha_rounded > 0:
            weighted_sum_parts = []
            weighted_sum_values = []
            for i, res in enumerate(sub_results):
                # MODIFIED: 先ほど計算・調整した丸め後の比率 (小数第2位) を使用
                ratio = ratios[i]
                # MODIFIED: 表示と計算を一致させるため、各区域の距離も四捨五入した整数値を使用する
                rounded_area_dist = int(Decimal(str(res['final_distance'])).quantize(Decimal('0'), rounding=ROUND_HALF_UP))
                
                part_str = f"({rounded_area_dist}m × {ratio:.2f})"
                weighted_sum_parts.append(part_str)
                weighted_sum_values.append(Decimal(str(rounded_area_dist)) * ratio)

            line1_formula = ' + '.join(weighted_sum_parts)
            # Decimalのまま合計を出し、高精度を維持する
            summary_decimal_result = sum(weighted_sum_values)
            
            # 小数第1位は「切り捨て」、整数は「四捨五入」で生成する
            line2_val = summary_decimal_result.quantize(Decimal('0.1'), rounding=ROUND_DOWN)
            line3_val = summary_decimal_result.quantize(Decimal('0'), rounding=ROUND_HALF_UP)

            report_blocks.append({
                'type': 'final_calculation',
                # MODIFIED: ユーザー要望により、計算式の見出しを「平均集材距離」から「加重距離計算」に変更
                'prefix': "加重距離計算",
                'line1': line1_formula,
                'line2': f"{line2_val:.1f} m",
                'line3': f"{line3_val} m"
            })
        report_blocks.append({'type': 'spacer', 'size': 20})

        # --- 7. 最終結果 ---
        # MODIFIED: 最終結果は、上の「加重距離計算」で算出した丸め後の値と完全に一致させる
        if total_ha_rounded > 0:
            final_dist_to_display = line3_val
        else:
            final_dist = summary_result.get('final_distance', 0.0)
            final_dist_to_display = int(round(final_dist))
            
        final_result_str = f"平均集材距離 = {final_dist_to_display} m"
        report_blocks.append({'type': 'final_result', 'text': final_result_str})

        return report_blocks