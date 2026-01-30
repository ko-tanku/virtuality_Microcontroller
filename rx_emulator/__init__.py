"""
RX65N マイコン仮想実行環境
Renesas RXファミリ（RX65N相当）の仮想エミュレータ

対象範囲:
- CPU構造・命令動作
- C言語とCPU動作の対応
- クロック・リセット
- GPIO・タイマ
- 割り込み
- RX用C/C++コンパイラ出力の実行
- RX65Nターゲットボード相当のI/O
"""

__version__ = "0.1.0"
__author__ = "RX Emulator Team"

from .cpu import RXCpu
from .memory import MemoryController
from .clock import ClockController
from .gpio import GPIOController
from .timer import TimerController
from .interrupt import InterruptController
from .loader import ELFLoader
from .board import VirtualBoard
from .emulator import RX65NEmulator

__all__ = [
    "RXCpu",
    "MemoryController",
    "ClockController",
    "GPIOController",
    "TimerController",
    "InterruptController",
    "ELFLoader",
    "VirtualBoard",
    "RX65NEmulator",
]
