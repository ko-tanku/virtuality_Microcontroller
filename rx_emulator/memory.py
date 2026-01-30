"""
メモリ/リセットモジュール

RX65Nのメモリマップを仮想再現
- Flash（プログラム格納）
- RAM（変数・スタック）
- 周辺レジスタ領域
"""

from dataclasses import dataclass
from typing import Dict, Optional, Callable, List, Tuple
from enum import IntEnum


class MemoryRegion(IntEnum):
    """メモリ領域タイプ"""
    RAM = 0
    FLASH = 1
    PERIPHERAL = 2
    RESERVED = 3


@dataclass
class MemoryBlock:
    """メモリブロック定義"""
    name: str
    start: int
    size: int
    region_type: MemoryRegion
    data: bytearray = None
    readonly: bool = False

    def __post_init__(self):
        if self.data is None:
            self.data = bytearray(self.size)

    @property
    def end(self) -> int:
        return self.start + self.size - 1

    def contains(self, address: int) -> bool:
        return self.start <= address <= self.end


class MemoryController:
    """
    メモリコントローラ

    RX65N相当のメモリマップを管理
    """

    # RX65Nメモリマップ (主要な領域)
    # RAM: 0x00000000 - 0x0003FFFF (256KB)
    # Peripheral: 0x00080000 - 0x000FFFFF
    # Flash: 0xFFC00000 - 0xFFFFFFFF (4MB)

    def __init__(self):
        self.blocks: List[MemoryBlock] = []
        self.peripheral_handlers: Dict[int, Tuple[Callable, Callable]] = {}

        # アクセスログ (デバッグ用)
        self.access_log: List[dict] = []
        self.log_enabled: bool = False

        # メモリ変更コールバック
        self.write_callbacks: List[Callable] = []

        # デフォルトのメモリマップを設定
        self._setup_default_memory_map()

    def _setup_default_memory_map(self) -> None:
        """RX65N相当のデフォルトメモリマップを設定"""

        # 内部RAM (256KB)
        self.add_block(MemoryBlock(
            name="RAM",
            start=0x00000000,
            size=0x00040000,  # 256KB
            region_type=MemoryRegion.RAM
        ))

        # 周辺レジスタ領域
        self.add_block(MemoryBlock(
            name="Peripheral",
            start=0x00080000,
            size=0x00080000,  # 512KB
            region_type=MemoryRegion.PERIPHERAL
        ))

        # 内部Flash (2MB)
        self.add_block(MemoryBlock(
            name="Flash",
            start=0xFFE00000,
            size=0x00200000,  # 2MB
            region_type=MemoryRegion.FLASH,
            readonly=False  # プログラムロード用に書き込み可能
        ))

        # ベクタテーブル領域 (固定ベクタ)
        self.add_block(MemoryBlock(
            name="FixedVector",
            start=0xFFFFFF80,
            size=0x80,  # 128B
            region_type=MemoryRegion.FLASH,
            readonly=False
        ))

    def add_block(self, block: MemoryBlock) -> None:
        """メモリブロックを追加"""
        self.blocks.append(block)
        # アドレス順にソート
        self.blocks.sort(key=lambda b: b.start)

    def _find_block(self, address: int) -> Optional[MemoryBlock]:
        """アドレスに対応するメモリブロックを検索"""
        for block in self.blocks:
            if block.contains(address):
                return block
        return None

    def _check_peripheral(self, address: int, is_write: bool, value: int = 0) -> Tuple[bool, int]:
        """周辺レジスタアクセスをチェック"""
        if address in self.peripheral_handlers:
            read_handler, write_handler = self.peripheral_handlers[address]
            if is_write and write_handler:
                write_handler(address, value)
                return (True, value)
            elif not is_write and read_handler:
                return (True, read_handler(address))
        return (False, 0)

    def register_peripheral(self, address: int,
                           read_handler: Optional[Callable] = None,
                           write_handler: Optional[Callable] = None) -> None:
        """周辺レジスタハンドラを登録"""
        self.peripheral_handlers[address] = (read_handler, write_handler)

    def read8(self, address: int) -> int:
        """8ビット読み込み"""
        address = address & 0xFFFFFFFF

        # 周辺レジスタチェック
        handled, value = self._check_peripheral(address, False)
        if handled:
            return value & 0xFF

        block = self._find_block(address)
        if block is None:
            if self.log_enabled:
                self.access_log.append({
                    'type': 'read8',
                    'address': address,
                    'error': 'unmapped'
                })
            return 0xFF  # 未マップ領域

        offset = address - block.start
        value = block.data[offset]

        if self.log_enabled:
            self.access_log.append({
                'type': 'read8',
                'address': address,
                'value': value
            })

        return value

    def read16(self, address: int) -> int:
        """16ビット読み込み (リトルエンディアン)"""
        low = self.read8(address)
        high = self.read8(address + 1)
        return (high << 8) | low

    def read32(self, address: int) -> int:
        """32ビット読み込み (リトルエンディアン)"""
        b0 = self.read8(address)
        b1 = self.read8(address + 1)
        b2 = self.read8(address + 2)
        b3 = self.read8(address + 3)
        return (b3 << 24) | (b2 << 16) | (b1 << 8) | b0

    def write8(self, address: int, value: int) -> None:
        """8ビット書き込み"""
        address = address & 0xFFFFFFFF
        value = value & 0xFF

        # 周辺レジスタチェック
        handled, _ = self._check_peripheral(address, True, value)
        if handled:
            return

        block = self._find_block(address)
        if block is None:
            if self.log_enabled:
                self.access_log.append({
                    'type': 'write8',
                    'address': address,
                    'value': value,
                    'error': 'unmapped'
                })
            return  # 未マップ領域

        if block.readonly:
            if self.log_enabled:
                self.access_log.append({
                    'type': 'write8',
                    'address': address,
                    'value': value,
                    'error': 'readonly'
                })
            return  # 読み取り専用

        offset = address - block.start
        block.data[offset] = value

        if self.log_enabled:
            self.access_log.append({
                'type': 'write8',
                'address': address,
                'value': value
            })

        # コールバック通知
        for callback in self.write_callbacks:
            callback(address, value, 1)

    def write16(self, address: int, value: int) -> None:
        """16ビット書き込み (リトルエンディアン)"""
        self.write8(address, value & 0xFF)
        self.write8(address + 1, (value >> 8) & 0xFF)

    def write32(self, address: int, value: int) -> None:
        """32ビット書き込み (リトルエンディアン)"""
        self.write8(address, value & 0xFF)
        self.write8(address + 1, (value >> 8) & 0xFF)
        self.write8(address + 2, (value >> 16) & 0xFF)
        self.write8(address + 3, (value >> 24) & 0xFF)

    def load_binary(self, address: int, data: bytes) -> None:
        """バイナリデータをメモリにロード"""
        for i, byte in enumerate(data):
            self.write8(address + i, byte)

    def load_from_file(self, address: int, filepath: str) -> int:
        """ファイルからバイナリをロード"""
        with open(filepath, 'rb') as f:
            data = f.read()
        self.load_binary(address, data)
        return len(data)

    def dump(self, start: int, size: int) -> bytes:
        """メモリ領域をダンプ"""
        result = bytearray(size)
        for i in range(size):
            result[i] = self.read8(start + i)
        return bytes(result)

    def dump_hex(self, start: int, size: int, bytes_per_line: int = 16) -> str:
        """メモリを16進ダンプ形式で取得"""
        lines = []
        data = self.dump(start, size)

        for i in range(0, size, bytes_per_line):
            addr = start + i
            hex_part = ' '.join(f'{b:02X}' for b in data[i:i+bytes_per_line])
            ascii_part = ''.join(
                chr(b) if 32 <= b < 127 else '.'
                for b in data[i:i+bytes_per_line]
            )
            lines.append(f'{addr:08X}: {hex_part:<{bytes_per_line*3}} {ascii_part}')

        return '\n'.join(lines)

    def reset(self) -> None:
        """メモリをリセット (RAMクリア)"""
        for block in self.blocks:
            if block.region_type == MemoryRegion.RAM:
                block.data = bytearray(block.size)

    def get_memory_map(self) -> List[dict]:
        """メモリマップ情報を取得"""
        return [{
            'name': block.name,
            'start': f'0x{block.start:08X}',
            'end': f'0x{block.end:08X}',
            'size': block.size,
            'type': block.region_type.name,
            'readonly': block.readonly
        } for block in self.blocks]

    def clear_access_log(self) -> None:
        """アクセスログをクリア"""
        self.access_log.clear()


class ResetController:
    """
    リセットコントローラ

    リセット要因の管理と初期化シーケンス
    """

    class ResetSource(IntEnum):
        """リセット要因"""
        POWER_ON = 0
        EXTERNAL = 1
        WATCHDOG = 2
        SOFTWARE = 3
        LOW_VOLTAGE = 4

    def __init__(self, memory: MemoryController):
        self.memory = memory
        self.reset_source = self.ResetSource.POWER_ON
        self.reset_callbacks: List[Callable] = []

    def register_callback(self, callback: Callable) -> None:
        """リセットコールバックを登録"""
        self.reset_callbacks.append(callback)

    def trigger_reset(self, source: ResetSource = None) -> None:
        """リセットをトリガー"""
        if source:
            self.reset_source = source

        # メモリリセット
        self.memory.reset()

        # コールバック実行
        for callback in self.reset_callbacks:
            callback(self.reset_source)

    def get_reset_source(self) -> ResetSource:
        """最後のリセット要因を取得"""
        return self.reset_source
