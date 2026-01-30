"""
割り込み制御モジュール

割り込み受付・優先順位・復帰制御の再現

RX65N 割り込み構成:
- 固定ベクタ割り込み (例外)
- 可変ベクタ割り込み (周辺割り込み)
- 割り込み優先レベル (IPL): 0-15
- ネスト割り込みサポート
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Callable, Tuple, TYPE_CHECKING
from collections import deque

if TYPE_CHECKING:
    from .memory import MemoryController


class InterruptType(IntEnum):
    """割り込みタイプ"""
    RESET = 0
    UNDEFINED_INSTRUCTION = 1
    FLOATING_POINT = 2
    SOFTWARE_INTERRUPT = 3
    NMI = 4
    PERIPHERAL = 5


@dataclass
class InterruptSource:
    """割り込みソース定義"""
    vector: int
    name: str
    priority: int = 0
    enabled: bool = False
    pending: bool = False
    interrupt_type: InterruptType = InterruptType.PERIPHERAL

    def __hash__(self):
        return hash(self.vector)


class InterruptController:
    """
    割り込みコントローラ

    割り込み要求の管理と優先度制御
    """

    # 固定ベクタテーブルアドレス (RX65N)
    FIXED_VECTOR_BASE = 0xFFFFFF80

    # 可変ベクタテーブルアドレス
    VARIABLE_VECTOR_BASE = 0xFFFFFF80

    # ICUレジスタベースアドレス
    ICU_BASE = 0x00087000

    # レジスタオフセット
    IR_OFFSET = 0x0000      # 割り込み要求レジスタ
    IER_OFFSET = 0x0200     # 割り込み許可レジスタ
    IPR_OFFSET = 0x0300     # 割り込み優先レベルレジスタ

    def __init__(self):
        self.memory: Optional['MemoryController'] = None

        # 割り込みソース定義
        self.sources: Dict[int, InterruptSource] = {}

        # 割り込み要求キュー
        self.pending_queue: deque = deque()

        # 割り込みネストスタック
        self.nest_stack: List[int] = []

        # 割り込みログ
        self.interrupt_log: List[dict] = []
        self.log_enabled: bool = True

        # 割り込みコールバック
        self.interrupt_callbacks: List[Callable] = []

        # デフォルトの割り込みソースを設定
        self._setup_default_sources()

    def _setup_default_sources(self) -> None:
        """デフォルトの割り込みソースを設定"""
        # 固定ベクタ割り込み
        fixed_vectors = [
            (0, "Reset", InterruptType.RESET),
            (1, "Undefined Instruction", InterruptType.UNDEFINED_INSTRUCTION),
            (2, "Floating Point Exception", InterruptType.FLOATING_POINT),
            (3, "Reserved", InterruptType.PERIPHERAL),
            (4, "Reserved", InterruptType.PERIPHERAL),
            (5, "Reserved", InterruptType.PERIPHERAL),
            (6, "Reserved", InterruptType.PERIPHERAL),
            (7, "Reserved", InterruptType.PERIPHERAL),
            (8, "Reserved", InterruptType.PERIPHERAL),
            (9, "Reserved", InterruptType.PERIPHERAL),
            (10, "Reserved", InterruptType.PERIPHERAL),
            (11, "Reserved", InterruptType.PERIPHERAL),
            (12, "Reserved", InterruptType.PERIPHERAL),
            (13, "Reserved", InterruptType.PERIPHERAL),
            (14, "Reserved", InterruptType.PERIPHERAL),
            (15, "Reserved", InterruptType.PERIPHERAL),
        ]

        for vector, name, int_type in fixed_vectors:
            self.sources[vector] = InterruptSource(
                vector=vector,
                name=name,
                interrupt_type=int_type
            )

        # CMT割り込み
        cmt_vectors = [
            (28, "CMT0_CMI0"),
            (29, "CMT1_CMI1"),
            (30, "CMT2_CMI2"),
            (31, "CMT3_CMI3"),
        ]

        for vector, name in cmt_vectors:
            self.sources[vector] = InterruptSource(
                vector=vector,
                name=name,
                interrupt_type=InterruptType.PERIPHERAL
            )

        # 外部割り込み (IRQ0-IRQ15)
        for i in range(16):
            self.sources[64 + i] = InterruptSource(
                vector=64 + i,
                name=f"IRQ{i}",
                interrupt_type=InterruptType.PERIPHERAL
            )

        # ソフトウェア割り込み
        self.sources[27] = InterruptSource(
            vector=27,
            name="SWINT",
            interrupt_type=InterruptType.SOFTWARE_INTERRUPT
        )

    def connect_memory(self, memory: 'MemoryController') -> None:
        """メモリコントローラを接続"""
        self.memory = memory
        self._register_peripheral_handlers()

    def _register_peripheral_handlers(self) -> None:
        """周辺レジスタハンドラを登録"""
        if not self.memory:
            return

        # IR (割り込み要求) レジスタ
        for vector in range(256):
            addr = self.ICU_BASE + self.IR_OFFSET + vector
            self.memory.register_peripheral(
                addr,
                lambda a, v=vector: self._read_ir(v),
                lambda a, val, v=vector: self._write_ir(v, val)
            )

        # IER (割り込み許可) レジスタ - 8ビットごと
        for group in range(32):
            addr = self.ICU_BASE + self.IER_OFFSET + group
            self.memory.register_peripheral(
                addr,
                lambda a, g=group: self._read_ier(g),
                lambda a, val, g=group: self._write_ier(g, val)
            )

        # IPR (割り込み優先度) レジスタ
        for vector in range(256):
            addr = self.ICU_BASE + self.IPR_OFFSET + vector
            self.memory.register_peripheral(
                addr,
                lambda a, v=vector: self._read_ipr(v),
                lambda a, val, v=vector: self._write_ipr(v, val)
            )

    def _read_ir(self, vector: int) -> int:
        """IR読み込み"""
        if vector in self.sources:
            return 1 if self.sources[vector].pending else 0
        return 0

    def _write_ir(self, vector: int, value: int) -> None:
        """IR書き込み (0書き込みでクリア)"""
        if vector in self.sources and value == 0:
            self.sources[vector].pending = False

    def _read_ier(self, group: int) -> int:
        """IER読み込み"""
        value = 0
        base_vector = group * 8
        for i in range(8):
            vector = base_vector + i
            if vector in self.sources and self.sources[vector].enabled:
                value |= (1 << i)
        return value

    def _write_ier(self, group: int, value: int) -> None:
        """IER書き込み"""
        base_vector = group * 8
        for i in range(8):
            vector = base_vector + i
            if vector not in self.sources:
                self.sources[vector] = InterruptSource(
                    vector=vector,
                    name=f"INT{vector}",
                    interrupt_type=InterruptType.PERIPHERAL
                )
            self.sources[vector].enabled = bool(value & (1 << i))

    def _read_ipr(self, vector: int) -> int:
        """IPR読み込み"""
        if vector in self.sources:
            return self.sources[vector].priority
        return 0

    def _write_ipr(self, vector: int, value: int) -> None:
        """IPR書き込み"""
        if vector not in self.sources:
            self.sources[vector] = InterruptSource(
                vector=vector,
                name=f"INT{vector}",
                interrupt_type=InterruptType.PERIPHERAL
            )
        self.sources[vector].priority = value & 0x0F

    def request(self, vector: int) -> None:
        """割り込み要求"""
        if vector not in self.sources:
            self.sources[vector] = InterruptSource(
                vector=vector,
                name=f"INT{vector}",
                interrupt_type=InterruptType.PERIPHERAL
            )

        source = self.sources[vector]
        if source.enabled:
            source.pending = True
            self.pending_queue.append(vector)

            if self.log_enabled:
                self.interrupt_log.append({
                    'event': 'request',
                    'vector': vector,
                    'name': source.name,
                    'priority': source.priority,
                })

            # コールバック
            for callback in self.interrupt_callbacks:
                callback('request', vector, source)

    def get_pending_interrupt(self) -> Optional[int]:
        """
        保留中の割り込みを取得

        最も優先度の高い割り込みを返す
        """
        highest_priority = -1
        highest_vector = None

        for vector, source in self.sources.items():
            if source.pending and source.enabled:
                if source.priority > highest_priority:
                    highest_priority = source.priority
                    highest_vector = vector

        return highest_vector

    def acknowledge(self, vector: int) -> None:
        """割り込み応答 (受付)"""
        if vector in self.sources:
            source = self.sources[vector]
            source.pending = False

            # ネストスタックに追加
            self.nest_stack.append(vector)

            if self.log_enabled:
                self.interrupt_log.append({
                    'event': 'acknowledge',
                    'vector': vector,
                    'name': source.name,
                    'nest_level': len(self.nest_stack),
                })

            # コールバック
            for callback in self.interrupt_callbacks:
                callback('acknowledge', vector, source)

    def return_from_interrupt(self) -> Optional[int]:
        """割り込みから復帰"""
        if self.nest_stack:
            vector = self.nest_stack.pop()

            if self.log_enabled:
                self.interrupt_log.append({
                    'event': 'return',
                    'vector': vector,
                    'nest_level': len(self.nest_stack),
                })

            return vector
        return None

    def get_vector_address(self, vector: int) -> int:
        """割り込みベクタアドレスを取得"""
        if vector < 16:
            # 固定ベクタ
            return self.FIXED_VECTOR_BASE + (vector * 4)
        else:
            # 可変ベクタ
            return self.VARIABLE_VECTOR_BASE + (vector * 4)

    def read_handler_address(self, vector: int) -> int:
        """ハンドラアドレスを読み取り"""
        if self.memory:
            vector_addr = self.get_vector_address(vector)
            return self.memory.read32(vector_addr)
        return 0

    def register_callback(self, callback: Callable) -> None:
        """割り込みコールバックを登録"""
        self.interrupt_callbacks.append(callback)

    def set_priority(self, vector: int, priority: int) -> None:
        """割り込み優先度を設定"""
        if vector in self.sources:
            self.sources[vector].priority = priority & 0x0F

    def enable(self, vector: int) -> None:
        """割り込みを許可"""
        if vector in self.sources:
            self.sources[vector].enabled = True

    def disable(self, vector: int) -> None:
        """割り込みを禁止"""
        if vector in self.sources:
            self.sources[vector].enabled = False

    def clear_pending(self, vector: int) -> None:
        """保留をクリア"""
        if vector in self.sources:
            self.sources[vector].pending = False

    def reset(self) -> None:
        """割り込みコントローラをリセット"""
        for source in self.sources.values():
            source.enabled = False
            source.pending = False
            source.priority = 0

        self.pending_queue.clear()
        self.nest_stack.clear()
        self.interrupt_log.clear()

    def get_state(self) -> dict:
        """割り込み状態を取得"""
        pending = [
            {
                'vector': v,
                'name': self.sources[v].name,
                'priority': self.sources[v].priority,
            }
            for v in self.sources
            if self.sources[v].pending
        ]

        enabled = [
            {
                'vector': v,
                'name': self.sources[v].name,
                'priority': self.sources[v].priority,
            }
            for v in self.sources
            if self.sources[v].enabled
        ]

        return {
            'pending': pending,
            'enabled': enabled,
            'nest_level': len(self.nest_stack),
            'nest_stack': list(self.nest_stack),
        }

    def get_interrupt_log(self, limit: int = 100) -> List[dict]:
        """割り込みログを取得"""
        return list(self.interrupt_log)[-limit:]

    def clear_log(self) -> None:
        """割り込みログをクリア"""
        self.interrupt_log.clear()
