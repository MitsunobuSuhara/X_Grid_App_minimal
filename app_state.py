from enum import Enum, auto

class AppState(Enum):
    """アプリケーションの状態を管理する列挙型"""
    IDLE = auto()                   # 初期状態、レイヤ読み込み待ち
    READY_TO_START = auto()         # 計算対象ポリゴンが選択され、「計算を開始」可能
    AWAITING_CALC_TYPE_CHOICE = auto() # 計算タイプ(単一/分割)の選択待ち
    AWAITING_BASE_CALC_MODE = auto()   # 基本/デフォルトの計算モード(内部/外部)の選択待ち
    AWAITING_LANDING_POINT = auto() # 起点(土場/入口)のクリック待ち
    AWAITING_TEXT_POINT = auto()    # テキストボックスの配置場所クリック待ち
    AWAITING_EXTERNAL_DISTANCE = auto()# 外部距離Lの入力待ち
    DRAWING_SPLIT_LINE = auto()     # 区域の分割線を描画中
    CONFIGURING_SUB_AREAS = auto()  # 分割後の各エリアの計算方法を設定中
    READY_TO_CALCULATE = auto()     # 全設定完了、計算実行可能
    CALCULATION_RUNNING = auto()    # 計算実行中
    RESULTS_DISPLAYED = auto()      # 計算結果表示中