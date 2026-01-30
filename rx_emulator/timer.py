"""
タイマモジュール

周期動作・割り込み生成の再現

RX65N タイマ構成:
- CMT (Compare Match Timer): 16ビットタイマ x 4チャンネル
- TMR (8ビットタイマ): 8ビットタイマ x 8チャンネル
- GPT (General PWM Timer): 汎用PWMタイマ
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .memory import MemoryController
    from .interrupt import InterruptController


class CMTClockDivider(IntEnum):
    """CMTクロック分周"""
    DIV_8 = 0
    DIV_32 = 1
    DIV_128 = 2
    DIV_512 = 3


@dataclass
class CMTChannel:
    """CMT (Compare Match Timer) チャンネル"""
    number: int

    # レジスタ
    cmcr: int = 0x0000    # コントロールレジスタ
    cmcnt: int = 0x0000   # カウンタ
    cmcor: int = 0xFFFF   # コンペアマッチレジスタ

    # 状態
    running: bool = False
    compare_match_flag: bool = False

    # 割り込み
    interrupt_enabled: bool = False
    interrupt_vector: int = 0

    @property
    def clock_divider(self) -> CMTClockDivider:
        """クロック分周設定"""
        return CMTClockDivider(self.cmcr & 0x03)

    @property
    def divider_value(self) -> int:
        """分周値"""
        div_map = {
            CMTClockDivider.DIV_8: 8,
            CMTClockDivider.DIV_32: 32,
            CMTClockDivider.DIV_128: 128,
            CMTClockDivider.DIV_512: 512,
        }
        return div_map[self.clock_divider]


class CMTUnit:
    """
    CMT (Compare Match Timer) ユニット

    2チャンネルで1ユニット
    """

    def __init__(self, unit_number: int, base_address: int):
        self.unit_number = unit_number
        self.base_address = base_address

        # CMSTR (スタートレジスタ)
        self.cmstr: int = 0x0000

        # チャンネル (1ユニットに2チャンネル)
        ch_base = unit_number * 2
        self.channels: Dict[int, CMTChannel] = {
            0: CMTChannel(ch_base),
            1: CMTChannel(ch_base + 1),
        }

        # 割り込みベクタ番号 (RX65N)
        self.channels[0].interrupt_vector = 28 + unit_number * 2
        self.channels[1].interrupt_vector = 29 + unit_number * 2

    def start_channel(self, ch: int) -> None:
        """チャンネルを開始"""
        if ch in self.channels:
            self.channels[ch].running = True
            self.cmstr |= (1 << ch)

    def stop_channel(self, ch: int) -> None:
        """チャンネルを停止"""
        if ch in self.channels:
            self.channels[ch].running = False
            self.cmstr &= ~(1 << ch)


class TimerController:
    """
    タイマコントローラ

    CMTおよびTMRを管理
    """

    # CMTベースアドレス (RX65N)
    CMT0_BASE = 0x00088000  # CMT0, CMT1
    CMT1_BASE = 0x00088010  # CMT2, CMT3

    # レジスタオフセット
    CMSTR_OFFSET = 0x00
    CMCR_OFFSET = 0x02
    CMCNT_OFFSET = 0x04
    CMCOR_OFFSET = 0x06

    def __init__(self):
        self.memory: Optional['MemoryController'] = None
        self.interrupt_controller: Optional['InterruptController'] = None

        # CMTユニット
        self.cmt_units: Dict[int, CMTUnit] = {
            0: CMTUnit(0, self.CMT0_BASE),
            1: CMTUnit(1, self.CMT1_BASE),
        }

        # 内部クロック (PCLKB相当)
        self.clock_hz: int = 60000000  # 60MHz

        # 分周カウンタ (各チャンネル)
        self.prescale_counters: Dict[int, int] = {}

        # タイマ変更コールバック
        self.timer_callbacks: List[Callable] = []

    def connect_memory(self, memory: 'MemoryController') -> None:
        """メモリコントローラを接続"""
        self.memory = memory
        self._register_peripheral_handlers()

    def connect_interrupt_controller(self, ic: 'InterruptController') -> None:
        """割り込みコントローラを接続"""
        self.interrupt_controller = ic

    def _register_peripheral_handlers(self) -> None:
        """周辺レジスタハンドラを登録"""
        if not self.memory:
            return

        for unit_num, unit in self.cmt_units.items():
            base = unit.base_address

            # CMSTR
            self.memory.register_peripheral(
                base + self.CMSTR_OFFSET,
                lambda a, u=unit_num: self._read_cmstr(u),
                lambda a, v, u=unit_num: self._write_cmstr(u, v)
            )

            # 各チャンネル
            for ch_idx in range(2):
                ch_offset = ch_idx * 8 + 2  # チャンネルごとにオフセット

                # CMCR
                self.memory.register_peripheral(
                    base + ch_offset + 0,
                    lambda a, u=unit_num, c=ch_idx: self._read_cmcr(u, c),
                    lambda a, v, u=unit_num, c=ch_idx: self._write_cmcr(u, c, v)
                )

                # CMCNT
                self.memory.register_peripheral(
                    base + ch_offset + 2,
                    lambda a, u=unit_num, c=ch_idx: self._read_cmcnt(u, c),
                    lambda a, v, u=unit_num, c=ch_idx: self._write_cmcnt(u, c, v)
                )

                # CMCOR
                self.memory.register_peripheral(
                    base + ch_offset + 4,
                    lambda a, u=unit_num, c=ch_idx: self._read_cmcor(u, c),
                    lambda a, v, u=unit_num, c=ch_idx: self._write_cmcor(u, c, v)
                )

    def _read_cmstr(self, unit: int) -> int:
        return self.cmt_units[unit].cmstr

    def _write_cmstr(self, unit: int, value: int) -> None:
        old = self.cmt_units[unit].cmstr
        self.cmt_units[unit].cmstr = value & 0x03

        # チャンネル開始/停止
        for ch in range(2):
            if (value & (1 << ch)) and not (old & (1 << ch)):
                self.cmt_units[unit].start_channel(ch)
            elif not (value & (1 << ch)) and (old & (1 << ch)):
                self.cmt_units[unit].stop_channel(ch)

    def _get_channel(self, unit: int, ch: int) -> CMTChannel:
        return self.cmt_units[unit].channels[ch]

    def _read_cmcr(self, unit: int, ch: int) -> int:
        return self._get_channel(unit, ch).cmcr

    def _write_cmcr(self, unit: int, ch: int, value: int) -> None:
        channel = self._get_channel(unit, ch)
        channel.cmcr = value & 0x00C3
        channel.interrupt_enabled = bool(value & 0x0040)

    def _read_cmcnt(self, unit: int, ch: int) -> int:
        return self._get_channel(unit, ch).cmcnt

    def _write_cmcnt(self, unit: int, ch: int, value: int) -> None:
        self._get_channel(unit, ch).cmcnt = value & 0xFFFF

    def _read_cmcor(self, unit: int, ch: int) -> int:
        return self._get_channel(unit, ch).cmcor

    def _write_cmcor(self, unit: int, ch: int, value: int) -> None:
        self._get_channel(unit, ch).cmcor = value & 0xFFFF

    def tick(self, cycles: int = 1) -> None:
        """クロックティック"""
        for unit in self.cmt_units.values():
            for ch_idx, channel in unit.channels.items():
                if not channel.running:
                    continue

                # 分周カウンタを更新
                ch_id = unit.unit_number * 2 + ch_idx
                if ch_id not in self.prescale_counters:
                    self.prescale_counters[ch_id] = 0

                self.prescale_counters[ch_id] += cycles

                # 分周値を超えたらカウンタ更新
                divider = channel.divider_value
                while self.prescale_counters[ch_id] >= divider:
                    self.prescale_counters[ch_id] -= divider
                    channel.cmcnt = (channel.cmcnt + 1) & 0xFFFF

                    # コンペアマッチ判定
                    if channel.cmcnt == channel.cmcor:
                        channel.compare_match_flag = True
                        channel.cmcnt = 0  # カウンタクリア

                        # 割り込み発生
                        if channel.interrupt_enabled and self.interrupt_controller:
                            self.interrupt_controller.request(channel.interrupt_vector)

                        # コールバック
                        for callback in self.timer_callbacks:
                            callback(unit.unit_number, ch_idx, 'compare_match')

    def register_timer_callback(self, callback: Callable) -> None:
        """タイマコールバックを登録"""
        self.timer_callbacks.append(callback)

    def set_clock(self, clock_hz: int) -> None:
        """動作クロック周波数を設定"""
        self.clock_hz = clock_hz

    def get_channel_frequency(self, unit: int, ch: int) -> float:
        """チャンネルの割り込み周波数を計算"""
        channel = self._get_channel(unit, ch)
        if channel.cmcor == 0:
            return 0.0
        return self.clock_hz / channel.divider_value / (channel.cmcor + 1)

    def reset(self) -> None:
        """タイマをリセット"""
        for unit in self.cmt_units.values():
            unit.cmstr = 0
            for channel in unit.channels.values():
                channel.cmcr = 0
                channel.cmcnt = 0
                channel.cmcor = 0xFFFF
                channel.running = False
                channel.compare_match_flag = False
                channel.interrupt_enabled = False
        self.prescale_counters.clear()

    def get_state(self) -> dict:
        """タイマ状態を取得"""
        result = {}
        for unit_num, unit in self.cmt_units.items():
            for ch_idx, channel in unit.channels.items():
                ch_name = f"CMT{unit_num * 2 + ch_idx}"
                result[ch_name] = {
                    'cmcr': f'0x{channel.cmcr:04X}',
                    'cmcnt': channel.cmcnt,
                    'cmcor': channel.cmcor,
                    'running': channel.running,
                    'interrupt_enabled': channel.interrupt_enabled,
                    'divider': channel.divider_value,
                    'frequency_hz': self.get_channel_frequency(unit_num, ch_idx),
                }
        return result


@dataclass
class TMRChannel:
    """8ビットタイマチャンネル"""
    number: int

    # レジスタ
    tcr: int = 0x00      # タイマコントロールレジスタ
    tcsr: int = 0x00     # タイマコントロール/ステータスレジスタ
    tcora: int = 0xFF    # タイムコンスタントレジスタA
    tcorb: int = 0xFF    # タイムコンスタントレジスタB
    tcnt: int = 0x00     # タイムカウンタ

    running: bool = False


class TMRUnit:
    """8ビットタイマユニット"""

    def __init__(self, unit_number: int, base_address: int):
        self.unit_number = unit_number
        self.base_address = base_address

        self.channels: Dict[int, TMRChannel] = {
            0: TMRChannel(unit_number * 2),
            1: TMRChannel(unit_number * 2 + 1),
        }
