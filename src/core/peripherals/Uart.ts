import { IPeripheral } from "./IPeripheral";

export class Uart implements IPeripheral {
    name = "UART";
    startAddress: number;
    endAddress: number;

    private txBuffer: string[] = [];

    constructor(startAddress: number) {
        this.startAddress = startAddress;
        this.endAddress = startAddress + 0x0F;
    }

    reset(): void {
        this.txBuffer = [];
    }

    getLog(): string {
        return this.txBuffer.join("");
    }

    clearLog() {
        this.txBuffer = [];
    }

    read8(): number {
        return 0;
    }

    read16(offset: number): number {
        return this.read8(offset) | (this.read8(offset + 1) << 8);
    }

    read32(offset: number): number {
        return this.read16(offset) | (this.read16(offset + 2) << 16);
    }

    write8(offset: number, value: number): void {
        const v = value & 0xFF;
        // offset 0x00: TDR (Transmit Data Register)
        if ((offset & 0x0F) === 0x00) {
            this.txBuffer.push(String.fromCharCode(v));
        }
    }

    write16(offset: number, value: number): void {
        this.write8(offset, value & 0xFF);
    }

    write32(offset: number, value: number): void {
        this.write8(offset, value & 0xFF);
    }

    tick(): void { }
}
