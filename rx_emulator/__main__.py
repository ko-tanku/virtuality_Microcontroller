"""
RX65N Emulator CLI Entry Point

Usage:
    python -m rx_emulator [options] [program]

Options:
    -d, --debug     Start in debug mode
    -r, --run       Run program immediately
    -h, --help      Show help
"""

import argparse
import sys
from pathlib import Path

from .emulator import RX65NEmulator
from .debugger import CLIDebugger


def main():
    parser = argparse.ArgumentParser(
        description='RX65N Microcontroller Virtual Emulator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m rx_emulator program.elf           # Load and debug
    python -m rx_emulator -r program.bin        # Load and run
    python -m rx_emulator -d                    # Start empty debugger
    python -m rx_emulator --demo                # Run demo program
"""
    )

    parser.add_argument('program', nargs='?', help='Program file to load (ELF, MOT, HEX, BIN)')
    parser.add_argument('-d', '--debug', action='store_true', help='Start in debug mode')
    parser.add_argument('-r', '--run', action='store_true', help='Run program immediately')
    parser.add_argument('-a', '--address', type=lambda x: int(x, 0), default=None,
                        help='Load address for binary files (hex, e.g., 0xFFE00000)')
    parser.add_argument('--demo', action='store_true', help='Run demo program')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    # エミュレータ作成
    emu = RX65NEmulator()

    print("RX65N Virtual Emulator v0.1.0")
    print("=" * 40)

    # デモモード
    if args.demo:
        print("Loading demo program...")
        load_demo_program(emu)
        print("Demo program loaded")

    # プログラムロード
    elif args.program:
        filepath = Path(args.program)
        if not filepath.exists():
            print(f"Error: File not found: {args.program}")
            sys.exit(1)

        print(f"Loading: {args.program}")
        result = emu.load_program(str(filepath), args.address)

        if result.success:
            print(f"Entry point: 0x{result.entry_point:08X}")
            if result.loaded_sections:
                for section in result.loaded_sections:
                    print(f"  Section: {section}")
            if args.verbose and result.symbols:
                print(f"Loaded {len(result.symbols)} symbols")
        else:
            print(f"Load failed: {result.errors}")
            sys.exit(1)

    # 実行モード
    if args.run:
        print("\nRunning program...")
        executed = emu.run(max_instructions=1000000)
        print(f"Executed {executed} instructions")
        print(f"Final PC: 0x{emu.cpu.regs.pc:08X}")
        print(f"\nBoard state:")
        print(f"  LEDs: {emu.get_led_display()}")
        print(f"  UART: {emu.get_uart_log()}")

    # デバッグモード
    else:
        print("\nStarting debugger...")
        print("Type 'help' for commands")
        debugger = CLIDebugger(emu)
        debugger.run_cli()

    print("\nEmulator terminated.")


def load_demo_program(emu: RX65NEmulator) -> None:
    """デモプログラムをロード"""
    # 簡単なLED点滅プログラム
    # R1にカウンタ、R2にLEDポートアドレス、R3にLED値

    program = bytes([
        # === エントリポイント (0xFFE00000) ===
        # MOV.L #0, R1 (カウンタ初期化)
        0xFB, 0x01, 0x00, 0x00, 0x00, 0x00,

        # MOV.L #0x0008C02D, R2 (PORTD PODR アドレス)
        0xFB, 0x02, 0x2D, 0xC0, 0x08, 0x00,

        # MOV.L #0x0008C00D, R3 (PORTD PDR アドレス)
        0xFB, 0x03, 0x0D, 0xC0, 0x08, 0x00,

        # MOV.L #0xC0, R4 (PD6, PD7を出力に設定)
        0xFB, 0x04, 0xC0, 0x00, 0x00, 0x00,

        # MOV.B R4, [R3] (PDR設定)
        0xC0, 0x43,

        # === メインループ (0xFFE00018) ===
        # MOV.L #0x40, R5 (LED0 ON)
        0xFB, 0x05, 0x40, 0x00, 0x00, 0x00,

        # MOV.B R5, [R2] (PODR書き込み)
        0xC0, 0x52,

        # ADD #1, R1 (カウンタ++)
        0x62, 0x11,

        # MOV.L #0x80, R5 (LED1 ON)
        0xFB, 0x05, 0x80, 0x00, 0x00, 0x00,

        # MOV.B R5, [R2] (PODR書き込み)
        0xC0, 0x52,

        # ADD #1, R1 (カウンタ++)
        0x62, 0x11,

        # BRA.W -24 (ループ)
        0x38, 0xE8, 0xFF,

        # NOP padding
        0x03, 0x03, 0x03,
    ])

    # Flashにプログラムをロード
    emu.load_binary_data(program, 0xFFE00000)

    # リセットベクタを設定
    emu.write_memory(0xFFFFFFFC, 0xFFE00000, 4)

    # スタックポインタ初期値
    emu.cpu.regs.sp = 0x0003FFFC

    # PC設定
    emu.cpu.regs.pc = 0xFFE00000


if __name__ == '__main__':
    main()
