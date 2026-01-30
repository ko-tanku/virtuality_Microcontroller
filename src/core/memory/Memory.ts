import { IMemory } from "./IMemory";
import { MEMORY_MAP } from "./MemoryMap";

export class Memory implements IMemory {
  private ram: Uint8Array;
  private rom: Uint8Array;
  // In a full implementation, we might handle Data Flash and Peripherals here or via a bus controller.
  // For simplicity, we'll store basic RAM and ROM buffers.

  constructor() {
    // Allocate RAM (256KB)
    const ramSize = MEMORY_MAP.RAM_END - MEMORY_MAP.RAM_START + 1;
    this.ram = new Uint8Array(ramSize);

    // Allocate ROM (2MB)
    const romSize = MEMORY_MAP.ROM_END - MEMORY_MAP.ROM_START + 1;
    this.rom = new Uint8Array(romSize);
    
    // Fill ROM with NOPs or specific pattern if needed
    this.rom.fill(0x03); // 0x03 is NOP in RX
  }

  reset(): void {
    this.ram.fill(0);
    // ROM is typically persistent, but for sim we might want to reload?
    // Keeping ROM as is for now.
  }

  load(data: Uint8Array, offset: number): void {
    // Determine if target is RAM or ROM based on offset
    if (offset >= MEMORY_MAP.RAM_START && offset <= MEMORY_MAP.RAM_END) {
      const localOffset = offset - MEMORY_MAP.RAM_START;
      // Copy data avoiding bounds check errors for simplicity
      for (let i = 0; i < data.length; i++) {
        if (localOffset + i < this.ram.length) {
          this.ram[localOffset + i] = data[i];
        }
      }
    } else if (offset >= MEMORY_MAP.ROM_START && offset <= MEMORY_MAP.ROM_END) {
      const localOffset = offset - MEMORY_MAP.ROM_START;
      for (let i = 0; i < data.length; i++) {
        if (localOffset + i < this.rom.length) {
          this.rom[localOffset + i] = data[i];
        }
      }
    } else {
      console.warn(`Load address 0x${offset.toString(16)} out of supported range.`);
    }
  }

  // Helper to map global address to local buffer
  private getTarget(addr: number): { buffer: Uint8Array; offset: number } | null {
    if (addr >= MEMORY_MAP.RAM_START && addr <= MEMORY_MAP.RAM_END) {
      return { buffer: this.ram, offset: addr - MEMORY_MAP.RAM_START };
    } else if (addr >= MEMORY_MAP.ROM_START && addr <= MEMORY_MAP.ROM_END) {
      return { buffer: this.rom, offset: addr - MEMORY_MAP.ROM_START };
    }
    // TODO: Handle I/O, DataFlash
    return null;
  }

  read8(addr: number): number {
    const target = this.getTarget(addr);
    if (target) {
      return target.buffer[target.offset];
    }
    return 0; // Return 0 for unmapped
  }

  read16(addr: number): number {
    // Little Endian
    const b0 = this.read8(addr);
    const b1 = this.read8(addr + 1);
    return b0 | (b1 << 8);
  }

  read32(addr: number): number {
    // Little Endian
    const b0 = this.read8(addr);
    const b1 = this.read8(addr + 1);
    const b2 = this.read8(addr + 2);
    const b3 = this.read8(addr + 3);
    return (b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)) >>> 0; // unsigned
  }

  write8(addr: number, value: number): void {
    const target = this.getTarget(addr);
    if (target) {
      // ROM is read-only in execution, but writable during load. 
      // For simulation, we might allow writing if it's Flash programming sim, but generally block it.
      // Allowing write for now to support 'load' like behavior if manual poke.
      // Ideally, separate isRom check.
      target.buffer[target.offset] = value & 0xFF;
    }
  }

  write16(addr: number, value: number): void {
    this.write8(addr, value & 0xFF);
    this.write8(addr + 1, (value >> 8) & 0xFF);
  }

  write32(addr: number, value: number): void {
    this.write8(addr, value & 0xFF);
    this.write8(addr + 1, (value >> 8) & 0xFF);
    this.write8(addr + 2, (value >> 16) & 0xFF);
    this.write8(addr + 3, (value >> 24) & 0xFF);
  }
}