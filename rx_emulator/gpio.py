"""
GPIOモジュール

入出力ポート制御の再現

RX65N GPIO構成:
- PORT0 〜 PORTE (15ポート)
- 各ポート最大8ビット
- 方向レジスタ (PDR)
- 出力データレジスタ (PODR)
- 入力データレジスタ (PIDR)
- プルアップ制御レジスタ (PCR)
- 駆動能力制御レジスタ (DSCR)
"""

from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from typing import Dict, List, Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .memory import MemoryController


class PinDirection(IntEnum):
    """ピン方向"""
    INPUT = 0
    OUTPUT = 1


class PinMode(IntEnum):
    """ピンモード"""
    GPIO = 0
    PERIPHERAL = 1


@dataclass
class GPIOPin:
    """単一GPIOピン"""
    port: int
    bit: int
    direction: PinDirection = PinDirection.INPUT
    mode: PinMode = PinMode.GPIO
    output_value: bool = False
    input_value: bool = False
    pullup_enabled: bool = False

    @property
    def name(self) -> str:
        return f"P{self.port:X}{self.bit}"

    def read(self) -> bool:
        """ピン値を読み取り"""
        if self.direction == PinDirection.OUTPUT:
            return self.output_value
        return self.input_value

    def write(self, value: bool) -> None:
        """ピン値を書き込み"""
        if self.direction == PinDirection.OUTPUT:
            self.output_value = value


@dataclass
class GPIOPort:
    """GPIOポート (8ビット)"""
    number: int
    pins: List[GPIOPin] = field(default_factory=list)

    # レジスタ値
    pdr: int = 0x00    # 方向レジスタ (0=入力, 1=出力)
    podr: int = 0x00   # 出力データレジスタ
    pidr: int = 0x00   # 入力データレジスタ
    pcr: int = 0x00    # プルアップ制御レジスタ
    pmr: int = 0x00    # ピンモードレジスタ (0=GPIO, 1=周辺)

    def __post_init__(self):
        if not self.pins:
            self.pins = [GPIOPin(self.number, i) for i in range(8)]

    @property
    def name(self) -> str:
        return f"PORT{self.number:X}"

    def read_pidr(self) -> int:
        """PIDR読み取り"""
        value = 0
        for i, pin in enumerate(self.pins):
            if pin.read():
                value |= (1 << i)
        return value

    def write_pdr(self, value: int) -> None:
        """PDR書き込み"""
        self.pdr = value & 0xFF
        for i, pin in enumerate(self.pins):
            pin.direction = PinDirection.OUTPUT if (value & (1 << i)) else PinDirection.INPUT

    def write_podr(self, value: int) -> None:
        """PODR書き込み"""
        self.podr = value & 0xFF
        for i, pin in enumerate(self.pins):
            pin.output_value = bool(value & (1 << i))

    def write_pcr(self, value: int) -> None:
        """PCR書き込み"""
        self.pcr = value & 0xFF
        for i, pin in enumerate(self.pins):
            pin.pullup_enabled = bool(value & (1 << i))

    def write_pmr(self, value: int) -> None:
        """PMR書き込み"""
        self.pmr = value & 0xFF
        for i, pin in enumerate(self.pins):
            pin.mode = PinMode.PERIPHERAL if (value & (1 << i)) else PinMode.GPIO

    def set_external_input(self, bit: int, value: bool) -> None:
        """外部入力設定"""
        if 0 <= bit < 8:
            self.pins[bit].input_value = value
            if value:
                self.pidr |= (1 << bit)
            else:
                self.pidr &= ~(1 << bit)


class GPIOController:
    """
    GPIOコントローラ

    RX65Nの入出力ポートを管理
    """

    # ポートベースアドレス (RX65N)
    PORT_BASE = 0x0008C000

    # レジスタオフセット
    PDR_OFFSET = 0x0000   # 方向レジスタ
    PODR_OFFSET = 0x0020  # 出力データレジスタ
    PIDR_OFFSET = 0x0040  # 入力データレジスタ
    PMR_OFFSET = 0x0060   # ピンモードレジスタ
    PCR_OFFSET = 0x00C0   # プルアップ制御レジスタ

    # ポート数
    NUM_PORTS = 15  # PORT0-PORTE

    def __init__(self):
        self.ports: Dict[int, GPIOPort] = {}
        self.memory: Optional['MemoryController'] = None

        # ピン変更コールバック
        self.pin_change_callbacks: List[Callable] = []

        # ポート初期化
        for i in range(self.NUM_PORTS):
            self.ports[i] = GPIOPort(i)

    def connect_memory(self, memory: 'MemoryController') -> None:
        """メモリコントローラを接続"""
        self.memory = memory
        self._register_peripheral_handlers()

    def _register_peripheral_handlers(self) -> None:
        """周辺レジスタハンドラを登録"""
        if not self.memory:
            return

        for port_num in range(self.NUM_PORTS):
            # PDR
            addr = self.PORT_BASE + self.PDR_OFFSET + port_num
            self.memory.register_peripheral(
                addr,
                lambda a, p=port_num: self._read_pdr(p),
                lambda a, v, p=port_num: self._write_pdr(p, v)
            )

            # PODR
            addr = self.PORT_BASE + self.PODR_OFFSET + port_num
            self.memory.register_peripheral(
                addr,
                lambda a, p=port_num: self._read_podr(p),
                lambda a, v, p=port_num: self._write_podr(p, v)
            )

            # PIDR
            addr = self.PORT_BASE + self.PIDR_OFFSET + port_num
            self.memory.register_peripheral(
                addr,
                lambda a, p=port_num: self._read_pidr(p),
                None  # 読み取り専用
            )

            # PMR
            addr = self.PORT_BASE + self.PMR_OFFSET + port_num
            self.memory.register_peripheral(
                addr,
                lambda a, p=port_num: self._read_pmr(p),
                lambda a, v, p=port_num: self._write_pmr(p, v)
            )

            # PCR
            addr = self.PORT_BASE + self.PCR_OFFSET + port_num
            self.memory.register_peripheral(
                addr,
                lambda a, p=port_num: self._read_pcr(p),
                lambda a, v, p=port_num: self._write_pcr(p, v)
            )

    def _read_pdr(self, port: int) -> int:
        return self.ports[port].pdr

    def _write_pdr(self, port: int, value: int) -> None:
        old_value = self.ports[port].pdr
        self.ports[port].write_pdr(value)
        if old_value != value:
            self._notify_change(port, 'pdr', value)

    def _read_podr(self, port: int) -> int:
        return self.ports[port].podr

    def _write_podr(self, port: int, value: int) -> None:
        old_value = self.ports[port].podr
        self.ports[port].write_podr(value)
        if old_value != value:
            self._notify_change(port, 'podr', value)

    def _read_pidr(self, port: int) -> int:
        return self.ports[port].read_pidr()

    def _read_pmr(self, port: int) -> int:
        return self.ports[port].pmr

    def _write_pmr(self, port: int, value: int) -> None:
        self.ports[port].write_pmr(value)

    def _read_pcr(self, port: int) -> int:
        return self.ports[port].pcr

    def _write_pcr(self, port: int, value: int) -> None:
        self.ports[port].write_pcr(value)

    def _notify_change(self, port: int, register: str, value: int) -> None:
        """変更通知"""
        for callback in self.pin_change_callbacks:
            callback(port, register, value)

    def register_pin_change_callback(self, callback: Callable) -> None:
        """ピン変更コールバックを登録"""
        self.pin_change_callbacks.append(callback)

    def get_pin(self, port: int, bit: int) -> Optional[GPIOPin]:
        """ピンを取得"""
        if port in self.ports and 0 <= bit < 8:
            return self.ports[port].pins[bit]
        return None

    def read_pin(self, port: int, bit: int) -> bool:
        """ピン値を読み取り"""
        pin = self.get_pin(port, bit)
        return pin.read() if pin else False

    def write_pin(self, port: int, bit: int, value: bool) -> None:
        """ピン値を書き込み"""
        pin = self.get_pin(port, bit)
        if pin:
            pin.write(value)
            # PODRも更新
            if value:
                self.ports[port].podr |= (1 << bit)
            else:
                self.ports[port].podr &= ~(1 << bit)

    def set_external_input(self, port: int, bit: int, value: bool) -> None:
        """外部入力を設定 (スイッチなど)"""
        if port in self.ports:
            self.ports[port].set_external_input(bit, value)

    def get_output_byte(self, port: int) -> int:
        """ポート出力バイト値を取得"""
        if port in self.ports:
            return self.ports[port].podr
        return 0

    def get_input_byte(self, port: int) -> int:
        """ポート入力バイト値を取得"""
        if port in self.ports:
            return self.ports[port].read_pidr()
        return 0

    def reset(self) -> None:
        """GPIOをリセット"""
        for port in self.ports.values():
            port.pdr = 0x00
            port.podr = 0x00
            port.pidr = 0x00
            port.pcr = 0x00
            port.pmr = 0x00
            for pin in port.pins:
                pin.direction = PinDirection.INPUT
                pin.mode = PinMode.GPIO
                pin.output_value = False
                pin.pullup_enabled = False

    def get_state(self) -> dict:
        """GPIO状態を取得"""
        return {
            f'PORT{p:X}': {
                'pdr': f'0x{port.pdr:02X}',
                'podr': f'0x{port.podr:02X}',
                'pidr': f'0x{port.read_pidr():02X}',
                'pmr': f'0x{port.pmr:02X}',
                'pcr': f'0x{port.pcr:02X}',
            }
            for p, port in self.ports.items()
        }

    def get_port_state(self, port: int) -> Optional[dict]:
        """特定ポートの状態を取得"""
        if port not in self.ports:
            return None

        p = self.ports[port]
        return {
            'name': p.name,
            'pdr': f'0x{p.pdr:02X}',
            'podr': f'0x{p.podr:02X}',
            'pidr': f'0x{p.read_pidr():02X}',
            'pmr': f'0x{p.pmr:02X}',
            'pcr': f'0x{p.pcr:02X}',
            'pins': [
                {
                    'name': pin.name,
                    'direction': pin.direction.name,
                    'mode': pin.mode.name,
                    'output': pin.output_value,
                    'input': pin.input_value,
                    'pullup': pin.pullup_enabled,
                }
                for pin in p.pins
            ]
        }
