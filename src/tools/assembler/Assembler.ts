/**
 * Simple Assembler for RX65N Subset
 * Converts text assembly to machine code.
 */

interface InstructionDef {
  mnemonic: string;
  operands: ('imm' | 'reg')[];
  handler: (args: string[]) => number[];
}

export interface AssemblyResult {
  code: Uint8Array;
  errors: string[];
}

export class Assembler {
  private instructions: InstructionDef[] = [];

  constructor() {
    this.registerInstructions();
  }

  private registerInstructions() {
    // NOP (0x03)
    this.instructions.push({
      mnemonic: 'NOP',
      operands: [],
      handler: () => [0x03]
    });

    // MOV.L #imm, Rd
    // RX Encoding (Simplified for 32-bit imm): FB 12 0d (imm32)
    // d = destination register (0-15)
    this.instructions.push({
      mnemonic: 'MOV.L',
      operands: ['imm', 'reg'],
      handler: (args) => {
        const imm = this.parseImmediate(args[0]);
        const rd = this.parseRegister(args[1]);
        if (rd === null) throw new Error("Invalid register");
        
        // Opcode: FB 12 0d [imm32]
        return [
          0xFB, 
          0x12, 
          0x00 | (rd & 0x0F), 
          imm & 0xFF, 
          (imm >> 8) & 0xFF, 
          (imm >> 16) & 0xFF, 
          (imm >> 24) & 0xFF
        ];
      }
    });

    // MOV.L Rs, Rd
    // RX Encoding: CF sd
    // s = src, d = dest
    this.instructions.push({
      mnemonic: 'MOV.L',
      operands: ['reg', 'reg'],
      handler: (args) => {
        const rs = this.parseRegister(args[0]);
        const rd = this.parseRegister(args[1]);
        if (rs === null || rd === null) throw new Error("Invalid register");

        // Opcode: CF sd
        return [0xCF, ((rs & 0x0F) << 4) | (rd & 0x0F)];
      }
    });

    // ADD.L #imm, Rd
    // RX Encoding (Simplified for 32-bit imm): 72 2d (imm32)
    this.instructions.push({
      mnemonic: 'ADD.L',
      operands: ['imm', 'reg'],
      handler: (args) => {
        const imm = this.parseImmediate(args[0]);
        const rd = this.parseRegister(args[1]);
        if (rd === null) throw new Error("Invalid register");
        
        // Opcode: 72 2d [imm32]
        return [
          0x72, 
          0x20 | (rd & 0x0F), 
          imm & 0xFF, 
          (imm >> 8) & 0xFF, 
          (imm >> 16) & 0xFF, 
          (imm >> 24) & 0xFF
        ];
      }
    });
  }

  public assemble(source: string): AssemblyResult {
    const lines = source.split('\n');
    const machineCode: number[] = [];
    const errors: string[] = [];

    lines.forEach((line, index) => {
      const cleanLine = line.trim().toUpperCase();
      if (!cleanLine || cleanLine.startsWith(';') || cleanLine.startsWith('//')) return;

      // Split mnemonic and operands
      // Example: MOV.L #100, R1 -> ["MOV.L", "#100, R1"]
      const firstSpace = cleanLine.indexOf(' ');
      let mnemonic = "";
      let argsStr = "";

      if (firstSpace === -1) {
        mnemonic = cleanLine;
      } else {
        mnemonic = cleanLine.substring(0, firstSpace).trim();
        argsStr = cleanLine.substring(firstSpace).trim();
      }

      // Parse args
      const args = argsStr ? argsStr.split(',').map(a => a.trim()) : [];

      try {
        const bytes = this.matchAndGenerate(mnemonic, args);
        machineCode.push(...bytes);
      } catch (e: any) {
        errors.push(`Line ${index + 1}: ${e.message}`);
      }
    });

    return {
      code: new Uint8Array(machineCode),
      errors
    };
  }

  private matchAndGenerate(mnemonic: string, args: string[]): number[] {
    const argTypes = args.map(a => {
      if (a.startsWith('#')) return 'imm';
      if (a.startsWith('R') || a === 'SP' || a === 'PC') return 'reg'; // Basic check
      return 'unknown';
    });

    for (const inst of this.instructions) {
      if (inst.mnemonic === mnemonic && 
          inst.operands.length === args.length &&
          inst.operands.every((t, i) => t === argTypes[i])) {
        return inst.handler(args);
      }
    }
    
    throw new Error(`Unknown instruction or invalid operands: ${mnemonic} ${args.join(', ')}`);
  }

  private parseRegister(reg: string): number | null {
    if (reg === 'SP') return 0; // R0 is usually SP
    if (reg.startsWith('R')) {
      const num = parseInt(reg.substring(1));
      if (!isNaN(num) && num >= 0 && num <= 15) return num;
    }
    return null;
  }

  private parseImmediate(imm: string): number {
    let valStr = imm.substring(1); // Remove #
    if (valStr.startsWith('0X')) {
      return parseInt(valStr, 16);
    }
    return parseInt(valStr, 10);
  }
}
