from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt

# --- 定数とヘルパー関数 ---
# 変更点: デフォルトの塗りつぶしを「完全に透明」に変更
DEFAULT_STYLE_INFO = {
    'fill_color': QColor(0, 0, 0, 0), # Alphaを0に設定
    'line_color': QColor(0, 0, 0),
    'line_width': 0.3,
    'pen_style': Qt.PenStyle.SolidLine,
}

def _parse_any_color_string(color_value, default_color=QColor(0, 0, 0, 0)):
    """あらゆる形式の色の文字列を解析してQColorオブジェクトを返す"""
    if not color_value or not isinstance(color_value, str):
        return default_color
    
    color_str = str(color_value).strip().lower()

    if not color_str:
        return default_color

    if ',' in color_str:
        try:
            parts = [int(p.strip()) for p in color_str.split(',') if p.strip().isdigit()]
            if len(parts) == 3:
                return QColor(parts[0], parts[1], parts[2])
            if len(parts) == 4:
                return QColor(parts[0], parts[1], parts[2], parts[3])
        except (ValueError, IndexError):
            pass

    if QColor.isValidColor(color_str):
        return QColor(color_str)
    
    if color_str == 'transparent':
        return QColor(0,0,0,0)

    return default_color