import { IPeripheral } from "./IPeripheral";

export class Gpio implements IPeripheral {
    name = "GPIO";
    startAddress: number;
    endAddress: number;

    // Registers (8-bit)
    private pdr = 0x00;  // Direction: 1=output, 0=input
    private podr = 0x00; // Output data
    private pidr = 0x00; // Input data

    constructor(startAddress: number) {
        this.startAddress = startAddress;
        this.endAddress = startAddress + 0x0F;
    }

    reset(): void {
        this.pdr = 0;
        this.podr = 0;
        this.pidr = 0;
    }

    setInputBit(bit: number, value: boolean) {
        if (bit < 0 || bit > 7) return;
        if (value) {
            this.pidr |= 1 << bit;
        } else {
            this.pidr &= ~(1 << bit);
        }
    }

    getOutputBit(bit: number): boolean {
        if (bit < 0 || bit > 7) return false;
        return (this.podr & (1 << bit)) !== 0;
    }

    read8(offset: number): number {
        switch (offset & 0x0F) {
            case 0x00: return this.pdr;
            case 0x04: return this.podr;
            case 0x08: return this.pidr;
            default: return 0;
        }
    }

    read16(offset: number): number {
        return this.read8(offset) | (this.read8(offset + 1) << 8);
    }

    read32(offset: number): number {
        return this.read16(offset) | (this.read16(offset + 2) << 16);
    }

    write8(offset: number, value: number): void {
        const v = value & 0xFF;
        switch (offset & 0x0F) {
            case 0x00:
                this.pdr = v;
                break;
            case 0x04:
                this.podr = v;
                break;
            default:
                break;
        }
    }

    write16(offset: number, value: number): void {
        this.write8(offset, value & 0xFF);
        this.write8(offset + 1, (value >> 8) & 0xFF);
    }

    write32(offset: number, value: number): void {
        this.write16(offset, value & 0xFFFF);
        this.write16(offset + 2, (value >> 16) & 0xFFFF);
    }

    tick(): void { }
}
