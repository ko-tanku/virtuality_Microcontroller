"""
ELF/BINローダーモジュール

RX用コンパイラ出力（ELF/BIN）を実行環境へロード

サポートするフォーマット:
- ELF32 (RX)
- Motorola S-Record (MOT/SREC)
- Intel HEX
- Raw Binary
"""

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
from enum import IntEnum

if TYPE_CHECKING:
    from .memory import MemoryController


class ELFClass(IntEnum):
    """ELFクラス"""
    ELFCLASS32 = 1
    ELFCLASS64 = 2


class ELFEndian(IntEnum):
    """ELFエンディアン"""
    LITTLE = 1
    BIG = 2


class ELFMachine(IntEnum):
    """ELFマシンタイプ"""
    RX = 173  # Renesas RX


class SectionType(IntEnum):
    """ELFセクションタイプ"""
    NULL = 0
    PROGBITS = 1
    SYMTAB = 2
    STRTAB = 3
    RELA = 4
    HASH = 5
    DYNAMIC = 6
    NOTE = 7
    NOBITS = 8
    REL = 9


class ProgramType(IntEnum):
    """ELFプログラムヘッダタイプ"""
    NULL = 0
    LOAD = 1
    DYNAMIC = 2
    INTERP = 3
    NOTE = 4


@dataclass
class ELFHeader:
    """ELFヘッダ"""
    magic: bytes = b'\x7fELF'
    elf_class: int = ELFClass.ELFCLASS32
    endian: int = ELFEndian.LITTLE
    version: int = 1
    osabi: int = 0
    machine: int = ELFMachine.RX
    entry_point: int = 0
    phoff: int = 0  # プログラムヘッダオフセット
    shoff: int = 0  # セクションヘッダオフセット
    flags: int = 0
    ehsize: int = 52  # ELFヘッダサイズ
    phentsize: int = 32  # プログラムヘッダエントリサイズ
    phnum: int = 0  # プログラムヘッダ数
    shentsize: int = 40  # セクションヘッダエントリサイズ
    shnum: int = 0  # セクションヘッダ数
    shstrndx: int = 0  # セクション名文字列テーブルインデックス


@dataclass
class ProgramHeader:
    """ELFプログラムヘッダ"""
    p_type: int = 0
    p_offset: int = 0
    p_vaddr: int = 0
    p_paddr: int = 0
    p_filesz: int = 0
    p_memsz: int = 0
    p_flags: int = 0
    p_align: int = 0


@dataclass
class SectionHeader:
    """ELFセクションヘッダ"""
    sh_name: int = 0
    sh_type: int = 0
    sh_flags: int = 0
    sh_addr: int = 0
    sh_offset: int = 0
    sh_size: int = 0
    sh_link: int = 0
    sh_info: int = 0
    sh_addralign: int = 0
    sh_entsize: int = 0
    name: str = ""


@dataclass
class Symbol:
    """ELFシンボル"""
    name: str = ""
    value: int = 0
    size: int = 0
    info: int = 0
    other: int = 0
    shndx: int = 0

    @property
    def bind(self) -> int:
        return self.info >> 4

    @property
    def sym_type(self) -> int:
        return self.info & 0xF


@dataclass
class LoadResult:
    """ロード結果"""
    success: bool = False
    entry_point: int = 0
    loaded_sections: List[dict] = field(default_factory=list)
    symbols: Dict[str, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class ELFLoader:
    """
    ELFローダー

    RX用ELFファイルをパースしてメモリにロード
    """

    def __init__(self):
        self.memory: Optional['MemoryController'] = None
        self.header: Optional[ELFHeader] = None
        self.program_headers: List[ProgramHeader] = []
        self.section_headers: List[SectionHeader] = []
        self.symbols: Dict[str, Symbol] = {}
        self.string_table: bytes = b''

    def connect_memory(self, memory: 'MemoryController') -> None:
        """メモリコントローラを接続"""
        self.memory = memory

    def load_elf(self, filepath: str) -> LoadResult:
        """ELFファイルをロード"""
        result = LoadResult()

        try:
            with open(filepath, 'rb') as f:
                data = f.read()

            # ELFヘッダ解析
            if not self._parse_elf_header(data):
                result.errors.append("Invalid ELF header")
                return result

            # プログラムヘッダ解析
            self._parse_program_headers(data)

            # セクションヘッダ解析
            self._parse_section_headers(data)

            # シンボルテーブル解析
            self._parse_symbols(data)

            # メモリにロード
            if self.memory:
                for ph in self.program_headers:
                    if ph.p_type == ProgramType.LOAD and ph.p_filesz > 0:
                        section_data = data[ph.p_offset:ph.p_offset + ph.p_filesz]
                        self.memory.load_binary(ph.p_paddr, section_data)

                        result.loaded_sections.append({
                            'vaddr': f'0x{ph.p_vaddr:08X}',
                            'paddr': f'0x{ph.p_paddr:08X}',
                            'size': ph.p_filesz,
                        })

                # BSS領域のゼロクリア
                for ph in self.program_headers:
                    if ph.p_type == ProgramType.LOAD and ph.p_memsz > ph.p_filesz:
                        bss_start = ph.p_paddr + ph.p_filesz
                        bss_size = ph.p_memsz - ph.p_filesz
                        for i in range(bss_size):
                            self.memory.write8(bss_start + i, 0)

            result.success = True
            result.entry_point = self.header.entry_point
            result.symbols = {name: sym.value for name, sym in self.symbols.items()}

        except Exception as e:
            result.errors.append(str(e))

        return result

    def _parse_elf_header(self, data: bytes) -> bool:
        """ELFヘッダを解析"""
        if len(data) < 52:
            return False

        # マジックナンバー確認
        if data[:4] != b'\x7fELF':
            return False

        self.header = ELFHeader()
        self.header.elf_class = data[4]
        self.header.endian = data[5]
        self.header.version = data[6]
        self.header.osabi = data[7]

        # リトルエンディアンを仮定
        fmt = '<'

        (
            self.header.machine,
            _,  # e_version
            self.header.entry_point,
            self.header.phoff,
            self.header.shoff,
            self.header.flags,
            self.header.ehsize,
            self.header.phentsize,
            self.header.phnum,
            self.header.shentsize,
            self.header.shnum,
            self.header.shstrndx,
        ) = struct.unpack(f'{fmt}HHIIIIHHHHHHH', data[16:52])

        return True

    def _parse_program_headers(self, data: bytes) -> None:
        """プログラムヘッダを解析"""
        self.program_headers.clear()

        if not self.header or self.header.phnum == 0:
            return

        offset = self.header.phoff
        for _ in range(self.header.phnum):
            if offset + 32 > len(data):
                break

            ph = ProgramHeader()
            (
                ph.p_type,
                ph.p_offset,
                ph.p_vaddr,
                ph.p_paddr,
                ph.p_filesz,
                ph.p_memsz,
                ph.p_flags,
                ph.p_align,
            ) = struct.unpack('<IIIIIIII', data[offset:offset + 32])

            self.program_headers.append(ph)
            offset += self.header.phentsize

    def _parse_section_headers(self, data: bytes) -> None:
        """セクションヘッダを解析"""
        self.section_headers.clear()

        if not self.header or self.header.shnum == 0:
            return

        offset = self.header.shoff
        for _ in range(self.header.shnum):
            if offset + 40 > len(data):
                break

            sh = SectionHeader()
            (
                sh.sh_name,
                sh.sh_type,
                sh.sh_flags,
                sh.sh_addr,
                sh.sh_offset,
                sh.sh_size,
                sh.sh_link,
                sh.sh_info,
                sh.sh_addralign,
                sh.sh_entsize,
            ) = struct.unpack('<IIIIIIIIII', data[offset:offset + 40])

            self.section_headers.append(sh)
            offset += self.header.shentsize

        # セクション名文字列テーブルを取得
        if self.header.shstrndx < len(self.section_headers):
            strtab = self.section_headers[self.header.shstrndx]
            self.string_table = data[strtab.sh_offset:strtab.sh_offset + strtab.sh_size]

            # セクション名を設定
            for sh in self.section_headers:
                sh.name = self._get_string(sh.sh_name)

    def _parse_symbols(self, data: bytes) -> None:
        """シンボルテーブルを解析"""
        self.symbols.clear()

        # .symtab セクションを探す
        symtab_section = None
        strtab_section = None

        for sh in self.section_headers:
            if sh.sh_type == SectionType.SYMTAB:
                symtab_section = sh
            if sh.name == '.strtab':
                strtab_section = sh

        if not symtab_section:
            return

        # シンボル文字列テーブル
        if strtab_section:
            sym_strtab = data[strtab_section.sh_offset:
                            strtab_section.sh_offset + strtab_section.sh_size]
        else:
            sym_strtab = b''

        # シンボル解析
        offset = symtab_section.sh_offset
        entry_size = symtab_section.sh_entsize or 16

        while offset < symtab_section.sh_offset + symtab_section.sh_size:
            if offset + entry_size > len(data):
                break

            sym = Symbol()
            (
                st_name,
                sym.value,
                sym.size,
                sym.info,
                sym.other,
                sym.shndx,
            ) = struct.unpack('<IIIBBH', data[offset:offset + 16])

            # シンボル名取得
            if st_name > 0 and st_name < len(sym_strtab):
                end = sym_strtab.find(b'\x00', st_name)
                if end == -1:
                    end = len(sym_strtab)
                sym.name = sym_strtab[st_name:end].decode('utf-8', errors='ignore')

            if sym.name:
                self.symbols[sym.name] = sym

            offset += entry_size

    def _get_string(self, offset: int) -> str:
        """文字列テーブルから文字列を取得"""
        if offset >= len(self.string_table):
            return ""
        end = self.string_table.find(b'\x00', offset)
        if end == -1:
            end = len(self.string_table)
        return self.string_table[offset:end].decode('utf-8', errors='ignore')

    def get_symbol_address(self, name: str) -> Optional[int]:
        """シンボルアドレスを取得"""
        if name in self.symbols:
            return self.symbols[name].value
        return None

    def get_entry_point(self) -> int:
        """エントリポイントを取得"""
        return self.header.entry_point if self.header else 0


class SRecordLoader:
    """
    S-Recordローダー

    Motorola S-Record (MOT/SREC)ファイルをパース
    """

    def __init__(self):
        self.memory: Optional['MemoryController'] = None
        self.entry_point: int = 0

    def connect_memory(self, memory: 'MemoryController') -> None:
        """メモリコントローラを接続"""
        self.memory = memory

    def load_srec(self, filepath: str) -> LoadResult:
        """S-Recordファイルをロード"""
        result = LoadResult()

        try:
            with open(filepath, 'r') as f:
                lines = f.readlines()

            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line[0] != 'S':
                    continue

                try:
                    self._parse_record(line)
                except ValueError as e:
                    result.errors.append(f"Line {line_num}: {e}")

            result.success = len(result.errors) == 0
            result.entry_point = self.entry_point

        except Exception as e:
            result.errors.append(str(e))

        return result

    def _parse_record(self, record: str) -> None:
        """1レコードを解析"""
        if len(record) < 4:
            raise ValueError("Record too short")

        record_type = record[1]
        byte_count = int(record[2:4], 16)

        # データ部分
        data_hex = record[4:]
        if len(data_hex) < (byte_count * 2):
            raise ValueError("Incomplete record")

        # レコードタイプ別処理
        if record_type == '0':
            # ヘッダレコード
            pass
        elif record_type == '1':
            # データ (16ビットアドレス)
            address = int(data_hex[0:4], 16)
            data = bytes.fromhex(data_hex[4:-2])  # チェックサム除く
            if self.memory:
                self.memory.load_binary(address, data)
        elif record_type == '2':
            # データ (24ビットアドレス)
            address = int(data_hex[0:6], 16)
            data = bytes.fromhex(data_hex[6:-2])
            if self.memory:
                self.memory.load_binary(address, data)
        elif record_type == '3':
            # データ (32ビットアドレス)
            address = int(data_hex[0:8], 16)
            data = bytes.fromhex(data_hex[8:-2])
            if self.memory:
                self.memory.load_binary(address, data)
        elif record_type == '7':
            # エントリポイント (32ビット)
            self.entry_point = int(data_hex[0:8], 16)
        elif record_type == '8':
            # エントリポイント (24ビット)
            self.entry_point = int(data_hex[0:6], 16)
        elif record_type == '9':
            # エントリポイント (16ビット)
            self.entry_point = int(data_hex[0:4], 16)


class IntelHexLoader:
    """
    Intel HEXローダー

    Intel HEXファイルをパース
    """

    def __init__(self):
        self.memory: Optional['MemoryController'] = None
        self.entry_point: int = 0
        self.extended_address: int = 0

    def connect_memory(self, memory: 'MemoryController') -> None:
        """メモリコントローラを接続"""
        self.memory = memory

    def load_hex(self, filepath: str) -> LoadResult:
        """Intel HEXファイルをロード"""
        result = LoadResult()

        try:
            with open(filepath, 'r') as f:
                lines = f.readlines()

            self.extended_address = 0

            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line[0] != ':':
                    continue

                try:
                    self._parse_record(line[1:])
                except ValueError as e:
                    result.errors.append(f"Line {line_num}: {e}")

            result.success = len(result.errors) == 0
            result.entry_point = self.entry_point

        except Exception as e:
            result.errors.append(str(e))

        return result

    def _parse_record(self, record: str) -> None:
        """1レコードを解析"""
        if len(record) < 10:
            raise ValueError("Record too short")

        byte_count = int(record[0:2], 16)
        address = int(record[2:6], 16)
        record_type = int(record[6:8], 16)
        data_hex = record[8:-2]  # チェックサム除く

        if record_type == 0x00:
            # データレコード
            full_address = self.extended_address + address
            data = bytes.fromhex(data_hex)
            if self.memory:
                self.memory.load_binary(full_address, data)

        elif record_type == 0x01:
            # EOFレコード
            pass

        elif record_type == 0x02:
            # 拡張セグメントアドレス
            self.extended_address = int(data_hex, 16) << 4

        elif record_type == 0x03:
            # スタートセグメントアドレス
            pass

        elif record_type == 0x04:
            # 拡張リニアアドレス
            self.extended_address = int(data_hex, 16) << 16

        elif record_type == 0x05:
            # スタートリニアアドレス
            self.entry_point = int(data_hex, 16)


class BinaryLoader:
    """
    バイナリローダー

    Raw バイナリファイルをロード
    """

    def __init__(self):
        self.memory: Optional['MemoryController'] = None

    def connect_memory(self, memory: 'MemoryController') -> None:
        """メモリコントローラを接続"""
        self.memory = memory

    def load_binary(self, filepath: str, load_address: int = 0xFFE00000) -> LoadResult:
        """バイナリファイルをロード"""
        result = LoadResult()

        try:
            with open(filepath, 'rb') as f:
                data = f.read()

            if self.memory:
                self.memory.load_binary(load_address, data)

                result.loaded_sections.append({
                    'address': f'0x{load_address:08X}',
                    'size': len(data),
                })

            result.success = True
            result.entry_point = load_address

        except Exception as e:
            result.errors.append(str(e))

        return result
