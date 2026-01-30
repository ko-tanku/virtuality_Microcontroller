"""
回路図/ブロック図表示モジュール

マイコンの内部構造とI/O接続を視覚的に表示
- ブロック図（CPU、メモリ、周辺機器）
- 信号フロー表示
- ピン接続図
- 配線アニメーション
"""

from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from enum import Enum

try:
    from rich.console import Console
    from rich.text import Text
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from .emulator import RX65NEmulator
from .board import LEDState, SwitchState


class SignalState(Enum):
    """信号状態"""
    LOW = 0
    HIGH = 1
    HIGH_Z = 2  # ハイインピーダンス
    UNKNOWN = 3


@dataclass
class Signal:
    """信号定義"""
    name: str
    state: SignalState = SignalState.LOW
    source: str = ""
    destination: str = ""


class SchematicRenderer:
    """
    回路図レンダラー

    ASCIIアートで回路図を描画
    """

    def __init__(self, emulator: RX65NEmulator):
        self.emu = emulator

    def render_full_schematic(self) -> str:
        """フルの回路図を描画"""
        # LED/SW状態
        led_states = self._get_led_indicators()
        sw_states = self._get_switch_indicators()

        # 信号状態の色分け用
        cpu_active = "▓" if self.emu.cpu.state.name == "RUNNING" else "░"

        schematic = f"""
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃                         RX65N Microcontroller Block Diagram                  ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

     ┌─────────────────────────────────────────────────────────────────┐
     │                          POWER SUPPLY                           │
     │    VCC ══════════════════════════════════════════════════ GND   │
     └───────────────────────────┬─────────────────────────────────────┘
                                 │
     ┌───────────────────────────┼───────────────────────────────────────────┐
     │                           │         RX65N CHIP                        │
     │   ┌───────────────────────┴───────────────────────────┐               │
     │   │                    CLOCK SYSTEM                    │               │
     │   │  ┌─────────┐    ┌─────────┐    ┌─────────┐        │               │
     │   │  │  LOCO   │    │  HOCO   │    │   PLL   │        │               │
     │   │  │ 240kHz  │    │  16MHz  │    │  x10    │        │               │
     │   │  └────┬────┘    └────┬────┘    └────┬────┘        │               │
     │   │       └───────┬──────┴───────┬──────┘             │               │
     │   │               │    MUX       │                    │               │
     │   │               └──────┬───────┘                    │               │
     │   └──────────────────────┼────────────────────────────┘               │
     │                          │ ICLK (120MHz)                              │
     │   ┌──────────────────────┼────────────────────────────┐               │
     │   │     ┌────────────────┴────────────────┐           │               │
     │   │     │            CPU {cpu_active}                  │           │               │
     │   │     │  ┌──────────────────────────┐   │           │               │
     │   │     │  │  Registers               │   │           │               │
     │   │     │  │  R0-R15, PC, SP, PSW     │   │           │               │
     │   │     │  └──────────────────────────┘   │           │               │
     │   │     │  ┌──────────────────────────┐   │           │               │
     │   │     │  │  ALU + Control Unit      │   │           │               │
     │   │     │  └──────────────────────────┘   │           │               │
     │   │     └────────────────┬────────────────┘           │               │
     │   │                      │                            │               │
     │   │     ═══════════════ BUS ══════════════════        │               │
     │   │     │                │                  │         │               │
     │   │     ▼                ▼                  ▼         │               │
     │   │ ┌────────┐    ┌────────────┐    ┌────────────┐    │               │
     │   │ │ FLASH  │    │    RAM     │    │ Peripheral │    │               │
     │   │ │  2MB   │    │   256KB    │    │  Registers │    │               │
     │   │ └────────┘    └────────────┘    └─────┬──────┘    │               │
     │   │                                       │           │               │
     │   └───────────────────────────────────────┼───────────┘               │
     │                                           │                           │
     │   ┌───────────────────────────────────────┼───────────────────────┐   │
     │   │            PERIPHERAL MODULES         │                       │   │
     │   │   ┌──────────┐  ┌──────────┐  ┌──────┴─────┐  ┌──────────┐   │   │
     │   │   │   GPIO   │  │  TIMER   │  │ INTERRUPT  │  │   UART   │   │   │
     │   │   │ PORT0-E  │  │ CMT0-3   │  │ Controller │  │  SCI0    │   │   │
     │   │   └────┬─────┘  └────┬─────┘  └────────────┘  └────┬─────┘   │   │
     │   │        │             │                              │        │   │
     │   └────────┼─────────────┼──────────────────────────────┼────────┘   │
     │            │             │                              │            │
     └────────────┼─────────────┼──────────────────────────────┼────────────┘
                  │             │                              │
     ┌────────────┼─────────────┼──────────────────────────────┼────────────┐
     │            │             │      EXTERNAL I/O            │            │
     │            ▼             │                              ▼            │
     │     ┌────────────────────┴───────────────┐      ┌────────────┐       │
     │     │           LED OUTPUTS              │      │    UART    │       │
     │     │  LED0   LED1   LED2   LED3         │      │  TX    RX  │       │
     │     │   {led_states[0]}     {led_states[1]}     {led_states[2]}     {led_states[3]}          │      │   ▼     ▲  │       │
     │     └────────────────────────────────────┘      └────────────┘       │
     │                                                                      │
     │     ┌────────────────────────────────────┐                           │
     │     │         SWITCH INPUTS              │                           │
     │     │     SW1           SW2              │                           │
     │     │     {sw_states[0]}            {sw_states[1]}              │                           │
     │     └────────────────────────────────────┘                           │
     │                                                                      │
     └──────────────────────────────────────────────────────────────────────┘
"""
        return schematic

    def render_gpio_detail(self) -> str:
        """GPIO詳細回路図"""
        portd_pdr = self.emu.gpio.ports[0x0D].pdr
        portd_podr = self.emu.gpio.ports[0x0D].podr

        # ビットごとの状態
        bits_dir = [(portd_pdr >> i) & 1 for i in range(8)]
        bits_out = [(portd_podr >> i) & 1 for i in range(8)]

        # 方向表示（→出力、←入力）
        dir_arrows = ['→' if d else '←' for d in bits_dir]
        out_vals = ['H' if o else 'L' for o in bits_out]

        gpio_schematic = f"""
┌─────────────────────────────────────────────────────────────────────────────┐
│                            GPIO PORT D Detail                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Internal Bus                                                               │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     PORT D Control Register                         │   │
│  │  PDR  = 0x{portd_pdr:02X}  (Direction: 0=In, 1=Out)                          │   │
│  │  PODR = 0x{portd_podr:02X}  (Output Data)                                     │   │
│  └──┬──┬──┬──┬──┬──┬──┬──┬─────────────────────────────────────────────┘   │
│     │  │  │  │  │  │  │  │                                                  │
│    D7 D6 D5 D4 D3 D2 D1 D0   (Pin Numbers)                                 │
│     │  │  │  │  │  │  │  │                                                  │
│     {dir_arrows[7]}  {dir_arrows[6]}  {dir_arrows[5]}  {dir_arrows[4]}  {dir_arrows[3]}  {dir_arrows[2]}  {dir_arrows[1]}  {dir_arrows[0]}   (Direction)                                     │
│     │  │  │  │  │  │  │  │                                                  │
│     {out_vals[7]}  {out_vals[6]}  {out_vals[5]}  {out_vals[4]}  {out_vals[3]}  {out_vals[2]}  {out_vals[1]}  {out_vals[0]}   (Output Value)                                   │
│     │  │  │  │  │  │  │  │                                                  │
│     ▼  ▼  │  │  │  │  │  │                                                  │
│  ┌──┴──┴──┘  │  │  │  │  │                                                  │
│  │  LEDs     │  │  │  │  │                                                  │
│  │  D7=LED1  │  │  │  │  │                                                  │
│  │  D6=LED0  │  │  │  │  │                                                  │
│  └───────────┘  │  │  │  │                                                  │
│                 │  │  │  │                                                  │
│              (未使用ピン)                                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
"""
        return gpio_schematic

    def render_timer_detail(self) -> str:
        """タイマ詳細回路図"""
        timer_state = self.emu.get_timer_state()
        cmt0 = timer_state.get('CMT0', {})

        cmcnt = cmt0.get('cmcnt', 0)
        cmcor = cmt0.get('cmcor', 0xFFFF)
        running = '▓' if cmt0.get('running', False) else '░'

        timer_schematic = f"""
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TIMER (CMT0) Detail                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   PCLKB (Peripheral Clock)                                                  │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────┐                                                        │
│  │   Clock Divider │  ÷8 / ÷32 / ÷128 / ÷512                               │
│  └────────┬────────┘                                                        │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────┐                        │
│  │              16-bit Counter (CMCNT)             │                        │
│  │  ┌─────────────────────────────────────────┐   │                        │
│  │  │  Current: {cmcnt:5d}                        │   │  {running}              │
│  │  │  ████████████░░░░░░░░░░░░░░░░░░░░░░░░░  │   │  Running             │
│  │  │  0                              {cmcor:5d}  │   │                        │
│  │  └─────────────────────────────────────────┘   │                        │
│  └─────────────────────┬───────────────────────────┘                        │
│                        │                                                    │
│                        ▼                                                    │
│  ┌─────────────────────────────────────────────────┐                        │
│  │              Compare Match Register (CMCOR)     │                        │
│  │              Value: {cmcor:5d}                        │                        │
│  └─────────────────────┬───────────────────────────┘                        │
│                        │                                                    │
│                        ▼                                                    │
│  ┌───────────────┐    ┌────────────────────┐                               │
│  │   CMCNT ==    │───►│   Compare Match    │                               │
│  │   CMCOR ?     │    │   Interrupt (CMI)  │──────► To Interrupt Controller │
│  └───────────────┘    └────────────────────┘                               │
│                                                                             │
│   When CMCNT reaches CMCOR:                                                 │
│     1. CMCNT resets to 0                                                    │
│     2. Compare Match Interrupt generated                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
"""
        return timer_schematic

    def render_interrupt_flow(self) -> str:
        """割り込みフロー図"""
        int_state = self.emu.get_interrupt_state()
        pending_count = len(int_state['pending'])
        nest_level = int_state['nest_level']

        psw_i = '1' if self.emu.cpu.regs.get_flag(0x00010000) else '0'  # I flag
        ipl = self.emu.cpu.regs.ipl

        interrupt_schematic = f"""
┌─────────────────────────────────────────────────────────────────────────────┐
│                        INTERRUPT FLOW DIAGRAM                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────────────────────────────────────────────────────────────┐     │
│   │  Interrupt Sources                                                │     │
│   │   ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐    │     │
│   │   │ Timer  │  │  GPIO  │  │  UART  │  │  SPI   │  │  etc.  │    │     │
│   │   │ CMT0-3 │  │  IRQ   │  │  SCI   │  │  RSPI  │  │        │    │     │
│   │   └───┬────┘  └───┬────┘  └───┬────┘  └───┬────┘  └───┬────┘    │     │
│   │       │           │           │           │           │         │     │
│   └───────┼───────────┼───────────┼───────────┼───────────┼─────────┘     │
│           │           │           │           │                           │
│           └───────────┴─────┬─────┴───────────┘                           │
│                             │                                              │
│                             ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────┐     │
│   │              Interrupt Controller (ICU)                          │     │
│   │  ┌─────────────────────────────────────────────────────────┐    │     │
│   │  │  IR (Interrupt Request)      Pending: {pending_count:2d}                 │    │     │
│   │  │  IER (Interrupt Enable)                                  │    │     │
│   │  │  IPR (Interrupt Priority)    0-15 levels                │    │     │
│   │  └─────────────────────────────────────────────────────────┘    │     │
│   │                             │                                    │     │
│   │                             ▼                                    │     │
│   │  ┌─────────────────────────────────────────────────────────┐    │     │
│   │  │  Priority Comparator                                     │    │     │
│   │  │  Request IPL > Current IPL ?                             │    │     │
│   │  │  Current IPL: {ipl:2d}                                        │    │     │
│   │  └─────────────────────────────────────────────────────────┘    │     │
│   └─────────────────────────────┬───────────────────────────────────┘     │
│                                 │                                          │
│                                 ▼                                          │
│   ┌─────────────────────────────────────────────────────────────────┐     │
│   │                         CPU                                      │     │
│   │  ┌─────────────────────────────────────────────────────────┐    │     │
│   │  │  PSW.I (Global Interrupt Enable): {psw_i}                     │    │     │
│   │  │  PSW.IPL (Current Priority Level): {ipl:2d}                   │    │     │
│   │  │  Nest Level: {nest_level:2d}                                       │    │     │
│   │  └─────────────────────────────────────────────────────────┘    │     │
│   │                                                                  │     │
│   │  When interrupt accepted:                                        │     │
│   │    1. Push PC and PSW to stack                                   │     │
│   │    2. Update IPL                                                 │     │
│   │    3. Jump to vector table address                               │     │
│   │    4. Execute ISR (Interrupt Service Routine)                    │     │
│   │    5. RTE: Pop PSW and PC from stack                             │     │
│   └─────────────────────────────────────────────────────────────────┘     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
"""
        return interrupt_schematic

    def render_memory_map(self) -> str:
        """メモリマップ図"""
        pc = self.emu.cpu.regs.pc
        sp = self.emu.cpu.regs.sp

        memory_map = f"""
┌─────────────────────────────────────────────────────────────────────────────┐
│                          RX65N MEMORY MAP                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  0xFFFFFFFF ┌─────────────────────────────────────────┐ ◄── Reset Vector   │
│             │        Fixed Vector Table (128B)        │                     │
│  0xFFFFFF80 ├─────────────────────────────────────────┤                     │
│             │                                         │                     │
│             │                                         │                     │
│             │         Internal Flash ROM              │                     │
│             │              (2MB)                      │                     │
│             │                                         │  ◄── PC: 0x{pc:08X} │
│  0xFFE00000 ├─────────────────────────────────────────┤                     │
│             │                                         │                     │
│             │           (Reserved)                    │                     │
│             │                                         │                     │
│  0x00100000 ├─────────────────────────────────────────┤                     │
│             │    Peripheral Registers (512KB)         │                     │
│             │    - GPIO:   0x0008C000                 │                     │
│             │    - Timer:  0x00088000                 │                     │
│             │    - SCI:    0x0008A000                 │                     │
│             │    - ICU:    0x00087000                 │                     │
│  0x00080000 ├─────────────────────────────────────────┤                     │
│             │                                         │                     │
│             │           (Reserved)                    │                     │
│             │                                         │                     │
│  0x00040000 ├─────────────────────────────────────────┤                     │
│             │                                         │  ◄── SP: 0x{sp:08X} │
│             │         Internal RAM (256KB)            │                     │
│             │                                         │                     │
│             │    Stack grows downward ↓               │                     │
│             │                                         │                     │
│  0x00000000 └─────────────────────────────────────────┘                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
"""
        return memory_map

    def _get_led_indicators(self) -> List[str]:
        """LED状態のインジケータを取得"""
        indicators = []
        for i in range(4):
            state = self.emu.board.get_led_state(f'LED{i}')
            if state == LEDState.ON:
                indicators.append('●')
            else:
                indicators.append('○')
        return indicators

    def _get_switch_indicators(self) -> List[str]:
        """スイッチ状態のインジケータを取得"""
        indicators = []
        for name in ['SW1', 'SW2']:
            state = self.emu.board.get_switch_state(name)
            if state == SwitchState.PRESSED:
                indicators.append('■')
            else:
                indicators.append('□')
        return indicators


def print_schematic_demo(emulator: RX65NEmulator) -> None:
    """回路図デモを表示"""
    renderer = SchematicRenderer(emulator)

    print("\n" + "=" * 80)
    print("RX65N Schematic Views")
    print("=" * 80)

    print("\n[1] Full Block Diagram:")
    print(renderer.render_full_schematic())

    input("\nPress Enter to see GPIO detail...")
    print(renderer.render_gpio_detail())

    input("\nPress Enter to see Timer detail...")
    print(renderer.render_timer_detail())

    input("\nPress Enter to see Interrupt flow...")
    print(renderer.render_interrupt_flow())

    input("\nPress Enter to see Memory map...")
    print(renderer.render_memory_map())
