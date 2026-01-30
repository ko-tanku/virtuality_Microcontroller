"""
RX CPUコアモジュール

RX CPUの命令実行・レジスタ管理・PC制御を行う中核モジュール

レジスタ構成:
- 汎用レジスタ: R0〜R15 (32ビット)
- PC: プログラムカウンタ
- SP: スタックポインタ (R0のエイリアス)
- PSW: プロセッサステータスワード
"""

from dataclasses import dataclass, field
from enum import IntEnum, IntFlag
from typing import Optional, Callable, Dict, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .memory import MemoryController
    from .interrupt import InterruptController


class PSWFlags(IntFlag):
    """PSW (Processor Status Word) フラグ定義"""
    C = 0x00000001   # キャリーフラグ
    Z = 0x00000002   # ゼロフラグ
    S = 0x00000004   # サインフラグ (負数)
    O = 0x00000008   # オーバーフローフラグ
    I = 0x00010000   # 割り込み許可
    U = 0x00020000   # ユーザーモード
    PM = 0x00100000  # プロセッサモード

    # IPL (Interrupt Priority Level) はビット24-27
    IPL_MASK = 0x0F000000


class CPUState(IntEnum):
    """CPU状態"""
    STOPPED = 0
    RUNNING = 1
    HALTED = 2
    WAITING = 3
    EXCEPTION = 4


@dataclass
class CPURegisters:
    """CPUレジスタセット"""
    # 汎用レジスタ R0-R15 (R0=SP)
    r: List[int] = field(default_factory=lambda: [0] * 16)

    # プログラムカウンタ
    pc: int = 0

    # プロセッサステータスワード
    psw: int = PSWFlags.I  # 初期状態: 割り込み許可

    # 割り込みスタックポインタ (ISP)
    isp: int = 0

    # ユーザースタックポインタ (USP)
    usp: int = 0

    # 浮動小数点ステータスワード
    fpsw: int = 0

    # アキュムレータ (64ビット)
    acc: int = 0

    @property
    def sp(self) -> int:
        """スタックポインタ (R0のエイリアス)"""
        return self.r[0]

    @sp.setter
    def sp(self, value: int) -> None:
        self.r[0] = value & 0xFFFFFFFF

    @property
    def ipl(self) -> int:
        """割り込み優先レベル"""
        return (self.psw >> 24) & 0x0F

    @ipl.setter
    def ipl(self, value: int) -> None:
        self.psw = (self.psw & ~PSWFlags.IPL_MASK) | ((value & 0x0F) << 24)

    def get_flag(self, flag: PSWFlags) -> bool:
        """PSWフラグを取得"""
        return bool(self.psw & flag)

    def set_flag(self, flag: PSWFlags, value: bool) -> None:
        """PSWフラグを設定"""
        if value:
            self.psw |= flag
        else:
            self.psw &= ~flag

    def update_flags_arithmetic(self, result: int, op1: int, op2: int,
                                  is_subtraction: bool = False, bits: int = 32) -> None:
        """算術演算後のフラグ更新"""
        mask = (1 << bits) - 1
        sign_bit = 1 << (bits - 1)

        # ゼロフラグ
        self.set_flag(PSWFlags.Z, (result & mask) == 0)

        # サインフラグ
        self.set_flag(PSWFlags.S, bool(result & sign_bit))

        # キャリーフラグ (符号なしオーバーフロー)
        if is_subtraction:
            self.set_flag(PSWFlags.C, op1 < op2)
        else:
            self.set_flag(PSWFlags.C, result > mask)

        # オーバーフローフラグ (符号付きオーバーフロー)
        op1_sign = bool(op1 & sign_bit)
        op2_sign = bool(op2 & sign_bit)
        result_sign = bool(result & sign_bit)

        if is_subtraction:
            overflow = (op1_sign != op2_sign) and (result_sign != op1_sign)
        else:
            overflow = (op1_sign == op2_sign) and (result_sign != op1_sign)
        self.set_flag(PSWFlags.O, overflow)

    def update_flags_logical(self, result: int, bits: int = 32) -> None:
        """論理演算後のフラグ更新"""
        mask = (1 << bits) - 1
        sign_bit = 1 << (bits - 1)

        self.set_flag(PSWFlags.Z, (result & mask) == 0)
        self.set_flag(PSWFlags.S, bool(result & sign_bit))


class RXCpu:
    """
    RX CPUエミュレータコア

    命令フェッチ・デコード・実行サイクルを実装
    """

    def __init__(self):
        self.regs = CPURegisters()
        self.state = CPUState.STOPPED
        self.memory: Optional['MemoryController'] = None
        self.interrupt_controller: Optional['InterruptController'] = None

        # 実行統計
        self.cycle_count: int = 0
        self.instruction_count: int = 0

        # 命令テーブル
        self._instruction_table: Dict[int, Callable] = {}
        self._build_instruction_table()

        # ブレークポイント
        self.breakpoints: set = set()

        # トレース用コールバック
        self.trace_callback: Optional[Callable] = None

    def connect_memory(self, memory: 'MemoryController') -> None:
        """メモリコントローラを接続"""
        self.memory = memory

    def connect_interrupt_controller(self, ic: 'InterruptController') -> None:
        """割り込みコントローラを接続"""
        self.interrupt_controller = ic

    def reset(self) -> None:
        """CPUリセット"""
        self.regs = CPURegisters()
        self.state = CPUState.STOPPED
        self.cycle_count = 0
        self.instruction_count = 0

        if self.memory:
            # リセットベクタからPC初期値を読み込む
            # RX65Nのリセットベクタは 0xFFFFFFFC
            reset_vector = self.memory.read32(0xFFFFFFFC)
            self.regs.pc = reset_vector

            # スタックポインタ初期値
            # 通常はリンカスクリプトで設定されるRAM末尾
            self.regs.sp = 0x00020000  # デフォルト値

        self.regs.psw = PSWFlags.I  # 割り込み許可
        self.state = CPUState.STOPPED

    def start(self) -> None:
        """CPU実行開始"""
        self.state = CPUState.RUNNING

    def stop(self) -> None:
        """CPU実行停止"""
        self.state = CPUState.STOPPED

    def step(self) -> bool:
        """1命令実行"""
        if not self.memory:
            raise RuntimeError("Memory not connected")

        # ブレークポイントチェック
        if self.regs.pc in self.breakpoints:
            self.state = CPUState.STOPPED
            return False

        # 割り込みチェック
        if self.interrupt_controller and self.regs.get_flag(PSWFlags.I):
            pending = self.interrupt_controller.get_pending_interrupt()
            if pending is not None and pending > self.regs.ipl:
                self._handle_interrupt(pending)

        # 命令フェッチ
        opcode = self._fetch()

        # デコードと実行
        self._execute(opcode)

        self.instruction_count += 1

        return self.state == CPUState.RUNNING

    def run(self, max_cycles: int = 0) -> int:
        """連続実行"""
        self.state = CPUState.RUNNING
        executed = 0

        while self.state == CPUState.RUNNING:
            if max_cycles > 0 and executed >= max_cycles:
                break

            self.step()
            executed += 1

        return executed

    def _fetch(self) -> int:
        """命令フェッチ (1バイト)"""
        opcode = self.memory.read8(self.regs.pc)
        self.regs.pc = (self.regs.pc + 1) & 0xFFFFFFFF
        self.cycle_count += 1
        return opcode

    def _fetch16(self) -> int:
        """2バイトフェッチ"""
        value = self.memory.read16(self.regs.pc)
        self.regs.pc = (self.regs.pc + 2) & 0xFFFFFFFF
        self.cycle_count += 2
        return value

    def _fetch32(self) -> int:
        """4バイトフェッチ"""
        value = self.memory.read32(self.regs.pc)
        self.regs.pc = (self.regs.pc + 4) & 0xFFFFFFFF
        self.cycle_count += 4
        return value

    def _execute(self, opcode: int) -> None:
        """命令実行"""
        if self.trace_callback:
            self.trace_callback(self.regs.pc - 1, opcode, self.regs)

        # 命令テーブルから実行
        handler = self._instruction_table.get(opcode)
        if handler:
            handler()
        else:
            # 未実装命令
            self._undefined_instruction(opcode)

    def _build_instruction_table(self) -> None:
        """命令テーブル構築"""
        # NOP
        self._instruction_table[0x03] = self._op_nop

        # MOV.L #imm32, Rd (FBh)
        self._instruction_table[0xFB] = self._op_mov_imm32

        # MOV.L Rs, Rd (EFh)
        self._instruction_table[0xEF] = self._op_mov_reg

        # ADD #imm, Rd (62h)
        self._instruction_table[0x62] = self._op_add_imm4

        # ADD Rs, Rd (48h-4Bh)
        for i in range(0x48, 0x4C):
            self._instruction_table[i] = self._op_add_reg

        # SUB Rs, Rd (44h-47h)
        for i in range(0x44, 0x48):
            self._instruction_table[i] = self._op_sub_reg

        # CMP #imm, Rd (61h)
        self._instruction_table[0x61] = self._op_cmp_imm4

        # AND Rs, Rd (50h-53h)
        for i in range(0x50, 0x54):
            self._instruction_table[i] = self._op_and_reg

        # OR Rs, Rd (54h-57h)
        for i in range(0x54, 0x58):
            self._instruction_table[i] = self._op_or_reg

        # XOR Rs, Rd (58h-5Bh)
        for i in range(0x58, 0x5C):
            self._instruction_table[i] = self._op_xor_reg

        # PUSH.L Rs (7Eh)
        self._instruction_table[0x7E] = self._op_push

        # POP Rd (7Fh)
        self._instruction_table[0x7F] = self._op_pop

        # BSR.W disp16 (39h)
        self._instruction_table[0x39] = self._op_bsr_w

        # BRA.W disp16 (38h)
        self._instruction_table[0x38] = self._op_bra_w

        # BEQ/BZ disp8 (20h)
        self._instruction_table[0x20] = self._op_beq

        # BNE/BNZ disp8 (21h)
        self._instruction_table[0x21] = self._op_bne

        # RTS (02h)
        self._instruction_table[0x02] = self._op_rts

        # RTE (7Fh 95h) - 2バイト命令として別途処理

        # JSR Rs (7Fh)
        # self._instruction_table[0x7F] = self._op_jsr  # POPと競合、2バイト目で判定

        # JMP Rs (7Fh)
        # 2バイト命令は別途処理

        # WAIT (7Fh 96h)

        # MOV.B Rs, [Rd] (C0h-C3h)
        for i in range(0xC0, 0xC4):
            self._instruction_table[i] = self._op_mov_b_store

        # MOV.B [Rs], Rd (CCh-CFh)
        for i in range(0xCC, 0xD0):
            self._instruction_table[i] = self._op_mov_b_load

        # MOV.L Rs, [Rd] (E0h-E3h)
        for i in range(0xE0, 0xE4):
            self._instruction_table[i] = self._op_mov_l_store

        # MOV.L [Rs], Rd (ECh-EFh)
        for i in range(0xEC, 0xF0):
            self._instruction_table[i] = self._op_mov_l_load

        # 拡張命令プレフィックス (FDh)
        self._instruction_table[0xFD] = self._op_fd_prefix

        # 拡張命令プレフィックス (FCh)
        self._instruction_table[0xFC] = self._op_fc_prefix

        # 拡張命令プレフィックス (76h)
        self._instruction_table[0x76] = self._op_76_prefix

    # === 命令実装 ===

    def _op_nop(self) -> None:
        """NOP - 何もしない"""
        pass

    def _op_mov_imm32(self) -> None:
        """MOV.L #imm32, Rd"""
        second = self._fetch()
        rd = second & 0x0F
        imm32 = self._fetch32()
        self.regs.r[rd] = imm32

    def _op_mov_reg(self) -> None:
        """MOV.L Rs, Rd"""
        second = self._fetch()
        rs = (second >> 4) & 0x0F
        rd = second & 0x0F
        self.regs.r[rd] = self.regs.r[rs]

    def _op_add_imm4(self) -> None:
        """ADD #imm4, Rd"""
        second = self._fetch()
        imm4 = (second >> 4) & 0x0F
        rd = second & 0x0F

        # 符号拡張
        if imm4 & 0x08:
            imm4 |= 0xFFFFFFF0

        op1 = self.regs.r[rd]
        result = (op1 + imm4) & 0xFFFFFFFF

        self.regs.update_flags_arithmetic(result, op1, imm4 & 0xFFFFFFFF)
        self.regs.r[rd] = result

    def _op_add_reg(self) -> None:
        """ADD Rs, Rd"""
        second = self._fetch()
        rs = (second >> 4) & 0x0F
        rd = second & 0x0F

        op1 = self.regs.r[rd]
        op2 = self.regs.r[rs]
        result = (op1 + op2) & 0xFFFFFFFF

        self.regs.update_flags_arithmetic(result, op1, op2)
        self.regs.r[rd] = result

    def _op_sub_reg(self) -> None:
        """SUB Rs, Rd"""
        second = self._fetch()
        rs = (second >> 4) & 0x0F
        rd = second & 0x0F

        op1 = self.regs.r[rd]
        op2 = self.regs.r[rs]
        result = (op1 - op2) & 0xFFFFFFFF

        self.regs.update_flags_arithmetic(result, op1, op2, is_subtraction=True)
        self.regs.r[rd] = result

    def _op_cmp_imm4(self) -> None:
        """CMP #imm4, Rd"""
        second = self._fetch()
        imm4 = (second >> 4) & 0x0F
        rd = second & 0x0F

        # 符号拡張
        if imm4 & 0x08:
            imm4 |= 0xFFFFFFF0

        op1 = self.regs.r[rd]
        result = (op1 - (imm4 & 0xFFFFFFFF)) & 0xFFFFFFFF

        self.regs.update_flags_arithmetic(result, op1, imm4 & 0xFFFFFFFF, is_subtraction=True)
        # 結果は破棄（フラグのみ更新）

    def _op_and_reg(self) -> None:
        """AND Rs, Rd"""
        second = self._fetch()
        rs = (second >> 4) & 0x0F
        rd = second & 0x0F

        result = self.regs.r[rd] & self.regs.r[rs]
        self.regs.update_flags_logical(result)
        self.regs.r[rd] = result

    def _op_or_reg(self) -> None:
        """OR Rs, Rd"""
        second = self._fetch()
        rs = (second >> 4) & 0x0F
        rd = second & 0x0F

        result = self.regs.r[rd] | self.regs.r[rs]
        self.regs.update_flags_logical(result)
        self.regs.r[rd] = result

    def _op_xor_reg(self) -> None:
        """XOR Rs, Rd"""
        second = self._fetch()
        rs = (second >> 4) & 0x0F
        rd = second & 0x0F

        result = self.regs.r[rd] ^ self.regs.r[rs]
        self.regs.update_flags_logical(result)
        self.regs.r[rd] = result

    def _op_push(self) -> None:
        """PUSH.L Rs"""
        second = self._fetch()
        rs = second & 0x0F

        self.regs.sp = (self.regs.sp - 4) & 0xFFFFFFFF
        self.memory.write32(self.regs.sp, self.regs.r[rs])

    def _op_pop(self) -> None:
        """POP Rd"""
        second = self._fetch()
        rd = second & 0x0F

        self.regs.r[rd] = self.memory.read32(self.regs.sp)
        self.regs.sp = (self.regs.sp + 4) & 0xFFFFFFFF

    def _op_bsr_w(self) -> None:
        """BSR.W disp16 - サブルーチン呼び出し"""
        disp16 = self._fetch16()

        # 符号拡張
        if disp16 & 0x8000:
            disp16 |= 0xFFFF0000

        # リターンアドレスをプッシュ
        self.regs.sp = (self.regs.sp - 4) & 0xFFFFFFFF
        self.memory.write32(self.regs.sp, self.regs.pc)

        # 分岐
        self.regs.pc = (self.regs.pc + disp16) & 0xFFFFFFFF

    def _op_bra_w(self) -> None:
        """BRA.W disp16 - 無条件分岐"""
        disp16 = self._fetch16()

        # 符号拡張
        if disp16 & 0x8000:
            disp16 |= 0xFFFF0000

        self.regs.pc = (self.regs.pc + disp16) & 0xFFFFFFFF

    def _op_beq(self) -> None:
        """BEQ/BZ disp8 - ゼロなら分岐"""
        disp8 = self._fetch()

        if self.regs.get_flag(PSWFlags.Z):
            # 符号拡張
            if disp8 & 0x80:
                disp8 |= 0xFFFFFF00
            self.regs.pc = (self.regs.pc + disp8) & 0xFFFFFFFF

    def _op_bne(self) -> None:
        """BNE/BNZ disp8 - ゼロでないなら分岐"""
        disp8 = self._fetch()

        if not self.regs.get_flag(PSWFlags.Z):
            # 符号拡張
            if disp8 & 0x80:
                disp8 |= 0xFFFFFF00
            self.regs.pc = (self.regs.pc + disp8) & 0xFFFFFFFF

    def _op_rts(self) -> None:
        """RTS - サブルーチンから復帰"""
        self.regs.pc = self.memory.read32(self.regs.sp)
        self.regs.sp = (self.regs.sp + 4) & 0xFFFFFFFF

    def _op_mov_b_store(self) -> None:
        """MOV.B Rs, [Rd]"""
        second = self._fetch()
        rs = (second >> 4) & 0x0F
        rd = second & 0x0F

        self.memory.write8(self.regs.r[rd], self.regs.r[rs] & 0xFF)

    def _op_mov_b_load(self) -> None:
        """MOV.B [Rs], Rd"""
        second = self._fetch()
        rs = (second >> 4) & 0x0F
        rd = second & 0x0F

        self.regs.r[rd] = self.memory.read8(self.regs.r[rs])

    def _op_mov_l_store(self) -> None:
        """MOV.L Rs, [Rd]"""
        second = self._fetch()
        rs = (second >> 4) & 0x0F
        rd = second & 0x0F

        self.memory.write32(self.regs.r[rd], self.regs.r[rs])

    def _op_mov_l_load(self) -> None:
        """MOV.L [Rs], Rd"""
        second = self._fetch()
        rs = (second >> 4) & 0x0F
        rd = second & 0x0F

        self.regs.r[rd] = self.memory.read32(self.regs.r[rs])

    def _op_fd_prefix(self) -> None:
        """FDh プレフィックス拡張命令"""
        second = self._fetch()

        if second == 0x72:  # SETPSW
            third = self._fetch()
            flag_bit = third & 0x0F
            if flag_bit == 0:
                self.regs.set_flag(PSWFlags.C, True)
            elif flag_bit == 1:
                self.regs.set_flag(PSWFlags.Z, True)
            elif flag_bit == 2:
                self.regs.set_flag(PSWFlags.S, True)
            elif flag_bit == 3:
                self.regs.set_flag(PSWFlags.O, True)
            elif flag_bit == 8:
                self.regs.set_flag(PSWFlags.I, True)

        elif second == 0x73:  # CLRPSW
            third = self._fetch()
            flag_bit = third & 0x0F
            if flag_bit == 0:
                self.regs.set_flag(PSWFlags.C, False)
            elif flag_bit == 1:
                self.regs.set_flag(PSWFlags.Z, False)
            elif flag_bit == 2:
                self.regs.set_flag(PSWFlags.S, False)
            elif flag_bit == 3:
                self.regs.set_flag(PSWFlags.O, False)
            elif flag_bit == 8:
                self.regs.set_flag(PSWFlags.I, False)

        else:
            self._undefined_instruction(0xFD00 | second)

    def _op_fc_prefix(self) -> None:
        """FCh プレフィックス拡張命令"""
        second = self._fetch()
        # MOV.L [Rs,Rd], Rd' など
        self._undefined_instruction(0xFC00 | second)

    def _op_76_prefix(self) -> None:
        """76h プレフィックス拡張命令"""
        second = self._fetch()

        if second == 0x90:  # WAIT
            self.state = CPUState.WAITING
        else:
            self._undefined_instruction(0x7600 | second)

    def _undefined_instruction(self, opcode: int) -> None:
        """未定義命令例外"""
        self.state = CPUState.EXCEPTION
        raise RuntimeError(f"Undefined instruction: 0x{opcode:04X} at PC=0x{self.regs.pc:08X}")

    def _handle_interrupt(self, vector: int) -> None:
        """割り込み処理"""
        # PSWをスタックに退避
        self.regs.sp = (self.regs.sp - 4) & 0xFFFFFFFF
        self.memory.write32(self.regs.sp, self.regs.psw)

        # PCをスタックに退避
        self.regs.sp = (self.regs.sp - 4) & 0xFFFFFFFF
        self.memory.write32(self.regs.sp, self.regs.pc)

        # 割り込み禁止
        self.regs.set_flag(PSWFlags.I, False)

        # IPL更新
        self.regs.ipl = vector

        # ベクタテーブルからハンドラアドレス取得
        vector_addr = 0xFFFFFF80 + (vector * 4)
        handler = self.memory.read32(vector_addr)
        self.regs.pc = handler

        # 割り込みコントローラに通知
        if self.interrupt_controller:
            self.interrupt_controller.acknowledge(vector)

    def execute_rte(self) -> None:
        """RTE - 割り込みから復帰"""
        # PCを復元
        self.regs.pc = self.memory.read32(self.regs.sp)
        self.regs.sp = (self.regs.sp + 4) & 0xFFFFFFFF

        # PSWを復元
        self.regs.psw = self.memory.read32(self.regs.sp)
        self.regs.sp = (self.regs.sp + 4) & 0xFFFFFFFF

    def get_state(self) -> dict:
        """CPU状態を辞書形式で取得"""
        return {
            'state': self.state.name,
            'pc': self.regs.pc,
            'sp': self.regs.sp,
            'psw': self.regs.psw,
            'flags': {
                'C': self.regs.get_flag(PSWFlags.C),
                'Z': self.regs.get_flag(PSWFlags.Z),
                'S': self.regs.get_flag(PSWFlags.S),
                'O': self.regs.get_flag(PSWFlags.O),
                'I': self.regs.get_flag(PSWFlags.I),
            },
            'ipl': self.regs.ipl,
            'registers': {f'R{i}': self.regs.r[i] for i in range(16)},
            'cycles': self.cycle_count,
            'instructions': self.instruction_count,
        }
