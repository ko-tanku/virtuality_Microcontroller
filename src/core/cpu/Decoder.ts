import { ICpu } from "./ICpu";
import { IMemory } from "../memory/IMemory";
import { Instructions } from "./Instructions";

export class Decoder {
  constructor() {}

  /**
   * Decodes instruction at CPU.PC and executes it.
   * Updates CPU.PC appropriately.
   * @returns cycles consumed
   */
  execute(cpu: ICpu, mem: IMemory): number {
    const pc = cpu.pc;
    const op1 = mem.read8(pc);

    // Simple Decoder based on the Assembler's defined Opcodes
    
    // NOP: 0x03
    if (op1 === 0x03) {
      Instructions.NOP(cpu, mem);
      cpu.pc += 1;
      return 1;
    }

    // MOV.L #imm, Rd: FB 12 0d (imm32)
    if (op1 === 0xFB) {
      const op2 = mem.read8(pc + 1);
      if (op2 === 0x12) {
        const op3 = mem.read8(pc + 2);
        const rd = op3 & 0x0F;
        const imm = mem.read32(pc + 3);
        
        Instructions.MOV_Imm_Reg(cpu, mem, rd, imm);
        cpu.pc += 7; // 3 bytes opcode + 4 bytes imm
        return 2;
      }
    }

    // MOV.L Rs, Rd: CF sd
    if (op1 === 0xCF) {
      const op2 = mem.read8(pc + 1);
      const rs = (op2 >> 4) & 0x0F;
      const rd = op2 & 0x0F;
      
      Instructions.MOV_Reg_Reg(cpu, mem, rs, rd);
      cpu.pc += 2;
      return 1;
    }

    // ADD.L #imm, Rd: 72 2d (imm32)
    if (op1 === 0x72) {
      const op2 = mem.read8(pc + 1);
      // Check if it matches 0x2d form
      if ((op2 & 0xF0) === 0x20) {
        const rd = op2 & 0x0F;
        const imm = mem.read32(pc + 2);
        
        Instructions.ADD_Imm_Reg(cpu, mem, rd, imm);
        cpu.pc += 6; // 2 bytes opcode + 4 bytes imm
        return 2;
      }
    }

    // Unknown Opcode
    console.warn(`Unknown Opcode at ${pc.toString(16)}: ${op1.toString(16)}`);
    cpu.pc += 1; // Skip to avoid infinite loop on 00
    return 1;
  }
}