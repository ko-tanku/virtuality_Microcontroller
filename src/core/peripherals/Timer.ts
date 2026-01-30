import { IPeripheral } from "./IPeripheral";
import { InterruptController } from "../interrupts/InterruptController";

export class Timer implements IPeripheral {
    name = "Timer";
    startAddress: number;
    endAddress: number;

    private tcnt = 0;
    private tcor = 1000;
    private tcr = 0;  // bit0: enable
    private tier = 0; // bit0: interrupt enable

    private icu: InterruptController;
    private vector: number;

    constructor(startAddress: number, icu: InterruptController, vector = 64) {
        this.startAddress = startAddress;
        this.endAddress = startAddress + 0x0F;
        this.icu = icu;
        this.vector = vector;
    }

    reset(): void {
        this.tcnt = 0;
        this.tcor = 1000;
        this.tcr = 0;
        this.tier = 0;
    }

    tick(cycles: number): void {
        if ((this.tcr & 0x01) === 0) return;
        this.tcnt = (this.tcnt + cycles) >>> 0;
        if (this.tcnt >= this.tcor) {
            this.tcnt = 0;
            if ((this.tier & 0x01) !== 0) {
                this.icu.requestInterrupt(this.vector, 3, this.name);
            }
        }
    }

    read8(offset: number): number {
        switch (offset & 0x0F) {
            case 0x00: return this.tcnt & 0xFF;
            case 0x01: return (this.tcnt >> 8) & 0xFF;
            case 0x02: return (this.tcnt >> 16) & 0xFF;
            case 0x03: return (this.tcnt >> 24) & 0xFF;
            case 0x04: return this.tcor & 0xFF;
            case 0x05: return (this.tcor >> 8) & 0xFF;
            case 0x06: return (this.tcor >> 16) & 0xFF;
            case 0x07: return (this.tcor >> 24) & 0xFF;
            case 0x08: return this.tcr & 0xFF;
            case 0x0C: return this.tier & 0xFF;
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
            case 0x01:
            case 0x02:
            case 0x03: {
                const shift = (offset & 0x03) * 8;
                this.tcnt = (this.tcnt & ~(0xFF << shift)) | (v << shift);
                break;
            }
            case 0x04:
            case 0x05:
            case 0x06:
            case 0x07: {
                const shift = (offset & 0x03) * 8;
                this.tcor = (this.tcor & ~(0xFF << shift)) | (v << shift);
                break;
            }
            case 0x08:
                this.tcr = v;
                break;
            case 0x0C:
                this.tier = v;
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
}
