"""
RX65Nエミュレータ メインモジュール

全モジュールを統合してRX65Nマイコン仮想環境を提供
"""

from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass

from .cpu import RXCpu, CPUState
from .memory import MemoryController, ResetController
from .clock import ClockController, ExecutionController
from .gpio import GPIOController
from .timer import TimerController
from .interrupt import InterruptController
from .loader import ELFLoader, SRecordLoader, IntelHexLoader, BinaryLoader, LoadResult
from .board import VirtualBoard


@dataclass
class EmulatorConfig:
    """エミュレータ設定"""
    # クロック設定
    clock_hz: int = 120000000  # 120MHz

    # メモリ設定
    ram_size: int = 0x40000    # 256KB
    flash_size: int = 0x200000  # 2MB

    # 実行設定
    max_cycles_per_step: int = 1000

    # デバッグ設定
    trace_enabled: bool = False
    memory_log_enabled: bool = False


class RX65NEmulator:
    """
    RX65N仮想エミュレータ

    全てのコンポーネントを統合して仮想RX65N環境を提供
    """

    def __init__(self, config: Optional[EmulatorConfig] = None):
        self.config = config or EmulatorConfig()

        # コンポーネント初期化
        self.cpu = RXCpu()
        self.memory = MemoryController()
        self.reset_controller = ResetController(self.memory)
        self.clock = ClockController()
        self.execution = ExecutionController()
        self.gpio = GPIOController()
        self.timer = TimerController()
        self.interrupt = InterruptController()
        self.board = VirtualBoard()

        # ローダー
        self.elf_loader = ELFLoader()
        self.srec_loader = SRecordLoader()
        self.hex_loader = IntelHexLoader()
        self.bin_loader = BinaryLoader()

        # コンポーネント接続
        self._connect_components()

        # イベントコールバック
        self.on_step: Optional[Callable] = None
        self.on_halt: Optional[Callable] = None
        self.on_breakpoint: Optional[Callable] = None
        self.on_error: Optional[Callable] = None

        # 実行状態
        self.running: bool = False
        self.last_error: Optional[str] = None

    def _connect_components(self) -> None:
        """コンポーネントを相互接続"""
        # CPU接続
        self.cpu.connect_memory(self.memory)
        self.cpu.connect_interrupt_controller(self.interrupt)

        # クロック接続
        self.clock.connect_memory(self.memory)

        # GPIO接続
        self.gpio.connect_memory(self.memory)

        # タイマ接続
        self.timer.connect_memory(self.memory)
        self.timer.connect_interrupt_controller(self.interrupt)

        # 割り込み接続
        self.interrupt.connect_memory(self.memory)

        # ローダー接続
        self.elf_loader.connect_memory(self.memory)
        self.srec_loader.connect_memory(self.memory)
        self.hex_loader.connect_memory(self.memory)
        self.bin_loader.connect_memory(self.memory)

        # ボード接続
        self.board.connect_gpio(self.gpio)
        self.board.connect_memory(self.memory)

        # リセットコールバック
        self.reset_controller.register_callback(self._on_reset)

        # クロックティックコールバック
        self.clock.register_tick_callback(self._on_clock_tick)

    def _on_reset(self, source) -> None:
        """リセット時の処理"""
        self.cpu.reset()
        self.gpio.reset()
        self.timer.reset()
        self.interrupt.reset()
        self.board.reset()
        self.clock.reset()

    def _on_clock_tick(self, cycles: int) -> None:
        """クロックティック時の処理"""
        self.timer.tick(cycles)

    def load_program(self, filepath: str, load_address: Optional[int] = None) -> LoadResult:
        """プログラムをロード"""
        ext = filepath.lower().split('.')[-1]

        if ext in ('elf', 'abs', 'out'):
            result = self.elf_loader.load_elf(filepath)
        elif ext in ('mot', 'srec', 's'):
            result = self.srec_loader.load_srec(filepath)
        elif ext in ('hex', 'ihex'):
            result = self.hex_loader.load_hex(filepath)
        elif ext == 'bin':
            addr = load_address or 0xFFE00000
            result = self.bin_loader.load_binary(filepath, addr)
        else:
            # デフォルトはバイナリとして処理
            addr = load_address or 0xFFE00000
            result = self.bin_loader.load_binary(filepath, addr)

        if result.success:
            self.cpu.regs.pc = result.entry_point

        return result

    def load_binary_data(self, data: bytes, address: int) -> None:
        """バイナリデータを直接ロード"""
        self.memory.load_binary(address, data)

    def reset(self) -> None:
        """システムリセット"""
        self.reset_controller.trigger_reset()
        self.running = False
        self.last_error = None

    def step(self) -> bool:
        """1命令実行"""
        try:
            # ブレークポイントチェック
            if self.execution.is_breakpoint(self.cpu.regs.pc):
                if self.on_breakpoint:
                    self.on_breakpoint(self.cpu.regs.pc)
                return False

            # CPU実行
            result = self.cpu.step()

            # クロックティック
            self.clock.tick(self.cpu.cycle_count)

            # コールバック
            if self.on_step:
                self.on_step(self.cpu.regs.pc, self.cpu.instruction_count)

            return result

        except Exception as e:
            self.last_error = str(e)
            self.running = False
            if self.on_error:
                self.on_error(str(e))
            return False

    def run(self, max_instructions: int = 0) -> int:
        """連続実行"""
        self.running = True
        executed = 0

        try:
            while self.running:
                if max_instructions > 0 and executed >= max_instructions:
                    break

                if not self.step():
                    break

                executed += 1

        except Exception as e:
            self.last_error = str(e)
            if self.on_error:
                self.on_error(str(e))

        self.running = False
        return executed

    def stop(self) -> None:
        """実行停止"""
        self.running = False
        self.cpu.stop()

    def add_breakpoint(self, address: int) -> None:
        """ブレークポイント追加"""
        self.execution.add_breakpoint(address)
        self.cpu.breakpoints.add(address)

    def remove_breakpoint(self, address: int) -> None:
        """ブレークポイント削除"""
        self.execution.remove_breakpoint(address)
        self.cpu.breakpoints.discard(address)

    def toggle_breakpoint(self, address: int) -> bool:
        """ブレークポイントトグル"""
        return self.execution.toggle_breakpoint(address)

    def get_register(self, name: str) -> Optional[int]:
        """レジスタ値取得"""
        name = name.upper()
        if name == 'PC':
            return self.cpu.regs.pc
        elif name == 'SP':
            return self.cpu.regs.sp
        elif name == 'PSW':
            return self.cpu.regs.psw
        elif name.startswith('R') and name[1:].isdigit():
            idx = int(name[1:])
            if 0 <= idx < 16:
                return self.cpu.regs.r[idx]
        return None

    def set_register(self, name: str, value: int) -> bool:
        """レジスタ値設定"""
        name = name.upper()
        value = value & 0xFFFFFFFF

        if name == 'PC':
            self.cpu.regs.pc = value
            return True
        elif name == 'SP':
            self.cpu.regs.sp = value
            return True
        elif name == 'PSW':
            self.cpu.regs.psw = value
            return True
        elif name.startswith('R') and name[1:].isdigit():
            idx = int(name[1:])
            if 0 <= idx < 16:
                self.cpu.regs.r[idx] = value
                return True
        return False

    def read_memory(self, address: int, size: int = 1) -> int:
        """メモリ読み込み"""
        if size == 1:
            return self.memory.read8(address)
        elif size == 2:
            return self.memory.read16(address)
        elif size == 4:
            return self.memory.read32(address)
        return 0

    def write_memory(self, address: int, value: int, size: int = 1) -> None:
        """メモリ書き込み"""
        if size == 1:
            self.memory.write8(address, value)
        elif size == 2:
            self.memory.write16(address, value)
        elif size == 4:
            self.memory.write32(address, value)

    def dump_memory(self, start: int, size: int) -> str:
        """メモリダンプ"""
        return self.memory.dump_hex(start, size)

    def get_state(self) -> dict:
        """システム状態取得"""
        return {
            'cpu': self.cpu.get_state(),
            'clock': self.clock.get_state(),
            'execution': self.execution.get_state(),
            'interrupt': self.interrupt.get_state(),
            'board': self.board.get_state(),
            'last_error': self.last_error,
        }

    def get_cpu_state(self) -> dict:
        """CPU状態取得"""
        return self.cpu.get_state()

    def get_gpio_state(self) -> dict:
        """GPIO状態取得"""
        return self.gpio.get_state()

    def get_timer_state(self) -> dict:
        """タイマ状態取得"""
        return self.timer.get_state()

    def get_interrupt_state(self) -> dict:
        """割り込み状態取得"""
        return self.interrupt.get_state()

    def get_board_state(self) -> dict:
        """ボード状態取得"""
        return self.board.get_state()

    def press_switch(self, name: str) -> None:
        """スイッチを押す"""
        self.board.press_switch(name)

    def release_switch(self, name: str) -> None:
        """スイッチを離す"""
        self.board.release_switch(name)

    def get_led_display(self) -> str:
        """LED表示取得"""
        return self.board.get_led_display()

    def get_uart_log(self) -> str:
        """UART送信ログ取得"""
        return self.board.uart.get_tx_log()

    def uart_input(self, text: str) -> None:
        """UART入力"""
        self.board.uart.receive_string(text)

    def get_symbol_address(self, name: str) -> Optional[int]:
        """シンボルアドレス取得"""
        return self.elf_loader.get_symbol_address(name)

    def get_memory_map(self) -> List[dict]:
        """メモリマップ取得"""
        return self.memory.get_memory_map()
