import { IMemory } from "../memory/IMemory";
import { MEMORY_MAP } from "../memory/MemoryMap";

export type InterruptRequest = {
  vector: number;
  priority: number;
  source: string;
};

export class InterruptController {
  private pending: InterruptRequest[] = [];

  requestInterrupt(vector: number, priority: number, source: string) {
    this.pending.push({ vector, priority, source });
    // Higher priority first
    this.pending.sort((a, b) => b.priority - a.priority);
  }

  hasPending(): boolean {
    return this.pending.length > 0;
  }

  popNext(): InterruptRequest | undefined {
    return this.pending.shift();
  }

  getVectorAddress(vector: number): number {
    return MEMORY_MAP.FIXED_VECTOR_TABLE_START + vector * 4;
  }

  resolveVector(mem: IMemory, vector: number): number {
    const addr = this.getVectorAddress(vector);
    return mem.read32(addr);
  }
}
