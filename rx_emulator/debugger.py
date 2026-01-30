"""
デバッガ/UIモジュール

内部状態可視化と操作:
- Run / Stop / Step
- レジスタ表示
- メモリ表示
- I/O状態表示
- 割り込みログ
"""

import sys
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass

from .emulator import RX65NEmulator
from .cpu import CPUState, PSWFlags


@dataclass
class DisassembledInstruction:
    """逆アセンブル結果"""
    address: int
    bytes: bytes
    mnemonic: str
    operands: str = ""

    def __str__(self) -> str:
        hex_bytes = ' '.join(f'{b:02X}' for b in self.bytes)
        if self.operands:
            return f"0x{self.address:08X}: {hex_bytes:<15} {self.mnemonic} {self.operands}"
        return f"0x{self.address:08X}: {hex_bytes:<15} {self.mnemonic}"


class SimpleDisassembler:
    """
    簡易逆アセンブラ

    基本的なRX命令の逆アセンブル
    """

    # 基本命令テーブル
    OPCODES = {
        0x02: ("RTS", 1),
        0x03: ("NOP", 1),
        0x20: ("BEQ", 2),
        0x21: ("BNE", 2),
        0x38: ("BRA.W", 3),
        0x39: ("BSR.W", 3),
        0x7E: ("PUSH.L", 2),
        0x7F: ("POP", 2),
        0xFB: ("MOV.L", 6),
    }

    def __init__(self, emulator: RX65NEmulator):
        self.emu = emulator

    def disassemble(self, address: int, count: int = 10) -> List[DisassembledInstruction]:
        """指定アドレスから逆アセンブル"""
        result = []
        current = address

        for _ in range(count):
            try:
                instr = self._disassemble_one(current)
                result.append(instr)
                current += len(instr.bytes)
            except Exception:
                # 不明な命令
                byte = self.emu.read_memory(current, 1)
                result.append(DisassembledInstruction(
                    address=current,
                    bytes=bytes([byte]),
                    mnemonic=f"DB 0x{byte:02X}",
                ))
                current += 1

        return result

    def _disassemble_one(self, address: int) -> DisassembledInstruction:
        """1命令を逆アセンブル"""
        opcode = self.emu.read_memory(address, 1)

        if opcode in self.OPCODES:
            mnemonic, size = self.OPCODES[opcode]
            inst_bytes = bytes([
                self.emu.read_memory(address + i, 1)
                for i in range(size)
            ])
            return DisassembledInstruction(
                address=address,
                bytes=inst_bytes,
                mnemonic=mnemonic,
            )

        # ADD/SUB系
        if 0x44 <= opcode <= 0x4B:
            second = self.emu.read_memory(address + 1, 1)
            rs = (second >> 4) & 0x0F
            rd = second & 0x0F
            if opcode < 0x48:
                mnemonic = "SUB"
            else:
                mnemonic = "ADD"
            return DisassembledInstruction(
                address=address,
                bytes=bytes([opcode, second]),
                mnemonic=mnemonic,
                operands=f"R{rs}, R{rd}",
            )

        # AND/OR/XOR系
        if 0x50 <= opcode <= 0x5B:
            second = self.emu.read_memory(address + 1, 1)
            rs = (second >> 4) & 0x0F
            rd = second & 0x0F
            if opcode < 0x54:
                mnemonic = "AND"
            elif opcode < 0x58:
                mnemonic = "OR"
            else:
                mnemonic = "XOR"
            return DisassembledInstruction(
                address=address,
                bytes=bytes([opcode, second]),
                mnemonic=mnemonic,
                operands=f"R{rs}, R{rd}",
            )

        # MOV系 (Load/Store)
        if 0xC0 <= opcode <= 0xCF:
            second = self.emu.read_memory(address + 1, 1)
            rs = (second >> 4) & 0x0F
            rd = second & 0x0F
            if opcode < 0xC4:
                return DisassembledInstruction(
                    address=address,
                    bytes=bytes([opcode, second]),
                    mnemonic="MOV.B",
                    operands=f"R{rs}, [R{rd}]",
                )
            elif opcode >= 0xCC:
                return DisassembledInstruction(
                    address=address,
                    bytes=bytes([opcode, second]),
                    mnemonic="MOV.B",
                    operands=f"[R{rs}], R{rd}",
                )

        if 0xE0 <= opcode <= 0xEF:
            second = self.emu.read_memory(address + 1, 1)
            rs = (second >> 4) & 0x0F
            rd = second & 0x0F
            if opcode < 0xE4:
                return DisassembledInstruction(
                    address=address,
                    bytes=bytes([opcode, second]),
                    mnemonic="MOV.L",
                    operands=f"R{rs}, [R{rd}]",
                )
            elif opcode >= 0xEC and opcode != 0xEF:
                return DisassembledInstruction(
                    address=address,
                    bytes=bytes([opcode, second]),
                    mnemonic="MOV.L",
                    operands=f"[R{rs}], R{rd}",
                )
            elif opcode == 0xEF:
                return DisassembledInstruction(
                    address=address,
                    bytes=bytes([opcode, second]),
                    mnemonic="MOV.L",
                    operands=f"R{rs}, R{rd}",
                )

        # デフォルト
        return DisassembledInstruction(
            address=address,
            bytes=bytes([opcode]),
            mnemonic=f"DB 0x{opcode:02X}",
        )


class Debugger:
    """
    デバッガ

    エミュレータのデバッグ機能を提供
    """

    def __init__(self, emulator: RX65NEmulator):
        self.emu = emulator
        self.disasm = SimpleDisassembler(emulator)

        # 履歴
        self.command_history: List[str] = []
        self.execution_history: List[dict] = []

        # ウォッチ変数
        self.watches: Dict[str, int] = {}

        # 出力コールバック
        self.output_callback: Optional[Callable] = None

    def output(self, text: str) -> None:
        """出力"""
        if self.output_callback:
            self.output_callback(text)
        else:
            print(text)

    def show_registers(self) -> None:
        """レジスタ表示"""
        state = self.emu.get_cpu_state()

        self.output("=== CPU Registers ===")
        self.output(f"PC:  0x{state['pc']:08X}    SP:  0x{state['sp']:08X}")
        self.output(f"PSW: 0x{state['psw']:08X}    IPL: {state['ipl']}")

        # フラグ
        flags = state['flags']
        flag_str = ' '.join(f"{k}={int(v)}" for k, v in flags.items())
        self.output(f"Flags: {flag_str}")

        # 汎用レジスタ
        self.output("\nGeneral Registers:")
        regs = state['registers']
        for i in range(0, 16, 4):
            line = '  '.join(f"R{j:2d}: 0x{regs[f'R{j}']:08X}" for j in range(i, min(i+4, 16)))
            self.output(line)

        self.output(f"\nCycles: {state['cycles']}  Instructions: {state['instructions']}")

    def show_memory(self, address: int, size: int = 64) -> None:
        """メモリ表示"""
        self.output(f"=== Memory Dump: 0x{address:08X} ===")
        dump = self.emu.dump_memory(address, size)
        self.output(dump)

    def show_disassembly(self, address: Optional[int] = None, count: int = 10) -> None:
        """逆アセンブル表示"""
        if address is None:
            address = self.emu.cpu.regs.pc

        self.output(f"=== Disassembly: 0x{address:08X} ===")
        instructions = self.disasm.disassemble(address, count)
        for instr in instructions:
            marker = '>' if instr.address == self.emu.cpu.regs.pc else ' '
            bp_marker = '*' if self.emu.execution.is_breakpoint(instr.address) else ' '
            self.output(f"{marker}{bp_marker} {instr}")

    def show_gpio(self) -> None:
        """GPIO状態表示"""
        self.output("=== GPIO State ===")
        state = self.emu.get_gpio_state()
        for port, info in sorted(state.items()):
            self.output(f"{port}: PDR={info['pdr']} PODR={info['podr']} PIDR={info['pidr']}")

    def show_timers(self) -> None:
        """タイマ状態表示"""
        self.output("=== Timer State ===")
        state = self.emu.get_timer_state()
        for name, info in state.items():
            running = "Running" if info['running'] else "Stopped"
            self.output(f"{name}: {running}")
            self.output(f"  CMCNT={info['cmcnt']} CMCOR={info['cmcor']}")
            self.output(f"  Divider={info['divider']} Freq={info['frequency_hz']:.2f}Hz")

    def show_interrupts(self) -> None:
        """割り込み状態表示"""
        self.output("=== Interrupt State ===")
        state = self.emu.get_interrupt_state()

        self.output(f"Nest Level: {state['nest_level']}")

        if state['pending']:
            self.output("\nPending Interrupts:")
            for item in state['pending']:
                self.output(f"  Vector {item['vector']}: {item['name']} (Priority={item['priority']})")

        if state['enabled'][:10]:  # 最初の10個
            self.output("\nEnabled Interrupts (first 10):")
            for item in state['enabled'][:10]:
                self.output(f"  Vector {item['vector']}: {item['name']} (Priority={item['priority']})")

    def show_board(self) -> None:
        """ボード状態表示"""
        self.output("=== Board State ===")
        self.output(f"LEDs:     {self.emu.get_led_display()}")
        self.output(f"Switches: {self.emu.board.get_switch_display()}")
        self.output(f"\nUART Output (last 80 chars):")
        self.output(f"  {self.emu.get_uart_log()[-80:]}")

    def show_breakpoints(self) -> None:
        """ブレークポイント表示"""
        self.output("=== Breakpoints ===")
        bps = self.emu.execution.breakpoints
        if bps:
            for bp in sorted(bps):
                self.output(f"  0x{bp:08X}")
        else:
            self.output("  (none)")

    def show_watches(self) -> None:
        """ウォッチ変数表示"""
        self.output("=== Watch Variables ===")
        if self.watches:
            for name, addr in self.watches.items():
                value = self.emu.read_memory(addr, 4)
                self.output(f"  {name} (0x{addr:08X}): 0x{value:08X}")
        else:
            self.output("  (none)")

    def add_watch(self, name: str, address: int) -> None:
        """ウォッチ変数追加"""
        self.watches[name] = address
        self.output(f"Watch added: {name} at 0x{address:08X}")

    def remove_watch(self, name: str) -> None:
        """ウォッチ変数削除"""
        if name in self.watches:
            del self.watches[name]
            self.output(f"Watch removed: {name}")
        else:
            self.output(f"Watch not found: {name}")

    def step(self, count: int = 1) -> None:
        """ステップ実行"""
        for _ in range(count):
            pc_before = self.emu.cpu.regs.pc
            self.emu.step()
            pc_after = self.emu.cpu.regs.pc

            # 履歴記録
            self.execution_history.append({
                'pc_before': pc_before,
                'pc_after': pc_after,
            })

            if self.emu.cpu.state != CPUState.RUNNING:
                break

    def run_until(self, address: int) -> int:
        """指定アドレスまで実行"""
        self.emu.add_breakpoint(address)
        executed = self.emu.run()
        self.emu.remove_breakpoint(address)
        return executed

    def show_help(self) -> None:
        """ヘルプ表示"""
        help_text = """
=== Debugger Commands ===
  r, regs       - Show registers
  m <addr> [n]  - Show memory (n bytes, default 64)
  d [addr] [n]  - Disassemble (n instructions, default 10)
  s [n]         - Step (n instructions, default 1)
  g             - Run (continue)
  b <addr>      - Toggle breakpoint
  bl            - List breakpoints
  w <name> <a>  - Add watch variable
  wr <name>     - Remove watch variable
  wl            - List watch variables
  gpio          - Show GPIO state
  timer         - Show timer state
  int           - Show interrupt state
  board         - Show board state (LEDs, switches, UART)
  sw <name>     - Press switch (SW1, SW2)
  sr <name>     - Release switch
  reset         - Reset system
  q, quit       - Quit debugger
  h, help       - Show this help
"""
        self.output(help_text)


class CLIDebugger(Debugger):
    """
    CLIデバッガ

    コマンドライン対話型デバッガ
    """

    def __init__(self, emulator: RX65NEmulator):
        super().__init__(emulator)
        self.running_cli = True

    def run_cli(self) -> None:
        """CLI実行"""
        self.output("RX65N Emulator Debugger")
        self.output("Type 'help' for commands")
        self.output("")

        self.show_registers()

        while self.running_cli:
            try:
                cmd = input("\n(rxdbg) ").strip()
                if cmd:
                    self.execute_command(cmd)
            except EOFError:
                break
            except KeyboardInterrupt:
                self.output("\nInterrupted")
                self.emu.stop()

    def execute_command(self, cmd: str) -> None:
        """コマンド実行"""
        self.command_history.append(cmd)
        parts = cmd.split()

        if not parts:
            return

        command = parts[0].lower()
        args = parts[1:]

        try:
            if command in ('r', 'regs'):
                self.show_registers()

            elif command in ('m', 'mem'):
                addr = int(args[0], 0) if args else 0
                size = int(args[1], 0) if len(args) > 1 else 64
                self.show_memory(addr, size)

            elif command in ('d', 'dis', 'disasm'):
                addr = int(args[0], 0) if args else None
                count = int(args[1]) if len(args) > 1 else 10
                self.show_disassembly(addr, count)

            elif command in ('s', 'step'):
                count = int(args[0]) if args else 1
                self.step(count)
                self.show_registers()
                self.show_disassembly(count=3)

            elif command in ('g', 'go', 'run', 'c', 'continue'):
                max_inst = int(args[0]) if args else 100000
                executed = self.emu.run(max_inst)
                self.output(f"Executed {executed} instructions")
                self.show_registers()

            elif command in ('b', 'bp', 'break'):
                if args:
                    addr = int(args[0], 0)
                    if self.emu.toggle_breakpoint(addr):
                        self.output(f"Breakpoint set at 0x{addr:08X}")
                    else:
                        self.output(f"Breakpoint removed at 0x{addr:08X}")
                else:
                    self.show_breakpoints()

            elif command in ('bl', 'blist'):
                self.show_breakpoints()

            elif command in ('w', 'watch'):
                if len(args) >= 2:
                    name = args[0]
                    addr = int(args[1], 0)
                    self.add_watch(name, addr)
                else:
                    self.show_watches()

            elif command in ('wr', 'wremove'):
                if args:
                    self.remove_watch(args[0])

            elif command in ('wl', 'wlist'):
                self.show_watches()

            elif command == 'gpio':
                self.show_gpio()

            elif command == 'timer':
                self.show_timers()

            elif command in ('int', 'interrupt'):
                self.show_interrupts()

            elif command == 'board':
                self.show_board()

            elif command == 'sw':
                if args:
                    self.emu.press_switch(args[0].upper())
                    self.output(f"Switch {args[0].upper()} pressed")

            elif command == 'sr':
                if args:
                    self.emu.release_switch(args[0].upper())
                    self.output(f"Switch {args[0].upper()} released")

            elif command == 'reset':
                self.emu.reset()
                self.output("System reset")
                self.show_registers()

            elif command in ('q', 'quit', 'exit'):
                self.running_cli = False

            elif command in ('h', 'help', '?'):
                self.show_help()

            elif command == 'set':
                if len(args) >= 2:
                    name = args[0].upper()
                    value = int(args[1], 0)
                    if self.emu.set_register(name, value):
                        self.output(f"{name} = 0x{value:08X}")
                    else:
                        self.output(f"Unknown register: {name}")

            else:
                self.output(f"Unknown command: {command}")
                self.output("Type 'help' for available commands")

        except ValueError as e:
            self.output(f"Invalid argument: {e}")
        except Exception as e:
            self.output(f"Error: {e}")
