/**
 * Represents the Processor Status Word (PSW) flags
 */
export interface IPsw {
  I: boolean; // Interrupt Enable
  U: boolean; // Stack Pointer Select (0=ISP, 1=USP)
  PM: boolean; // Processor Mode (0=Supervisor, 1=User)
  IPL: number; // Interrupt Priority Level (4 bits)
  O: boolean; // Overflow
  S: boolean; // Sign
  Z: boolean; // Zero
  C: boolean; // Carry
}

/**
 * Interface for the RX CPU Core
 */
export interface ICpu {
  // Registers
  r: Uint32Array; // General Purpose Registers R0-R15
  pc: number;     // Program Counter
  psw: IPsw;      // Processor Status Word
  usp: number;    // User Stack Pointer
  isp: number;    // Interrupt Stack Pointer
  
  // Accumulator (64-bit)
  acc: bigint;

  /**
   * Reset the CPU to initial state.
   * Fetches initial PC from reset vector.
   */
  reset(): void;

  /**
   * Execute a single instruction cycle (Fetch -> Decode -> Execute).
   * @returns cycles consumed
   */
  step(): number;

  /**
   * Run for a specific number of cycles.
   */
  run(cycles: number): void;
}