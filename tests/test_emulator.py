"""
RX65N Emulator Tests

エミュレータの基本動作テスト
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rx_emulator import RX65NEmulator
from rx_emulator.cpu import CPUState, PSWFlags


def test_cpu_registers():
    """CPUレジスタのテスト"""
    print("Testing CPU registers...")

    emu = RX65NEmulator()

    # レジスタ設定
    for i in range(16):
        emu.set_register(f'R{i}', i * 0x1000)

    # レジスタ読み取り
    for i in range(16):
        value = emu.get_register(f'R{i}')
        assert value == i * 0x1000, f"R{i} mismatch: expected {i * 0x1000:#x}, got {value:#x}"

    # PC設定
    emu.set_register('PC', 0xFFE00000)
    assert emu.get_register('PC') == 0xFFE00000

    # SP設定
    emu.set_register('SP', 0x0003FFFC)
    assert emu.get_register('SP') == 0x0003FFFC

    print("  CPU registers: OK")


def test_memory_operations():
    """メモリ操作のテスト"""
    print("Testing memory operations...")

    emu = RX65NEmulator()

    # 8ビット書き込み/読み込み
    emu.write_memory(0x00001000, 0x55, 1)
    assert emu.read_memory(0x00001000, 1) == 0x55

    # 16ビット書き込み/読み込み
    emu.write_memory(0x00001002, 0x1234, 2)
    assert emu.read_memory(0x00001002, 2) == 0x1234

    # 32ビット書き込み/読み込み
    emu.write_memory(0x00001004, 0xDEADBEEF, 4)
    assert emu.read_memory(0x00001004, 4) == 0xDEADBEEF

    print("  Memory operations: OK")


def test_nop_instruction():
    """NOP命令のテスト"""
    print("Testing NOP instruction...")

    emu = RX65NEmulator()

    # NOPプログラム
    program = bytes([0x03, 0x03, 0x03])  # NOP NOP NOP
    emu.load_binary_data(program, 0xFFE00000)
    emu.cpu.regs.pc = 0xFFE00000

    # 実行
    pc_before = emu.cpu.regs.pc
    emu.step()
    pc_after = emu.cpu.regs.pc

    assert pc_after == pc_before + 1, f"PC not incremented: {pc_before:#x} -> {pc_after:#x}"

    print("  NOP instruction: OK")


def test_mov_instruction():
    """MOV命令のテスト"""
    print("Testing MOV instruction...")

    emu = RX65NEmulator()

    # MOV.L #0x12345678, R1
    program = bytes([0xFB, 0x01, 0x78, 0x56, 0x34, 0x12])
    emu.load_binary_data(program, 0xFFE00000)
    emu.cpu.regs.pc = 0xFFE00000

    emu.step()

    r1 = emu.get_register('R1')
    assert r1 == 0x12345678, f"R1 mismatch: expected 0x12345678, got {r1:#x}"

    print("  MOV instruction: OK")


def test_add_instruction():
    """ADD命令のテスト"""
    print("Testing ADD instruction...")

    emu = RX65NEmulator()

    # R1 = 0x100
    emu.set_register('R1', 0x100)
    # R2 = 0x50
    emu.set_register('R2', 0x50)

    # ADD R2, R1 (R1 = R1 + R2)
    program = bytes([0x48, 0x21])  # ADD R2, R1
    emu.load_binary_data(program, 0xFFE00000)
    emu.cpu.regs.pc = 0xFFE00000

    emu.step()

    r1 = emu.get_register('R1')
    assert r1 == 0x150, f"R1 mismatch: expected 0x150, got {r1:#x}"

    print("  ADD instruction: OK")


def test_branch_instruction():
    """分岐命令のテスト"""
    print("Testing branch instruction...")

    emu = RX65NEmulator()

    # BRA.W +4 (2バイト先へジャンプ)
    program = bytes([0x38, 0x02, 0x00])  # BRA.W +2
    emu.load_binary_data(program, 0xFFE00000)
    emu.cpu.regs.pc = 0xFFE00000

    emu.step()

    pc = emu.get_register('PC')
    expected = 0xFFE00005  # 0xFFE00000 + 3 (命令長) + 2 (オフセット)
    assert pc == expected, f"PC mismatch: expected {expected:#x}, got {pc:#x}"

    print("  Branch instruction: OK")


def test_push_pop_instruction():
    """PUSH/POP命令のテスト"""
    print("Testing PUSH/POP instruction...")

    emu = RX65NEmulator()

    # スタックポインタ設定
    emu.set_register('SP', 0x0003FFFC)
    # R1に値を設定
    emu.set_register('R1', 0xDEADBEEF)

    # PUSH.L R1
    program = bytes([0x7E, 0x01])
    emu.load_binary_data(program, 0xFFE00000)
    emu.cpu.regs.pc = 0xFFE00000

    sp_before = emu.get_register('SP')
    emu.step()
    sp_after = emu.get_register('SP')

    assert sp_after == sp_before - 4, f"SP not decremented: {sp_before:#x} -> {sp_after:#x}"

    # スタック上の値を確認
    stacked = emu.read_memory(sp_after, 4)
    assert stacked == 0xDEADBEEF, f"Stacked value mismatch: {stacked:#x}"

    # R2を0にしてPOPでR1の値を復元
    emu.set_register('R2', 0)

    # POP R2
    program2 = bytes([0x7F, 0x02])
    emu.load_binary_data(program2, 0xFFE00010)
    emu.cpu.regs.pc = 0xFFE00010

    emu.step()

    r2 = emu.get_register('R2')
    assert r2 == 0xDEADBEEF, f"R2 mismatch: expected 0xDEADBEEF, got {r2:#x}"

    print("  PUSH/POP instruction: OK")


def test_gpio():
    """GPIOのテスト"""
    print("Testing GPIO...")

    emu = RX65NEmulator()

    # PDR設定 (PORT0を出力に)
    emu.write_memory(0x0008C000, 0xFF, 1)  # PDR0 = 0xFF (全ビット出力)

    # PODR設定
    emu.write_memory(0x0008C020, 0x55, 1)  # PODR0 = 0x55

    # 読み取り確認
    pdr = emu.read_memory(0x0008C000, 1)
    podr = emu.read_memory(0x0008C020, 1)

    assert pdr == 0xFF, f"PDR mismatch: {pdr:#x}"
    assert podr == 0x55, f"PODR mismatch: {podr:#x}"

    print("  GPIO: OK")


def test_timer():
    """タイマのテスト"""
    print("Testing timer...")

    emu = RX65NEmulator()

    # CMT0設定
    # CMCOR0 = 1000
    emu.timer.cmt_units[0].channels[0].cmcor = 1000
    # 割り込み許可
    emu.timer.cmt_units[0].channels[0].interrupt_enabled = True
    # タイマ開始
    emu.timer.cmt_units[0].start_channel(0)

    # ティック
    for _ in range(100):
        emu.timer.tick(100)

    # カウンタ値確認
    cnt = emu.timer.cmt_units[0].channels[0].cmcnt
    assert cnt > 0, f"Timer not counting: {cnt}"

    print("  Timer: OK")


def test_board():
    """ボードのテスト"""
    print("Testing virtual board...")

    emu = RX65NEmulator()

    # スイッチ操作
    emu.press_switch('SW1')
    state = emu.board.get_switch_state('SW1')
    assert state is not None and state.name == 'PRESSED', f"SW1 not pressed: {state}"

    emu.release_switch('SW1')
    state = emu.board.get_switch_state('SW1')
    assert state is not None and state.name == 'RELEASED', f"SW1 not released: {state}"

    print("  Virtual board: OK")


def test_breakpoint():
    """ブレークポイントのテスト"""
    print("Testing breakpoint...")

    emu = RX65NEmulator()

    # プログラム: NOP NOP NOP
    program = bytes([0x03, 0x03, 0x03])
    emu.load_binary_data(program, 0xFFE00000)
    emu.cpu.regs.pc = 0xFFE00000

    # ブレークポイント設定
    emu.add_breakpoint(0xFFE00001)

    # 実行
    emu.step()  # 0xFFE00000 実行
    emu.step()  # 0xFFE00001 でブレーク

    pc = emu.get_register('PC')
    assert pc == 0xFFE00001, f"Did not stop at breakpoint: {pc:#x}"

    print("  Breakpoint: OK")


def run_all_tests():
    """全テスト実行"""
    print("=" * 50)
    print("RX65N Emulator Test Suite")
    print("=" * 50)
    print()

    tests = [
        test_cpu_registers,
        test_memory_operations,
        test_nop_instruction,
        test_mov_instruction,
        test_add_instruction,
        test_branch_instruction,
        test_push_pop_instruction,
        test_gpio,
        test_timer,
        test_board,
        test_breakpoint,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1

    print()
    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
