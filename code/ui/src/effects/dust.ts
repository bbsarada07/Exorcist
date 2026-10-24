// One-shot "disintegrate into particles" burst for DELETE_RECORD, drawn on a single overlay canvas.
// Runs on the shared ticker only while particles are alive; does nothing in Lite mode (caller skips it).
import { subscribe } from "./ticker";

interface Mote { x: number; y: number; vx: number; vy: number; life: number; c: string }

export class DustLayer {
  private ctx: CanvasRenderingContext2D;
  private motes: Mote[] = [];
  private unsub: (() => void) | null = null;
  private dpr = Math.min(window.devicePixelRatio || 1, 1.5);

  constructor(private canvas: HTMLCanvasElement, private cap = 1400) {
    this.ctx = canvas.getContext("2d")!;
    this.resize();
  }

  resize() {
    const r = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.round(r.width * this.dpr);
    this.canvas.height = Math.round(r.height * this.dpr);
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
  }

  /** Burst motes out of a rectangle given in canvas-local CSS pixels. */
  burst(rect: { x: number; y: number; w: number; h: number }, color = "#FF6B47", amount = 420) {
    const n = Math.min(amount, this.cap - this.motes.length);
    for (let i = 0; i < n; i++) {
      this.motes.push({ x: rect.x + Math.random() * rect.w, y: rect.y + Math.random() * rect.h,
                        vx: (Math.random() - 0.3) * 2.4, vy: -Math.random() * 2.2 - 0.3, life: 1,
                        c: Math.random() < 0.6 ? color : "#EDE9E0" });
    }
    if (!this.unsub) this.unsub = subscribe((dt) => this.frame(dt));
  }

  private frame(dt: number) {
    const k = dt / 16.67;
    const { ctx } = this;
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    for (const m of this.motes) {
      m.vx *= 0.985; m.vy = m.vy * 0.985 - 0.02 * k;
      m.x += m.vx * k * 1.6; m.y += m.vy * k * 1.6;
      m.life -= 0.011 * k;
      ctx.globalAlpha = Math.max(0, m.life);
      ctx.fillStyle = m.c;
      ctx.fillRect(m.x, m.y, 1.6, 1.6);
    }
    ctx.globalAlpha = 1;
    this.motes = this.motes.filter((m) => m.life > 0);
    if (!this.motes.length && this.unsub) { this.unsub(); this.unsub = null; ctx.clearRect(0, 0, this.canvas.width, this.canvas.height); }
  }

  destroy() { this.unsub?.(); }
}
