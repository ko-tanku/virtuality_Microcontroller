export class Clock {
  private frequencyHz: number;
  private slowMode: boolean;

  constructor(frequencyHz = 1_000_000, slowMode = false) {
    this.frequencyHz = frequencyHz;
    this.slowMode = slowMode;
  }

  setFrequencyHz(freq: number) {
    this.frequencyHz = Math.max(1, Math.floor(freq));
  }

  setSlowMode(enabled: boolean) {
    this.slowMode = enabled;
  }

  getFrequencyHz(): number {
    return this.frequencyHz;
  }

  isSlowMode(): boolean {
    return this.slowMode;
  }

  getStepsPerTick(tickMs: number): number {
    const hz = this.slowMode ? Math.max(1, Math.floor(this.frequencyHz / 100)) : this.frequencyHz;
    return Math.max(1, Math.floor((hz * tickMs) / 1000));
  }
}
