"""
ビジュアルUI モジュール

マイコンボードを視覚的に表示するターミナルUI
- ボード全体のブロック図
- LED/スイッチの状態表示
- CPUレジスタのリアルタイム表示
- メモリマップの可視化
- 配線/信号フローの表示
"""

import os
import sys
import time
import threading
from typing import Optional, Callable, List, Dict, Any

try:
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich.style import Style
    from rich.box import ROUNDED, HEAVY, DOUBLE
    from rich.align import Align
    from rich.columns import Columns
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    # ダミー定義
    Console = None
    Panel = None
    Table = None
    Layout = None
    Live = None
    Text = None
    Style = None
    ROUNDED = None
    HEAVY = None
    DOUBLE = None
    Align = None
    Columns = None
    box = None
    Group = None

from .emulator import RX65NEmulator
from .cpu import CPUState, PSWFlags
from .board import LEDState, SwitchState


class BoardVisualizer:
    """
    マイコンボードのビジュアル表示

    ASCIIアートでRX65Nターゲットボードを描画
    """

    # LED表示用の文字
    LED_ON = "●"
    LED_OFF = "○"

    # スイッチ表示用の文字
    SW_PRESSED = "[■]"
    SW_RELEASED = "[ ]"

    # 配線表示用の文字
    WIRE_H = "─"
    WIRE_V = "│"
    WIRE_CORNER_TL = "┌"
    WIRE_CORNER_TR = "┐"
    WIRE_CORNER_BL = "└"
    WIRE_CORNER_BR = "┘"
    WIRE_T_DOWN = "┬"
    WIRE_T_UP = "┴"
    WIRE_T_RIGHT = "├"
    WIRE_T_LEFT = "┤"
    WIRE_CROSS = "┼"

    def __init__(self, emulator: RX65NEmulator):
        self.emu = emulator

    def get_led_display(self, led_name: str) -> tuple:
        """LED表示を取得 (文字, 色)"""
        state = self.emu.board.get_led_state(led_name)
        if state == LEDState.ON:
            return (self.LED_ON, "bright_green")
        return (self.LED_OFF, "dim")

    def get_switch_display(self, sw_name: str) -> tuple:
        """スイッチ表示を取得 (文字, 色)"""
        state = self.emu.board.get_switch_state(sw_name)
        if state == SwitchState.PRESSED:
            return (self.SW_PRESSED, "bright_yellow")
        return (self.SW_RELEASED, "dim")

    def draw_board_ascii(self) -> str:
        """ボードのASCIIアート表示"""
        # LED状態
        led0 = self.LED_ON if self.emu.board.get_led_state('LED0') == LEDState.ON else self.LED_OFF
        led1 = self.LED_ON if self.emu.board.get_led_state('LED1') == LEDState.ON else self.LED_OFF
        led2 = self.LED_ON if self.emu.board.get_led_state('LED2') == LEDState.ON else self.LED_OFF
        led3 = self.LED_ON if self.emu.board.get_led_state('LED3') == LEDState.ON else self.LED_OFF

        # スイッチ状態
        sw1 = self.SW_PRESSED if self.emu.board.get_switch_state('SW1') == SwitchState.PRESSED else self.SW_RELEASED
        sw2 = self.SW_PRESSED if self.emu.board.get_switch_state('SW2') == SwitchState.PRESSED else self.SW_RELEASED

        board = f"""
╔══════════════════════════════════════════════════════════════════╗
║                    RX65N Target Board                            ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║   ┌──────────┐         ┌──────────────────────┐                  ║
║   │          │         │      MEMORY          │                  ║
║   │   RX65N  │◄───────►│  Flash: 2MB          │                  ║
║   │   CPU    │  BUS    │  RAM:   256KB        │                  ║
║   │          │         │                      │                  ║
║   └────┬─────┘         └──────────────────────┘                  ║
║        │                                                         ║
║        │ GPIO                                                    ║
║   ┌────┴─────┐                                                   ║
║   │  PORTD   │───────►  LED0:{led0}  LED1:{led1}  LED2:{led2}  LED3:{led3}      ║
║   │  PORTE   │                                                   ║
║   └────┬─────┘                                                   ║
║        │                                                         ║
║   ┌────┴─────┐         ┌────────────┐                            ║
║   │  PORT0   │◄────────│   SW1 {sw1} │                            ║
║   │          │◄────────│   SW2 {sw2} │                            ║
║   └────┬─────┘         └────────────┘                            ║
║        │                                                         ║
║   ┌────┴─────┐         ┌────────────┐                            ║
║   │  TIMER   │────────►│  Interrupt │                            ║
║   │  CMT0-3  │         │ Controller │                            ║
║   └──────────┘         └────────────┘                            ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝"""
        return board


class RichVisualUI:
    """
    Rich ライブラリを使ったビジュアルUI
    """

    def __init__(self, emulator: RX65NEmulator):
        if not RICH_AVAILABLE:
            raise ImportError("rich library is required. Install with: pip install rich")

        self.emu = emulator
        self.console = Console()
        self.running = False
        self.visualizer = BoardVisualizer(emulator)

        # キー入力用
        self.command_queue = []

    def create_cpu_panel(self) -> Panel:
        """CPUステータスパネルを作成"""
        state = self.emu.get_cpu_state()

        # レジスタテーブル
        table = Table(show_header=True, header_style="bold cyan", box=box.SIMPLE)
        table.add_column("Register", style="cyan", width=8)
        table.add_column("Value", style="green", width=12)
        table.add_column("Register", style="cyan", width=8)
        table.add_column("Value", style="green", width=12)

        regs = state['registers']
        for i in range(0, 16, 2):
            table.add_row(
                f"R{i}", f"0x{regs[f'R{i}']:08X}",
                f"R{i+1}", f"0x{regs[f'R{i+1}']:08X}"
            )

        # PC, SP, PSW
        pc_sp = Text()
        pc_sp.append("PC: ", style="bold yellow")
        pc_sp.append(f"0x{state['pc']:08X}\n", style="bright_green")
        pc_sp.append("SP: ", style="bold yellow")
        pc_sp.append(f"0x{state['sp']:08X}\n", style="bright_green")
        pc_sp.append("PSW: ", style="bold yellow")
        pc_sp.append(f"0x{state['psw']:08X}", style="bright_green")

        # フラグ
        flags = state['flags']
        flag_text = Text("\n\nFlags: ")
        for name, value in flags.items():
            color = "bright_green" if value else "dim"
            flag_text.append(f"{name}={int(value)} ", style=color)

        # IPL
        flag_text.append(f"\nIPL: {state['ipl']}", style="yellow")

        # 実行状態
        cpu_state = Text(f"\n\nState: {state['state']}",
                         style="bright_green" if state['state'] == 'RUNNING' else "yellow")
        cpu_state.append(f"\nCycles: {state['cycles']}")
        cpu_state.append(f"\nInstructions: {state['instructions']}")

        content = Group(pc_sp, table, flag_text, cpu_state)

        return Panel(content, title="[bold blue]CPU - RX65N[/bold blue]",
                    border_style="blue", box=ROUNDED)

    def create_memory_panel(self) -> Panel:
        """メモリパネルを作成"""
        # メモリマップ表示
        table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
        table.add_column("Region", style="cyan", width=12)
        table.add_column("Start", style="green", width=12)
        table.add_column("Size", style="yellow", width=10)

        mem_map = self.emu.get_memory_map()
        for region in mem_map[:5]:  # 最初の5領域
            size_str = f"{region['size'] // 1024}KB" if region['size'] >= 1024 else f"{region['size']}B"
            table.add_row(region['name'], region['start'], size_str)

        # 現在のPC周辺のメモリ
        pc = self.emu.cpu.regs.pc
        mem_text = Text("\n\nMemory around PC:\n", style="bold")

        start = max(0, pc - 8)
        for i in range(0, 16, 4):
            addr = start + i
            val = self.emu.read_memory(addr, 4)
            marker = "► " if addr <= pc < addr + 4 else "  "
            mem_text.append(f"{marker}0x{addr:08X}: 0x{val:08X}\n",
                          style="bright_green" if marker == "► " else "dim")

        content = Group(table, mem_text)

        return Panel(content, title="[bold magenta]Memory[/bold magenta]",
                    border_style="magenta", box=ROUNDED)

    def create_board_panel(self) -> Panel:
        """ボードパネルを作成"""
        # LED表示
        led_text = Text("LEDs:\n", style="bold")
        for i in range(4):
            name = f"LED{i}"
            char, color = self.visualizer.get_led_display(name)
            led_text.append(f"  {name}: ", style="white")
            led_text.append(f"{char}", style=color)
            led_text.append("  ")

        # スイッチ表示
        sw_text = Text("\n\nSwitches:\n", style="bold")
        for name in ['SW1', 'SW2']:
            char, color = self.visualizer.get_switch_display(name)
            sw_text.append(f"  {name}: ", style="white")
            sw_text.append(f"{char}", style=color)
            sw_text.append("  ")

        # UART出力
        uart_text = Text("\n\nUART Output:\n", style="bold")
        uart_log = self.emu.get_uart_log()[-40:]  # 最新40文字
        uart_text.append(f"  {uart_log if uart_log else '(empty)'}", style="cyan")

        content = Group(led_text, sw_text, uart_text)

        return Panel(content, title="[bold green]I/O Board[/bold green]",
                    border_style="green", box=ROUNDED)

    def create_gpio_panel(self) -> Panel:
        """GPIOパネルを作成"""
        table = Table(show_header=True, header_style="bold yellow", box=box.SIMPLE)
        table.add_column("Port", style="cyan", width=8)
        table.add_column("PDR", style="green", width=6)
        table.add_column("PODR", style="yellow", width=6)
        table.add_column("PIDR", style="magenta", width=6)

        gpio_state = self.emu.get_gpio_state()
        # 主要なポートのみ表示
        for port_name in ['PORT0', 'PORTD', 'PORTE']:
            if port_name in gpio_state:
                info = gpio_state[port_name]
                table.add_row(port_name, info['pdr'], info['podr'], info['pidr'])

        # ビット表示
        portd_podr = self.emu.gpio.ports[0x0D].podr
        bit_text = Text("\n\nPORTD Bits (Output):\n", style="bold")
        for i in range(7, -1, -1):
            bit_val = (portd_podr >> i) & 1
            color = "bright_green" if bit_val else "dim"
            bit_text.append(f" {bit_val}", style=color)
        bit_text.append("\n  7 6 5 4 3 2 1 0", style="dim")

        content = Group(table, bit_text)

        return Panel(content, title="[bold yellow]GPIO Ports[/bold yellow]",
                    border_style="yellow", box=ROUNDED)

    def create_timer_panel(self) -> Panel:
        """タイマパネルを作成"""
        timer_state = self.emu.get_timer_state()

        table = Table(show_header=True, header_style="bold red", box=box.SIMPLE)
        table.add_column("Timer", style="cyan", width=8)
        table.add_column("CMCNT", style="green", width=8)
        table.add_column("CMCOR", style="yellow", width=8)
        table.add_column("Status", style="magenta", width=10)

        for name, info in timer_state.items():
            status = "Running" if info['running'] else "Stopped"
            status_style = "bright_green" if info['running'] else "dim"
            table.add_row(
                name,
                str(info['cmcnt']),
                str(info['cmcor']),
                Text(status, style=status_style)
            )

        return Panel(table, title="[bold red]Timers (CMT)[/bold red]",
                    border_style="red", box=ROUNDED)

    def create_interrupt_panel(self) -> Panel:
        """割り込みパネルを作成"""
        int_state = self.emu.get_interrupt_state()

        text = Text()
        text.append(f"Nest Level: {int_state['nest_level']}\n", style="bold")

        text.append("\nPending: ", style="yellow")
        if int_state['pending']:
            for item in int_state['pending'][:3]:
                text.append(f"\n  Vector {item['vector']}: {item['name']}", style="bright_red")
        else:
            text.append("None", style="dim")

        text.append("\n\nEnabled IRQs: ", style="cyan")
        enabled_count = len(int_state['enabled'])
        text.append(f"{enabled_count}", style="bright_green" if enabled_count > 0 else "dim")

        return Panel(text, title="[bold cyan]Interrupts[/bold cyan]",
                    border_style="cyan", box=ROUNDED)

    def create_help_panel(self) -> Panel:
        """ヘルプパネルを作成"""
        help_text = Text()
        help_text.append("Commands:\n", style="bold")
        help_text.append("  s      ", style="cyan")
        help_text.append("Step\n", style="dim")
        help_text.append("  r      ", style="cyan")
        help_text.append("Run (100 inst)\n", style="dim")
        help_text.append("  1/2    ", style="cyan")
        help_text.append("Press SW1/SW2\n", style="dim")
        help_text.append("  !/@    ", style="cyan")
        help_text.append("Release SW1/SW2\n", style="dim")
        help_text.append("  x      ", style="cyan")
        help_text.append("Reset\n", style="dim")
        help_text.append("  q      ", style="cyan")
        help_text.append("Quit\n", style="dim")

        return Panel(help_text, title="[bold white]Help[/bold white]",
                    border_style="white", box=ROUNDED)

    def create_layout(self) -> Layout:
        """全体レイアウトを作成"""
        layout = Layout()

        # 上部: ボード図
        # 中部: CPU | Memory | GPIO
        # 下部: Timer | Interrupt | Help

        layout.split_column(
            Layout(name="board", size=3),
            Layout(name="upper", size=20),
            Layout(name="lower", size=12)
        )

        layout["upper"].split_row(
            Layout(name="cpu"),
            Layout(name="memory"),
            Layout(name="gpio")
        )

        layout["lower"].split_row(
            Layout(name="io_board"),
            Layout(name="timer"),
            Layout(name="interrupt"),
            Layout(name="help")
        )

        return layout

    def update_layout(self, layout: Layout) -> None:
        """レイアウトを更新"""
        # タイトルバー
        title = Text("RX65N Virtual Microcontroller Emulator", style="bold white on blue", justify="center")
        layout["board"].update(Panel(title, box=HEAVY, border_style="blue"))

        # 各パネル更新
        layout["cpu"].update(self.create_cpu_panel())
        layout["memory"].update(self.create_memory_panel())
        layout["gpio"].update(self.create_gpio_panel())
        layout["io_board"].update(self.create_board_panel())
        layout["timer"].update(self.create_timer_panel())
        layout["interrupt"].update(self.create_interrupt_panel())
        layout["help"].update(self.create_help_panel())

    def run_interactive(self) -> None:
        """インタラクティブモードで実行"""
        layout = self.create_layout()

        self.console.print("\n[bold cyan]RX65N Visual Emulator[/bold cyan]")
        self.console.print("Press keys to control. 'q' to quit.\n")

        # デモプログラムをロード
        from .__main__ import load_demo_program
        load_demo_program(self.emu)

        self.running = True

        try:
            with Live(layout, console=self.console, refresh_per_second=10, screen=True) as live:
                while self.running:
                    # レイアウト更新
                    self.update_layout(layout)

                    # 非ブロッキングでキー入力を取得
                    import select
                    if sys.stdin in select.select([sys.stdin], [], [], 0.1)[0]:
                        key = sys.stdin.read(1)
                        self.handle_key(key)

        except KeyboardInterrupt:
            pass

        self.console.print("\n[yellow]Emulator stopped.[/yellow]")

    def handle_key(self, key: str) -> None:
        """キー入力を処理"""
        if key == 'q':
            self.running = False
        elif key == 's':
            self.emu.step()
        elif key == 'r':
            self.emu.run(max_instructions=100)
        elif key == '1':
            self.emu.press_switch('SW1')
        elif key == '!':
            self.emu.release_switch('SW1')
        elif key == '2':
            self.emu.press_switch('SW2')
        elif key == '@':
            self.emu.release_switch('SW2')
        elif key == 'x':
            self.emu.reset()
            from .__main__ import load_demo_program
            load_demo_program(self.emu)

    def show_static(self) -> None:
        """静的表示（1回だけ表示）"""
        layout = self.create_layout()
        self.update_layout(layout)
        self.console.print(layout)


class SimpleVisualUI:
    """
    シンプルなビジュアルUI（rich不要版）
    """

    def __init__(self, emulator: RX65NEmulator):
        self.emu = emulator
        self.visualizer = BoardVisualizer(emulator)

    def clear_screen(self) -> None:
        """画面クリア"""
        os.system('cls' if os.name == 'nt' else 'clear')

    def draw(self) -> None:
        """画面を描画"""
        self.clear_screen()

        # ヘッダー
        print("=" * 70)
        print("          RX65N Virtual Microcontroller Emulator")
        print("=" * 70)
        print()

        # ボード図
        print(self.visualizer.draw_board_ascii())
        print()

        # CPUステータス
        state = self.emu.get_cpu_state()
        print(f"┌{'─'*30} CPU {'─'*30}┐")
        print(f"│ PC: 0x{state['pc']:08X}    SP: 0x{state['sp']:08X}    PSW: 0x{state['psw']:08X} │")
        flags = state['flags']
        flag_str = ' '.join(f"{k}={int(v)}" for k, v in flags.items())
        print(f"│ Flags: {flag_str:<55}│")
        print(f"│ State: {state['state']:<10} Cycles: {state['cycles']:<10} Instructions: {state['instructions']:<10}│")
        print(f"└{'─'*66}┘")
        print()

        # レジスタ
        print("Registers:")
        regs = state['registers']
        for i in range(0, 16, 4):
            line = "  ".join(f"R{j:2d}=0x{regs[f'R{j}']:08X}" for j in range(i, i+4))
            print(f"  {line}")
        print()

        # UART
        uart_log = self.emu.get_uart_log()
        if uart_log:
            print(f"UART Output: {uart_log[-60:]}")
        print()

        # コマンドヘルプ
        print("Commands: [s]tep [r]un [1/2]press SW [!/\"]release SW [x]reset [q]uit")

    def run_interactive(self) -> None:
        """インタラクティブモードで実行"""
        # デモプログラムをロード
        from .__main__ import load_demo_program
        load_demo_program(self.emu)

        running = True

        while running:
            self.draw()

            try:
                cmd = input("\n> ").strip().lower()

                if cmd == 'q':
                    running = False
                elif cmd == 's':
                    self.emu.step()
                elif cmd == 'r':
                    self.emu.run(max_instructions=100)
                elif cmd == '1':
                    self.emu.press_switch('SW1')
                elif cmd == '!':
                    self.emu.release_switch('SW1')
                elif cmd == '2':
                    self.emu.press_switch('SW2')
                elif cmd == '@' or cmd == '"':
                    self.emu.release_switch('SW2')
                elif cmd == 'x':
                    self.emu.reset()
                    load_demo_program(self.emu)
                elif cmd.startswith('run '):
                    try:
                        n = int(cmd.split()[1])
                        self.emu.run(max_instructions=n)
                    except (ValueError, IndexError):
                        pass

            except (EOFError, KeyboardInterrupt):
                running = False

        print("\nEmulator stopped.")


def run_visual_ui(use_rich: bool = True) -> None:
    """ビジュアルUIを起動"""
    emu = RX65NEmulator()

    if use_rich and RICH_AVAILABLE:
        ui = RichVisualUI(emu)
        ui.run_interactive()
    else:
        ui = SimpleVisualUI(emu)
        ui.run_interactive()


if __name__ == '__main__':
    run_visual_ui()
