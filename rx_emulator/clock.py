"""
クロック/実行制御モジュール

発振回路・実行速度・リセット連動の再現

RX65N クロック構成:
- LOCO: 低速オンチップオシレータ (240kHz)
- HOCO: 高速オンチップオシレータ (16/18/20MHz)
- Main Clock: 外部メインクロック
- Sub Clock: 外部サブクロック (32.768kHz)
- PLL: 位相同期回路
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, Callable, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .memory import MemoryController


class ClockSource(IntEnum):
    """クロックソース"""
    LOCO = 0       # 低速オンチップオシレータ (240kHz)
    HOCO = 1       # 高速オンチップオシレータ (16/18/20MHz)
    MAIN = 2       # 外部メインクロック
    SUB = 3        # サブクロック (32.768kHz)
    PLL = 4        # PLL出力


class HOCOFrequency(IntEnum):
    """HOCO周波数設定"""
    FREQ_16MHZ = 0
    FREQ_18MHZ = 1
    FREQ_20MHZ = 2


@dataclass
class ClockConfig:
    """クロック設定"""
    source: ClockSource = ClockSource.LOCO
    hoco_freq: HOCOFrequency = HOCOFrequency.FREQ_16MHZ
    main_freq_hz: int = 12000000       # 12MHz (外部)
    pll_multiplier: int = 20           # PLL逓倍率
    pll_divider: int = 2               # PLL分周率
    iclk_divider: int = 2              # システムクロック分周
    pclka_divider: int = 2             # 周辺クロックA分周
    pclkb_divider: int = 4             # 周辺クロックB分周
    pclkc_divider: int = 4             # 周辺クロックC分周
    pclkd_divider: int = 4             # 周辺クロックD分周
    fclk_divider: int = 4              # FlashIFクロック分周
    bclk_divider: int = 2              # 外部バスクロック分周


class ClockController:
    """
    クロックコントローラ

    発振回路の管理と各クロック周波数の計算
    """

    # 固定クロック周波数
    LOCO_FREQ = 240000        # 240kHz
    SUB_FREQ = 32768          # 32.768kHz

    # HOCO周波数テーブル
    HOCO_FREQ_TABLE = {
        HOCOFrequency.FREQ_16MHZ: 16000000,
        HOCOFrequency.FREQ_18MHZ: 18000000,
        HOCOFrequency.FREQ_20MHZ: 20000000,
    }

    # レジスタアドレス (RX65N)
    REG_SCKCR = 0x00080020    # システムクロック制御レジスタ
    REG_SCKCR2 = 0x00080024   # システムクロック制御レジスタ2
    REG_SCKCR3 = 0x00080026   # システムクロック制御レジスタ3
    REG_PLLCR = 0x00080028    # PLL制御レジスタ
    REG_PLLCR2 = 0x0008002A   # PLL制御レジスタ2
    REG_MOSCCR = 0x00080032   # メインクロック発振器制御レジスタ
    REG_HOCOCR = 0x00080036   # HOCO制御レジスタ
    REG_HOCOCR2 = 0x00080037  # HOCO制御レジスタ2

    def __init__(self):
        self.config = ClockConfig()
        self.memory: Optional['MemoryController'] = None

        # クロック状態
        self.main_osc_enabled: bool = False
        self.hoco_enabled: bool = True
        self.pll_enabled: bool = False

        # 仮想実行速度制御
        self.speed_multiplier: float = 1.0  # 1.0 = リアルタイム

        # 周期コールバック
        self.tick_callbacks: List[Callable] = []

        # 現在のティックカウント
        self.tick_count: int = 0

    def connect_memory(self, memory: 'MemoryController') -> None:
        """メモリコントローラを接続"""
        self.memory = memory
        self._register_peripheral_handlers()

    def _register_peripheral_handlers(self) -> None:
        """周辺レジスタハンドラを登録"""
        if not self.memory:
            return

        # SCKCR
        self.memory.register_peripheral(
            self.REG_SCKCR,
            self._read_sckcr,
            self._write_sckcr
        )

        # SCKCR3
        self.memory.register_peripheral(
            self.REG_SCKCR3,
            self._read_sckcr3,
            self._write_sckcr3
        )

        # HOCOCR
        self.memory.register_peripheral(
            self.REG_HOCOCR,
            self._read_hococr,
            self._write_hococr
        )

    def _read_sckcr(self, address: int) -> int:
        """SCKCR読み込み"""
        value = 0
        value |= (self.config.iclk_divider - 1) << 24
        value |= (self.config.pclka_divider - 1) << 12
        value |= (self.config.pclkb_divider - 1) << 8
        value |= (self.config.bclk_divider - 1) << 16
        return value

    def _write_sckcr(self, address: int, value: int) -> None:
        """SCKCR書き込み"""
        self.config.iclk_divider = ((value >> 24) & 0xF) + 1
        self.config.pclka_divider = ((value >> 12) & 0xF) + 1
        self.config.pclkb_divider = ((value >> 8) & 0xF) + 1
        self.config.bclk_divider = ((value >> 16) & 0xF) + 1

    def _read_sckcr3(self, address: int) -> int:
        """SCKCR3読み込み"""
        return self.config.source << 8

    def _write_sckcr3(self, address: int, value: int) -> None:
        """SCKCR3書き込み"""
        source = (value >> 8) & 0x7
        if source < len(ClockSource):
            self.config.source = ClockSource(source)

    def _read_hococr(self, address: int) -> int:
        """HOCOCR読み込み"""
        return 0 if self.hoco_enabled else 1

    def _write_hococr(self, address: int, value: int) -> None:
        """HOCOCR書き込み"""
        self.hoco_enabled = (value & 1) == 0

    def get_source_frequency(self) -> int:
        """現在のクロックソース周波数を取得"""
        source = self.config.source

        if source == ClockSource.LOCO:
            return self.LOCO_FREQ
        elif source == ClockSource.HOCO:
            return self.HOCO_FREQ_TABLE[self.config.hoco_freq]
        elif source == ClockSource.MAIN:
            return self.config.main_freq_hz
        elif source == ClockSource.SUB:
            return self.SUB_FREQ
        elif source == ClockSource.PLL:
            return self._calculate_pll_frequency()

        return self.LOCO_FREQ

    def _calculate_pll_frequency(self) -> int:
        """PLL出力周波数を計算"""
        input_freq = self.config.main_freq_hz
        return (input_freq * self.config.pll_multiplier) // self.config.pll_divider

    def get_iclk(self) -> int:
        """システムクロック(ICLK)周波数を取得"""
        return self.get_source_frequency() // self.config.iclk_divider

    def get_pclka(self) -> int:
        """周辺クロックA(PCLKA)周波数を取得"""
        return self.get_source_frequency() // self.config.pclka_divider

    def get_pclkb(self) -> int:
        """周辺クロックB(PCLKB)周波数を取得"""
        return self.get_source_frequency() // self.config.pclkb_divider

    def get_pclkc(self) -> int:
        """周辺クロックC(PCLKC)周波数を取得"""
        return self.get_source_frequency() // self.config.pclkc_divider

    def get_pclkd(self) -> int:
        """周辺クロックD(PCLKD)周波数を取得"""
        return self.get_source_frequency() // self.config.pclkd_divider

    def get_fclk(self) -> int:
        """FlashIFクロック(FCLK)周波数を取得"""
        return self.get_source_frequency() // self.config.fclk_divider

    def get_bclk(self) -> int:
        """外部バスクロック(BCLK)周波数を取得"""
        return self.get_source_frequency() // self.config.bclk_divider

    def tick(self, cycles: int = 1) -> None:
        """クロックティック"""
        self.tick_count += cycles

        # コールバック実行
        for callback in self.tick_callbacks:
            callback(cycles)

    def register_tick_callback(self, callback: Callable) -> None:
        """ティックコールバックを登録"""
        self.tick_callbacks.append(callback)

    def set_speed_multiplier(self, multiplier: float) -> None:
        """実行速度倍率を設定"""
        self.speed_multiplier = max(0.01, multiplier)

    def reset(self) -> None:
        """クロックをリセット"""
        self.config = ClockConfig()
        self.main_osc_enabled = False
        self.hoco_enabled = True
        self.pll_enabled = False
        self.tick_count = 0

    def get_state(self) -> dict:
        """クロック状態を取得"""
        return {
            'source': self.config.source.name,
            'source_freq_hz': self.get_source_frequency(),
            'iclk_hz': self.get_iclk(),
            'pclka_hz': self.get_pclka(),
            'pclkb_hz': self.get_pclkb(),
            'pclkc_hz': self.get_pclkc(),
            'pclkd_hz': self.get_pclkd(),
            'fclk_hz': self.get_fclk(),
            'bclk_hz': self.get_bclk(),
            'hoco_enabled': self.hoco_enabled,
            'main_osc_enabled': self.main_osc_enabled,
            'pll_enabled': self.pll_enabled,
            'tick_count': self.tick_count,
            'speed_multiplier': self.speed_multiplier,
        }


class ExecutionController:
    """
    実行制御

    ステップ実行・連続実行・ブレークポイントの管理
    """

    def __init__(self):
        self.running: bool = False
        self.single_step: bool = False
        self.step_over: bool = False

        # ブレークポイント
        self.breakpoints: set = set()

        # ウォッチポイント
        self.watchpoints: set = set()

        # 実行制御コールバック
        self.on_break: Optional[Callable] = None
        self.on_step: Optional[Callable] = None

    def add_breakpoint(self, address: int) -> None:
        """ブレークポイントを追加"""
        self.breakpoints.add(address)

    def remove_breakpoint(self, address: int) -> None:
        """ブレークポイントを削除"""
        self.breakpoints.discard(address)

    def toggle_breakpoint(self, address: int) -> bool:
        """ブレークポイントをトグル"""
        if address in self.breakpoints:
            self.breakpoints.remove(address)
            return False
        else:
            self.breakpoints.add(address)
            return True

    def is_breakpoint(self, address: int) -> bool:
        """ブレークポイントかチェック"""
        return address in self.breakpoints

    def add_watchpoint(self, address: int) -> None:
        """ウォッチポイントを追加"""
        self.watchpoints.add(address)

    def remove_watchpoint(self, address: int) -> None:
        """ウォッチポイントを削除"""
        self.watchpoints.discard(address)

    def is_watchpoint(self, address: int) -> bool:
        """ウォッチポイントかチェック"""
        return address in self.watchpoints

    def clear_all(self) -> None:
        """全てのブレーク/ウォッチポイントをクリア"""
        self.breakpoints.clear()
        self.watchpoints.clear()

    def start(self) -> None:
        """実行開始"""
        self.running = True
        self.single_step = False

    def stop(self) -> None:
        """実行停止"""
        self.running = False

    def step(self) -> None:
        """シングルステップ"""
        self.single_step = True
        self.running = True

    def get_state(self) -> dict:
        """実行制御状態を取得"""
        return {
            'running': self.running,
            'single_step': self.single_step,
            'breakpoints': list(self.breakpoints),
            'watchpoints': list(self.watchpoints),
        }
