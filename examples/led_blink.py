"""
LED点滅サンプルプログラム

RX65N仮想環境でLEDを点滅させるデモ
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rx_emulator import RX65NEmulator


def create_led_blink_program():
    """LED点滅プログラムを生成"""
    # RX アセンブリ:
    # ; 初期化
    # MOV.L #0x0008C02D, R2    ; PORTD PODR アドレス
    # MOV.L #0x0008C00D, R3    ; PORTD PDR アドレス
    # MOV.L #0xC0, R4          ; PD6, PD7を出力
    # MOV.B R4, [R3]           ; PDR設定
    #
    # loop:
    # MOV.L #0x40, R5          ; LED0 ON (PD6=1, Low Active なので実際はOFF)
    # MOV.B R5, [R2]           ; PODR書き込み
    # ; delay
    # MOV.L #0x80, R5          ; LED1 ON
    # MOV.B R5, [R2]           ; PODR書き込み
    # ; delay
    # MOV.L #0x00, R5          ; 両方ON (Low Active)
    # MOV.B R5, [R2]           ; PODR書き込み
    # BRA loop

    program = bytes([
        # 初期化 (0xFFE00000)
        # MOV.L #0x0008C02D, R2 (PORTD PODR)
        0xFB, 0x02, 0x2D, 0xC0, 0x08, 0x00,

        # MOV.L #0x0008C00D, R3 (PORTD PDR)
        0xFB, 0x03, 0x0D, 0xC0, 0x08, 0x00,

        # MOV.L #0xC0, R4 (出力設定)
        0xFB, 0x04, 0xC0, 0x00, 0x00, 0x00,

        # MOV.B R4, [R3] (PDR書き込み)
        0xC0, 0x43,

        # ループ開始 (0xFFE00014)
        # MOV.L #0x40, R5 (LED0 OFF, LED1 ON - Low Active)
        0xFB, 0x05, 0x40, 0x00, 0x00, 0x00,

        # MOV.B R5, [R2]
        0xC0, 0x52,

        # MOV.L #0x80, R5 (LED0 ON, LED1 OFF)
        0xFB, 0x05, 0x80, 0x00, 0x00, 0x00,

        # MOV.B R5, [R2]
        0xC0, 0x52,

        # MOV.L #0x00, R5 (両方ON)
        0xFB, 0x05, 0x00, 0x00, 0x00, 0x00,

        # MOV.B R5, [R2]
        0xC0, 0x52,

        # MOV.L #0xC0, R5 (両方OFF)
        0xFB, 0x05, 0xC0, 0x00, 0x00, 0x00,

        # MOV.B R5, [R2]
        0xC0, 0x52,

        # BRA loop (-38バイト)
        0x38, 0xD8, 0xFF,

        # パディング
        0x03, 0x03,
    ])

    return program


def main():
    print("RX65N LED Blink Demo")
    print("=" * 40)

    # エミュレータ作成
    emu = RX65NEmulator()

    # プログラムロード
    program = create_led_blink_program()
    emu.load_binary_data(program, 0xFFE00000)

    # リセットベクタ設定
    emu.write_memory(0xFFFFFFFC, 0xFFE00000, 4)

    # 初期設定
    emu.cpu.regs.pc = 0xFFE00000
    emu.cpu.regs.sp = 0x0003FFFC

    print(f"Program loaded at 0xFFE00000")
    print(f"Program size: {len(program)} bytes")
    print()

    # LED変更コールバック
    def on_led_change(name, state):
        print(f"  {name}: {state.name}")

    emu.board.register_led_callback(on_led_change)

    # 実行
    print("Running program...")
    print("(LED state changes will be shown)")
    print()

    try:
        for cycle in range(10):
            print(f"--- Cycle {cycle + 1} ---")
            emu.run(max_instructions=50)  # 少しずつ実行
            print(f"Board: {emu.get_led_display()}")
            print()
            time.sleep(0.2)

    except KeyboardInterrupt:
        print("\nInterrupted")

    # 最終状態
    print()
    print("Final State:")
    print(f"  PC: 0x{emu.cpu.regs.pc:08X}")
    print(f"  Instructions executed: {emu.cpu.instruction_count}")
    print(f"  LEDs: {emu.get_led_display()}")


if __name__ == '__main__':
    main()
