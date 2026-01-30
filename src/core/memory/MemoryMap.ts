// RX65N Memory Map Definitions
// Based on RX65N Group User's Manual: Hardware

export const MEMORY_MAP = {
  // RAM (256KB for RX65N 2MB model, assuming typical configuration)
  RAM_START: 0x00000000,
  RAM_END:   0x0003FFFF,

  // Peripheral I/O Registers 1
  PERIPHERAL_IO_1_START: 0x00080000,
  PERIPHERAL_IO_1_END:   0x0009FFFF,

  // Peripheral I/O Registers 2
  PERIPHERAL_IO_2_START: 0x000A0000,
  PERIPHERAL_IO_2_END:   0x000FFFFF,

  // Peripheral Blocks (Simplified)
  GPIO0_START: 0x00080000,
  TIMER0_START: 0x00081000,
  UART0_START: 0x00082000,

  // Data Flash (32KB)
  DATA_FLASH_START: 0x00100000,
  DATA_FLASH_END:   0x00107FFF,

  // ROM (Program Flash) - 2MB
  // Top of ROM is typically 0xFFFFFFFF
  ROM_START: 0xFFE00000,
  ROM_END:   0xFFFFFFFF,

  // Vector Table
  FIXED_VECTOR_TABLE_START: 0xFFFFFFD0,
  FIXED_VECTOR_TABLE_END:   0xFFFFFFFF,
} as const;

export type MemoryMapKey = keyof typeof MEMORY_MAP;