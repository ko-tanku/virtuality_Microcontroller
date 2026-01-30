export interface IMemory {
  /**
   * Reads an 8-bit byte from the specified address.
   */
  read8(addr: number): number;

  /**
   * Reads a 16-bit word from the specified address (Little Endian).
   */
  read16(addr: number): number;

  /**
   * Reads a 32-bit long word from the specified address (Little Endian).
   */
  read32(addr: number): number;

  /**
   * Writes an 8-bit byte to the specified address.
   */
  write8(addr: number, value: number): void;

  /**
   * Writes a 16-bit word to the specified address (Little Endian).
   */
  write16(addr: number, value: number): void;

  /**
   * Writes a 32-bit long word to the specified address (Little Endian).
   */
  write32(addr: number, value: number): void;

  /**
   * Resets the memory state (clears RAM, reloads ROM if necessary).
   */
  reset(): void;

  /**
   * Load binary data into memory at specific offset.
   */
  load(data: Uint8Array, offset: number): void;
}