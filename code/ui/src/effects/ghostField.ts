// "The Summoning": a Canvas-2D ghost particle field.
//  - particles drift on a cheap curl-ish flow (sin/cos field, no noise library)
//  - the pointer is a flashlight: particles brighten and masked PII fragments are revealed near it
//  - summon(): particles snap into the EXORCIST wordmark sampled from an offscreen canvas
// Performance: typed arrays, fillRect only, count capped by deviceBudget(), DPR capped, paused offscreen/hidden.
import { subscribe } from "./ticker";

// Generic masked patterns only — never values from the dataset.
const FRAGMENTS = [
  "k.r••@••••.com", "••• •• 4417", "user_••••", "+44 •••• ••3 18", "sha256: 9f2c••••••a1e0",
  "j.m•••••@••••.org", "acct_••••91", "DOB ••/••/19••", "•••• •••• •••• 0042", "m••••@••••.io",
  "export_••••.zip", "+81 90 •••• ••07", "s.o••@••••.net", "ip 10.•••.•.17",
];

export interface GhostFieldOptions { count: number; dpr: number }

export class GhostField {
  private ctx: CanvasRenderingContext2D;
  private w = 0;
  private h = 0;
  private n: number;
  private x: Float32Array; private y: Float32Array;
  private vx: Float32Array; private vy: Float32Array;
  private tx: Float32Array; private ty: Float32Array;
  private hasTarget: Uint8Array;
  private seed: Float32Array;
  private frags: { text: string; x: number; y: number; v: number }[] = [];
  private mx = -9999; private my = -9999; private sx = -9999; private sy = -9999;
  private summonT = 0;           // 0 = drifting, ramps to 1 when summoned
  private summoned = false;
  private unsub: (() => void) | null = null;
  private visible = true;
  private io: IntersectionObserver;

  constructor(private canvas: HTMLCanvasElement, private opts: GhostFieldOptions) {
    this.ctx = canvas.getContext("2d", { alpha: false })!;
    this.n = opts.count;
    const mk = () => new Float32Array(this.n);
    this.x = mk(); this.y = mk(); this.vx = mk(); this.vy = mk(); this.tx = mk(); this.ty = mk(); this.seed = mk();
    this.hasTarget = new Uint8Array(this.n);
    this.resize();
    for (let i = 0; i < this.n; i++) {
      this.x[i] = Math.random() * this.w; this.y[i] = Math.random() * this.h; this.seed[i] = Math.random();
    }
    // fragments on a jittered 7x4 grid (two copies of the list) so any flashlight position reveals at least one
    const all = [...FRAGMENTS, ...FRAGMENTS];
    this.frags = all.map((text, i) => {
      const gx = i % 7, gy = Math.floor(i / 7) % 4;
      return { text, x: ((gx + 0.25 + 0.5 * ((i * 0.618034) % 1)) / 7) * this.w,
               y: ((gy + 0.2 + 0.6 * ((i * 0.381966) % 1)) / 4) * this.h, v: 0.003 + (i % 5) * 0.0015 };
    });
    this.io = new IntersectionObserver(([e]) => { this.visible = e.isIntersecting; this.toggle(); });
    this.io.observe(canvas);
    this.toggle();
  }

  private toggle() {
    if (this.visible && !this.unsub) this.unsub = subscribe((dt, t) => this.frame(dt, t));
    else if (!this.visible && this.unsub) { this.unsub(); this.unsub = null; }
  }

  resize() {
    const r = this.canvas.getBoundingClientRect();
    this.w = Math.max(1, r.width); this.h = Math.max(1, r.height);
    this.canvas.width = Math.round(this.w * this.opts.dpr);
    this.canvas.height = Math.round(this.h * this.opts.dpr);
    this.ctx.setTransform(this.opts.dpr, 0, 0, this.opts.dpr, 0, 0);
    if (this.summoned) this.computeTargets();
  }

  pointer(x: number, y: number) { this.mx = x; this.my = y; }

  async summon() {
    if (this.summoned) return;
    this.summoned = true;
    await document.fonts.load(`400 200px "Instrument Serif"`).catch(() => undefined);
    this.computeTargets();
  }

  private computeTargets() {
    const off = document.createElement("canvas");
    const W = Math.round(this.w), H = Math.round(this.h);
    off.width = W; off.height = H;
    const g = off.getContext("2d")!;
    const size = Math.min(W * 0.2, H * 0.32);
    g.fillStyle = "#fff";
    g.textAlign = "center"; g.textBaseline = "middle";
    g.font = `400 ${size}px "Instrument Serif", Georgia, serif`;
    g.fillText("EXORCIST", W / 2, H * 0.4);
    const data = g.getImageData(0, 0, W, H).data;
    const pts: number[] = [];
    const step = Math.max(2, Math.round(Math.sqrt((W * H * 0.022) / this.n)));
    for (let py = 0; py < H; py += step) for (let px = 0; px < W; px += step) if (data[(py * W + px) * 4 + 3] > 140) pts.push(px, py);
    const k = pts.length / 2;
    for (let i = 0; i < this.n; i++) {
      if (i < Math.min(this.n * 0.88, k * 1.6)) {
        const j = (i * 7919) % k;   // spread particles over the glyphs deterministically
        this.tx[i] = pts[j * 2] + (Math.random() - 0.5) * step * 0.5; this.ty[i] = pts[j * 2 + 1] + (Math.random() - 0.5) * step * 0.5;
        this.hasTarget[i] = 1;
      } else this.hasTarget[i] = 0;
    }
  }

  private frame(dt: number, t: number) {
    const { ctx, w, h } = this;
    const k = dt / 16.67;
    if (this.summoned && this.summonT < 1) this.summonT = Math.min(1, this.summonT + 0.012 * k);
    const s = this.summonT * this.summonT * (3 - 2 * this.summonT);    // smoothstep
    this.sx += (this.mx - this.sx) * 0.18 * k; this.sy += (this.my - this.sy) * 0.18 * k;
    const R = Math.min(260, Math.max(170, w * 0.16));
    ctx.fillStyle = "rgba(7,7,11,0.34)";
    ctx.fillRect(0, 0, w, h);

    // flashlight cone
    if (this.sx > -1000) {
      const g = ctx.createRadialGradient(this.sx, this.sy, 0, this.sx, this.sy, R * 1.3);
      g.addColorStop(0, "rgba(124,255,178,0.075)"); g.addColorStop(1, "rgba(124,255,178,0)");
      ctx.fillStyle = g; ctx.fillRect(this.sx - R * 1.3, this.sy - R * 1.3, R * 2.6, R * 2.6);
    }

    // once the particles have nearly settled, a faint underlay of the same glyphs makes the word legible
    if (s > 0.85) {
      const size = Math.min(w * 0.2, h * 0.32);
      // the trail fade (34% ink per frame) accumulates this to ~3x: 0.07 settles near a 20% underlay
      ctx.globalAlpha = Math.min(0.07, (s - 0.85) * 0.5);
      ctx.fillStyle = "#EDE9E0";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.font = `400 ${size}px "Instrument Serif", Georgia, serif`;
      ctx.fillText("EXORCIST", w / 2, h * 0.4);
      ctx.globalAlpha = 1;
    }

    const tt = t * 0.00012;
    for (let i = 0; i < this.n; i++) {
      const sd = this.seed[i];
      // drift field
      const ax = Math.sin(this.y[i] * 0.004 + tt * 3 + sd * 6) * 0.05;
      const ay = Math.cos(this.x[i] * 0.004 - tt * 2 + sd * 6) * 0.05 - 0.008;
      this.vx[i] = (this.vx[i] + ax * k) * 0.96; this.vy[i] = (this.vy[i] + ay * k) * 0.96;
      let nx = this.x[i] + this.vx[i] * k * 6, ny = this.y[i] + this.vy[i] * k * 6;
      if (this.hasTarget[i] && s > 0) {
        nx += (this.tx[i] + Math.sin(t * 0.002 + sd * 20) * 0.6 - nx) * 0.09 * s * k;
        ny += (this.ty[i] + Math.cos(t * 0.002 + sd * 20) * 0.6 - ny) * 0.09 * s * k;
      }
      if (nx < -5) nx = w + 5; else if (nx > w + 5) nx = -5;
      if (ny < -5) ny = h + 5; else if (ny > h + 5) ny = -5;
      this.x[i] = nx; this.y[i] = ny;
      const dx = nx - this.sx, dy = ny - this.sy;
      const near = Math.max(0, 1 - Math.sqrt(dx * dx + dy * dy) / R);
      const word = this.hasTarget[i] ? s : 0;
      // constant colour strings + globalAlpha: no per-particle string allocation
      ctx.globalAlpha = Math.min(1, 0.16 + sd * 0.22 + near * 0.55 + word * 0.5);
      ctx.fillStyle = near > 0.15 ? "#A0FFCD" : word > 0.5 ? "#EDE9E0" : "#C8C4D6";
      const sz = (sd < 0.85 ? 1.1 : 1.9) + near * 0.9 + word * 0.7;
      ctx.fillRect(nx, ny, sz, sz);
    }
    ctx.globalAlpha = 1;

    // masked PII fragments: only visible inside the flashlight
    ctx.font = `500 14px "JetBrains Mono Variable", monospace`;
    ctx.textAlign = "center";
    ctx.shadowColor = "#7CFFB2";
    ctx.shadowBlur = 10;   // only a handful of fragments are ever lit, so the blur cost stays tiny
    for (const f of this.frags) {
      f.y -= f.v * k * 6; if (f.y < -20) f.y = h + 20;
      const dx = f.x - this.sx, dy = f.y - this.sy;
      const vis = Math.max(0, 1 - Math.sqrt(dx * dx + dy * dy) / (R * 0.95)) * (1 - s * 0.7);
      if (vis <= 0.01) continue;
      ctx.globalAlpha = vis * 0.95;
      ctx.fillStyle = "#7CFFB2";
      ctx.fillText(f.text, f.x, f.y);
    }
    ctx.shadowBlur = 0;
    ctx.globalAlpha = 1;
  }

  destroy() { this.unsub?.(); this.io.disconnect(); }
}
