import { ICpu, IPsw } from "./ICpu";
import { IMemory } from "../memory/IMemory";
import { MEMORY_MAP } from "../memory/MemoryMap";

import { Decoder } from "./Decoder";

export class CpuCore implements ICpu {
  r: Uint32Array;
  pc: number;
  psw: IPsw;
  usp: number;
  isp: number;
  acc: bigint;
  
  private memory: IMemory;
  private decoder: Decoder;

  constructor(memory: IMemory) {
    this.memory = memory;
    this.decoder = new Decoder();
    this.r = new Uint32Array(16);
    this.pc = 0;
    this.usp = 0;
    this.isp = 0;
    this.acc = 0n;
    this.psw = {
      I: false, U: false, PM: false, IPL: 0,
      O: false, S: false, Z: false, C: false
    };
  }

  reset(): void {
    // 1. Initialize Registers
    this.r.fill(0);
    this.acc = 0n;
    
    // 2. Initialize PSW (Typical reset value)
    this.psw = {
      I: false, // Interrupts disabled
      U: false, // Stack Pointer is ISP
      PM: false,// Supervisor Mode
      IPL: 0,
      O: false, S: false, Z: false, C: false
    };

    // 3. Fetch Initial PC from Reset Vector (0xFFFFFFFC in some RX, or Fixed Vector Table)
    // RX65N Reset Vector is at 0xFFFFFFFC (32-bit)
    // Note: In Hardware Manual, Reset vector is part of Fixed Vector Table at FFFFFFFC.
    this.pc = this.memory.read32(0xFFFFFFFC);
    
    // Also, SP (ISP) is often initialized by software, but some debuggers/sims allow preset.
    // In strict RX hardware, SP is undefined at reset until code sets it.
    // We will initialize it to top of RAM for convenience if it's 0.
    this.isp = MEMORY_MAP.RAM_END;
  }

  step(): number {
    return this.decoder.execute(this, this.memory);
  }

  run(cycles: number): void {
    let cyclesUsed = 0;
    while (cyclesUsed < cycles) {
      cyclesUsed += this.step();
    }
  }
}