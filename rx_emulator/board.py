"""
仮想RX65Nターゲットボードモデル

実機ボード相当のI/O表現:
- LED表示
- スイッチ入力
- UARTログ出力
- リセットSW
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Callable, TYPE_CHECKING
from collections import deque

if TYPE_CHECKING:
    from .gpio import GPIOController
    from .memory import MemoryController


class LEDState(IntEnum):
    """LED状態"""
    OFF = 0
    ON = 1


class SwitchState(IntEnum):
    """スイッチ状態"""
    RELEASED = 0
    PRESSED = 1


@dataclass
class LED:
    """LED定義"""
    name: str
    port: int
    bit: int
    active_low: bool = True  # Low activeの場合True
    state: LEDState = LEDState.OFF

    def update(self, pin_value: bool) -> bool:
        """ピン値からLED状態を更新"""
        if self.active_low:
            new_state = LEDState.ON if not pin_value else LEDState.OFF
        else:
            new_state = LEDState.ON if pin_value else LEDState.OFF

        changed = (self.state != new_state)
        self.state = new_state
        return changed


@dataclass
class Switch:
    """スイッチ定義"""
    name: str
    port: int
    bit: int
    active_low: bool = True  # Low activeの場合True
    state: SwitchState = SwitchState.RELEASED

    def get_pin_value(self) -> bool:
        """ピン値を取得"""
        if self.active_low:
            return self.state == SwitchState.RELEASED
        return self.state == SwitchState.PRESSED


@dataclass
class UARTConfig:
    """UART設定"""
    baudrate: int = 115200
    data_bits: int = 8
    stop_bits: int = 1
    parity: str = 'none'


class VirtualUART:
    """
    仮想UART

    送受信バッファとログ機能
    """

    # SCIレジスタベースアドレス (RX65N SCI0)
    SCI0_BASE = 0x0008A000

    # レジスタオフセット
    SMR_OFFSET = 0x00   # シリアルモードレジスタ
    BRR_OFFSET = 0x01   # ビットレートレジスタ
    SCR_OFFSET = 0x02   # シリアルコントロールレジスタ
    TDR_OFFSET = 0x03   # トランスミットデータレジスタ
    SSR_OFFSET = 0x04   # シリアルステータスレジスタ
    RDR_OFFSET = 0x05   # レシーブデータレジスタ

    def __init__(self, channel: int = 0):
        self.channel = channel
        self.base_address = self.SCI0_BASE + (channel * 0x20)

        self.config = UARTConfig()
        self.tx_buffer: deque = deque(maxlen=256)
        self.rx_buffer: deque = deque(maxlen=256)
        self.tx_log: List[str] = []

        # レジスタ
        self.smr: int = 0x00
        self.brr: int = 0xFF
        self.scr: int = 0x00
        self.ssr: int = 0x84  # TDRE=1, TEND=1

        # コールバック
        self.tx_callback: Optional[Callable] = None
        self.memory: Optional['MemoryController'] = None

    def connect_memory(self, memory: 'MemoryController') -> None:
        """メモリコントローラを接続"""
        self.memory = memory
        self._register_peripheral_handlers()

    def _register_peripheral_handlers(self) -> None:
        """周辺レジスタハンドラを登録"""
        if not self.memory:
            return

        base = self.base_address

        # SMR
        self.memory.register_peripheral(
            base + self.SMR_OFFSET,
            lambda a: self.smr,
            lambda a, v: setattr(self, 'smr', v & 0xFF)
        )

        # BRR
        self.memory.register_peripheral(
            base + self.BRR_OFFSET,
            lambda a: self.brr,
            lambda a, v: setattr(self, 'brr', v & 0xFF)
        )

        # SCR
        self.memory.register_peripheral(
            base + self.SCR_OFFSET,
            lambda a: self.scr,
            lambda a, v: self._write_scr(v)
        )

        # TDR
        self.memory.register_peripheral(
            base + self.TDR_OFFSET,
            lambda a: 0,  # 書き込み専用
            lambda a, v: self._write_tdr(v)
        )

        # SSR
        self.memory.register_peripheral(
            base + self.SSR_OFFSET,
            lambda a: self.ssr,
            lambda a, v: self._write_ssr(v)
        )

        # RDR
        self.memory.register_peripheral(
            base + self.RDR_OFFSET,
            lambda a: self._read_rdr(),
            None
        )

    def _write_scr(self, value: int) -> None:
        """SCR書き込み"""
        self.scr = value & 0xFF

    def _write_tdr(self, value: int) -> None:
        """TDR書き込み (送信)"""
        char = chr(value & 0x7F) if value < 128 else '?'
        self.tx_buffer.append(value & 0xFF)
        self.tx_log.append(char)

        # 送信完了フラグ
        self.ssr |= 0x84  # TDRE=1, TEND=1

        if self.tx_callback:
            self.tx_callback(value & 0xFF, char)

    def _write_ssr(self, value: int) -> None:
        """SSR書き込み (フラグクリア)"""
        # 0を書き込んでフラグクリア
        self.ssr &= (value | 0x84)

    def _read_rdr(self) -> int:
        """RDR読み込み (受信)"""
        if self.rx_buffer:
            value = self.rx_buffer.popleft()
            # 受信データなしならRDRFクリア
            if not self.rx_buffer:
                self.ssr &= ~0x40
            return value
        return 0

    def receive(self, data: int) -> None:
        """外部から受信データを入力"""
        self.rx_buffer.append(data & 0xFF)
        self.ssr |= 0x40  # RDRF=1

    def receive_string(self, text: str) -> None:
        """文字列を受信バッファに入力"""
        for char in text:
            self.receive(ord(char))

    def get_tx_log(self) -> str:
        """送信ログを取得"""
        return ''.join(self.tx_log)

    def clear_tx_log(self) -> None:
        """送信ログをクリア"""
        self.tx_log.clear()

    def reset(self) -> None:
        """UARTをリセット"""
        self.smr = 0x00
        self.brr = 0xFF
        self.scr = 0x00
        self.ssr = 0x84
        self.tx_buffer.clear()
        self.rx_buffer.clear()
        self.tx_log.clear()


class VirtualBoard:
    """
    仮想RX65Nターゲットボード

    RX65Nターゲットボード相当のI/Oを提供
    """

    def __init__(self):
        self.gpio: Optional['GPIOController'] = None
        self.memory: Optional['MemoryController'] = None

        # LED定義 (RX65N Target Board相当)
        self.leds: Dict[str, LED] = {
            'LED0': LED('LED0', port=0x0D, bit=6, active_low=True),  # PD6
            'LED1': LED('LED1', port=0x0D, bit=7, active_low=True),  # PD7
            'LED2': LED('LED2', port=0x0E, bit=0, active_low=True),  # PE0
            'LED3': LED('LED3', port=0x0E, bit=1, active_low=True),  # PE1
        }

        # スイッチ定義
        self.switches: Dict[str, Switch] = {
            'SW1': Switch('SW1', port=0x00, bit=5, active_low=True),  # P05
            'SW2': Switch('SW2', port=0x00, bit=7, active_low=True),  # P07
        }

        # UART
        self.uart: VirtualUART = VirtualUART(channel=0)

        # リセット状態
        self.reset_pressed: bool = False

        # イベントコールバック
        self.led_change_callbacks: List[Callable] = []
        self.switch_change_callbacks: List[Callable] = []

    def connect_gpio(self, gpio: 'GPIOController') -> None:
        """GPIOコントローラを接続"""
        self.gpio = gpio
        # GPIO変更コールバックを登録
        gpio.register_pin_change_callback(self._on_gpio_change)

    def connect_memory(self, memory: 'MemoryController') -> None:
        """メモリコントローラを接続"""
        self.memory = memory
        self.uart.connect_memory(memory)

    def _on_gpio_change(self, port: int, register: str, value: int) -> None:
        """GPIO変更時のコールバック"""
        if register == 'podr':
            # LED状態更新
            for led in self.leds.values():
                if led.port == port:
                    pin_value = bool(value & (1 << led.bit))
                    if led.update(pin_value):
                        self._notify_led_change(led)

    def _notify_led_change(self, led: LED) -> None:
        """LED変更通知"""
        for callback in self.led_change_callbacks:
            callback(led.name, led.state)

    def _notify_switch_change(self, switch: Switch) -> None:
        """スイッチ変更通知"""
        for callback in self.switch_change_callbacks:
            callback(switch.name, switch.state)

    def press_switch(self, name: str) -> None:
        """スイッチを押す"""
        if name in self.switches:
            switch = self.switches[name]
            switch.state = SwitchState.PRESSED

            # GPIO入力を更新
            if self.gpio:
                self.gpio.set_external_input(
                    switch.port,
                    switch.bit,
                    switch.get_pin_value()
                )

            self._notify_switch_change(switch)

    def release_switch(self, name: str) -> None:
        """スイッチを離す"""
        if name in self.switches:
            switch = self.switches[name]
            switch.state = SwitchState.RELEASED

            # GPIO入力を更新
            if self.gpio:
                self.gpio.set_external_input(
                    switch.port,
                    switch.bit,
                    switch.get_pin_value()
                )

            self._notify_switch_change(switch)

    def toggle_switch(self, name: str) -> None:
        """スイッチをトグル"""
        if name in self.switches:
            switch = self.switches[name]
            if switch.state == SwitchState.PRESSED:
                self.release_switch(name)
            else:
                self.press_switch(name)

    def press_reset(self) -> None:
        """リセットスイッチを押す"""
        self.reset_pressed = True

    def release_reset(self) -> None:
        """リセットスイッチを離す"""
        self.reset_pressed = False

    def set_led(self, name: str, state: LEDState) -> None:
        """LED状態を直接設定 (テスト用)"""
        if name in self.leds:
            self.leds[name].state = state
            self._notify_led_change(self.leds[name])

    def get_led_state(self, name: str) -> Optional[LEDState]:
        """LED状態を取得"""
        if name in self.leds:
            return self.leds[name].state
        return None

    def get_switch_state(self, name: str) -> Optional[SwitchState]:
        """スイッチ状態を取得"""
        if name in self.switches:
            return self.switches[name].state
        return None

    def register_led_callback(self, callback: Callable) -> None:
        """LED変更コールバックを登録"""
        self.led_change_callbacks.append(callback)

    def register_switch_callback(self, callback: Callable) -> None:
        """スイッチ変更コールバックを登録"""
        self.switch_change_callbacks.append(callback)

    def get_state(self) -> dict:
        """ボード状態を取得"""
        return {
            'leds': {
                name: led.state.name
                for name, led in self.leds.items()
            },
            'switches': {
                name: switch.state.name
                for name, switch in self.switches.items()
            },
            'reset_pressed': self.reset_pressed,
            'uart_tx_log': self.uart.get_tx_log()[-100:],  # 最新100文字
        }

    def reset(self) -> None:
        """ボードをリセット"""
        for led in self.leds.values():
            led.state = LEDState.OFF
        for switch in self.switches.values():
            switch.state = SwitchState.RELEASED
        self.reset_pressed = False
        self.uart.reset()

    def get_led_display(self) -> str:
        """LED表示用文字列を取得 (CLI表示用)"""
        display = []
        for name, led in self.leds.items():
            symbol = '*' if led.state == LEDState.ON else 'o'
            display.append(f"{name}:{symbol}")
        return ' '.join(display)

    def get_switch_display(self) -> str:
        """スイッチ表示用文字列を取得 (CLI表示用)"""
        display = []
        for name, switch in self.switches.items():
            symbol = '[X]' if switch.state == SwitchState.PRESSED else '[ ]'
            display.append(f"{name}:{symbol}")
        return ' '.join(display)
