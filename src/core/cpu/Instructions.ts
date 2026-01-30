import { ICpu } from "./ICpu";
import { IMemory } from "../memory/IMemory";

// Helper to read sign-extended values or specific patterns could go here.
export const OpOps = {
  // Flag updates
  updateZ: (cpu: ICpu, val: number) => { cpu.psw.Z = (val === 0); },
  updateS: (cpu: ICpu, val: number) => { cpu.psw.S = (val < 0); }, // Simple check for now, requires careful 32bit handling
  // Correct 32-bit Sign Check:
  updateS32: (cpu: ICpu, val: number) => { cpu.psw.S = ((val & 0x80000000) !== 0); }
};

export const Instructions = {
  NOP: (cpu: ICpu, mem: IMemory) => {
    // Do nothing
  },

  MOV_Imm_Reg: (cpu: ICpu, mem: IMemory, rd: number, imm: number) => {
    cpu.r[rd] = imm >>> 0; // Ensure unsigned 32-bit storage
    OpOps.updateZ(cpu, cpu.r[rd]);
    OpOps.updateS32(cpu, cpu.r[rd]);
  },

  MOV_Reg_Reg: (cpu: ICpu, mem: IMemory, rs: number, rd: number) => {
    cpu.r[rd] = cpu.r[rs];
    OpOps.updateZ(cpu, cpu.r[rd]);
    OpOps.updateS32(cpu, cpu.r[rd]);
  },

  ADD_Imm_Reg: (cpu: ICpu, mem: IMemory, rd: number, imm: number) => {
    const a = cpu.r[rd];
    const b = imm;
    const res = (a + b) >>> 0; // 32-bit wrap
    cpu.r[rd] = res;
    
    // Update Flags (Basic Z/S for now, O/C omitted for brevity in this step)
    OpOps.updateZ(cpu, res);
    OpOps.updateS32(cpu, res);
  }
};