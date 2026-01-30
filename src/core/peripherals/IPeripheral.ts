import { IMemory } from "../memory/IMemory";

/**
 * Interface for Memory Mapped Peripherals (GPIO, Timer, etc.)
 */
export interface IPeripheral {
  /**
   * Name of the peripheral for debugging
   */
  name: string;

  /**
   * Address range this peripheral occupies
   */
  startAddress: number;
  endAddress: number;

  /**
   * Initialize or Reset the peripheral state
   */
  reset(): void;

  /**
   * Read from a register within this peripheral
   */
  read8(offset: number): number;
  read16(offset: number): number;
  read32(offset: number): number;

  /**
   * Write to a register within this peripheral
   */
  write8(offset: number, value: number): void;
  write16(offset: number, value: number): void;
  write32(offset: number, value: number): void;

  /**
   * Update internal state (for timers, etc.)
   * @param cycles Number of CPU cycles passed
   */
  tick(cycles: number): void;
}