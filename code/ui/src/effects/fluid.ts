// "Ink in water": one raw WebGL1 full-screen fragment shader (no three.js).
// Domain-warped fbm noise -> slowly morphing marbled ink. Rendered at 0.5x CSS resolution and upscaled by CSS,
// capped at 60 fps on the shared ticker, paused when the tab is hidden, and in "auto" performance mode the
// render scale steps down 0.5 -> 0.35 -> 0.25 when the frame time degrades.
import { subscribe } from "./ticker";
import { fluid } from "../lib/fluid";

const VERT = `attribute vec2 a; void main(){ gl_Position = vec4(a, 0.0, 1.0); }`;

const FRAG = `
precision mediump float;
uniform vec2 u_res; uniform float u_time; uniform float u_oct;
uniform vec2 u_mouse; uniform vec2 u_stir;
uniform float u_ratio; uniform float u_violet; uniform float u_purge; uniform vec2 u_origin;
uniform vec3 u_bloom; uniform float u_bright;

float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){
  vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}
float fbm(vec2 p){
  float v = 0.0, a = 0.5; mat2 m = mat2(1.6, 1.2, -1.2, 1.6);
  for (int i = 0; i < 5; i++){ if (float(i) >= u_oct) break; v += a * noise(p); p = m * p; a *= 0.5; }
  return v;
}
void main(){
  float asp = u_res.x / u_res.y;
  vec2 uv = gl_FragCoord.xy / u_res;
  vec2 p = (uv - 0.5) * vec2(asp, 1.0) * 1.7;
  float t = u_time * 0.03;

  // cursor stirs the ink: displacement along the damped pointer velocity, local to the cursor
  vec2 m = (u_mouse - 0.5) * vec2(asp, 1.0) * 1.7;
  p -= u_stir * exp(-dot(p - m, p - m) * 2.5) * 0.9;

  // click ink-bloom: an expanding, fading ring that pushes the field outward
  vec2 b = (u_bloom.xy - 0.5) * vec2(asp, 1.0) * 1.7;
  float bd = length(p - b);
  float ring = exp(-pow((bd - u_bloom.z * 0.75) * 7.0, 2.0)) * exp(-u_bloom.z * 1.4);
  p += (p - b) / (bd + 1e-3) * ring * 0.10;

  // exorcism purge: the wave front pushes the field away from the seal point
  vec2 o = (u_origin - 0.5) * vec2(asp, 1.0) * 1.7;
  float od = length(p - o);
  float front = u_purge * 3.2;
  float inside = 1.0 - smoothstep(front - 0.35, front, od);
  p += (p - o) / (od + 1e-3) * inside * u_purge * 0.25;

  // domain warp (iq style): q warps r, r warps the final field
  vec2 q = vec2(fbm(p + vec2(0.0, t)), fbm(p + vec2(5.2, 1.3) - t));
  vec2 r = vec2(fbm(p + 3.0 * q + vec2(1.7, 9.2) + 0.6 * t), fbm(p + 3.0 * q + vec2(8.3, 2.8) - 0.4 * t));
  float f = fbm(p + 3.4 * r);

  float veins = smoothstep(0.52, 0.92, f);
  float body = smoothstep(0.15, 0.85, f);

  // ember vs green partition: a slow large-scale field thresholded at the real haunted share
  float part = smoothstep(0.28, 0.72, fbm(p * 0.42 + r * 0.7 + vec2(t * 0.4, -t * 0.2)));
  float ember = 1.0 - smoothstep(u_ratio - 0.07, u_ratio + 0.07, part);
  ember *= (1.0 - inside) * (1.0 - 0.92 * u_purge);              // purge drives ember out and fades it

  float violet = smoothstep(0.60, 0.80, r.y) * smoothstep(0.35, 0.6, q.x) * u_violet * (1.0 - 0.7 * u_purge);

  vec3 ink = vec3(0.027, 0.027, 0.043);
  vec3 cEmber = vec3(1.0, 0.42, 0.28), cGreen = vec3(0.49, 1.0, 0.70), cViolet = vec3(0.61, 0.55, 1.0);
  vec3 tint = mix(cGreen, cEmber, ember);
  float lum = (veins * 0.62 + body * 0.18) * (0.75 + 0.25 * inside * u_purge);
  vec3 col = ink + tint * lum * 0.32 * u_bright + cViolet * violet * (0.22 + veins * 0.35) * u_bright;
  col += cGreen * ring * 0.12;                                    // bloom shimmer
  float vig = smoothstep(1.25, 0.25, length((uv - 0.5) * vec2(asp, 1.0)));
  gl_FragColor = vec4(col * (0.55 + 0.45 * vig), 1.0);
}`;

export type PerfMode = "auto" | "high" | "low";
const SCALES = [0.5, 0.35, 0.25];

export interface FluidStats {
  ok: boolean; scale: number; octaves: number; frames: number; emaMs: number; mode: PerfMode;
  downgrades: { at: number; from: number; to: number; emaMs: number }[];
  uniforms: { ratio: number; violet: number; purge: number };
}

export class FluidRenderer {
  private gl: WebGLRenderingContext;
  private loc: Record<string, WebGLUniformLocation | null> = {};
  private unsub: (() => void) | null = null;
  private scaleIdx = 0;
  private octaves = 5;
  private last = 0;
  private ema = 16.7;
  private slow = 0;                 // ms of sustained slow frames
  private load = 0;                 // test hook: artificial ms of work per frame
  private cur = { ratio: fluid.target.ratio, violet: fluid.target.violet, bright: 0 };
  stats: FluidStats;

  constructor(private canvas: HTMLCanvasElement, private mode: PerfMode, lowTier: boolean) {
    const gl = canvas.getContext("webgl", { antialias: false, depth: false, stencil: false, alpha: false, preserveDrawingBuffer: true,
                                             powerPreference: "low-power" });
    if (!gl) throw new Error("WebGL unavailable");
    this.gl = gl;
    const sh = (type: number, src: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error("shader compile failed: " + gl.getShaderInfoLog(s));
      return s;
    };
    const prog = gl.createProgram()!;
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, VERT)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error("program link failed: " + gl.getProgramInfoLog(prog));
    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const a = gl.getAttribLocation(prog, "a");
    gl.enableVertexAttribArray(a); gl.vertexAttribPointer(a, 2, gl.FLOAT, false, 0, 0);
    for (const n of ["u_res", "u_time", "u_oct", "u_mouse", "u_stir", "u_ratio", "u_violet", "u_purge", "u_origin", "u_bloom", "u_bright"])
      this.loc[n] = gl.getUniformLocation(prog, n);
    this.applyMode(mode, lowTier);
    this.stats = { ok: true, scale: SCALES[this.scaleIdx], octaves: this.octaves, frames: 0, emaMs: 0, mode, downgrades: [],
                   uniforms: { ratio: 0, violet: 0, purge: 0 } };
    canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); this.stats.ok = false; this.stop(); });
    this.resize();
    this.start();
  }

  applyMode(mode: PerfMode, lowTier = false) {
    this.mode = mode;
    if (mode === "high") { this.scaleIdx = 0; this.octaves = 5; }
    else if (mode === "low") { this.scaleIdx = 2; this.octaves = 3; }
    else { this.scaleIdx = lowTier ? 1 : 0; this.octaves = lowTier ? 4 : 5; }
    this.slow = 0;
    if (this.stats) { this.stats.mode = mode; this.stats.octaves = this.octaves; }
    this.resize();
  }

  setLoad(ms: number) { this.load = ms; }

  resize() {
    const s = SCALES[this.scaleIdx];
    this.canvas.width = Math.max(2, Math.round(innerWidth * s));
    this.canvas.height = Math.max(2, Math.round(innerHeight * s));
    this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    if (this.stats) this.stats.scale = s;
  }

  start() { if (!this.unsub) this.unsub = subscribe((dt, t) => this.frame(dt, t)); }
  stop() { this.unsub?.(); this.unsub = null; }

  private frame(_dt: number, t: number) {
    if (t - this.last < 15.5) return;                  // 60 fps cap even on 120/144 Hz displays
    const frameDt = this.last ? t - this.last : 16.7;
    this.last = t;
    if (this.load) { const until = performance.now() + this.load; while (performance.now() < until) { /* simulated load */ } }

    // auto mode: downgrade the render scale when the frame time stays bad
    this.ema = this.ema * 0.92 + frameDt * 0.08;
    // time-based: ~0.75 s of sustained frame time above 24 ms (< ~42 fps) steps the scale down one notch
    if (this.mode === "auto" && this.scaleIdx < SCALES.length - 1) {
      this.slow = this.ema > 24 ? this.slow + frameDt : Math.max(0, this.slow - frameDt * 2);
      if (this.slow > 750) {
        const from = SCALES[this.scaleIdx];
        this.scaleIdx++; this.slow = 0; this.ema = 20;   // re-measure at the new scale before deciding again
        if (this.scaleIdx === SCALES.length - 1) this.octaves = Math.min(this.octaves, 4);
        this.resize();
        this.stats.downgrades.push({ at: Math.round(t), from, to: SCALES[this.scaleIdx], emaMs: +this.ema.toFixed(1) });
      }
    }

    // ease toward the data-driven targets (smooth page-to-page transitions)
    const k = Math.min(1, frameDt / 900);
    this.cur.ratio += (fluid.target.ratio - this.cur.ratio) * k * 2;
    this.cur.violet += (fluid.target.violet - this.cur.violet) * k * 2;
    this.cur.bright += (fluid.target.bright - this.cur.bright) * k;
    const pt = fluid.pointer;
    pt.vx *= 0.94; pt.vy *= 0.94;                        // damped stir

    const gl = this.gl, L = this.loc;
    gl.uniform2f(L.u_res, this.canvas.width, this.canvas.height);
    gl.uniform1f(L.u_time, t / 1000);
    gl.uniform1f(L.u_oct, this.octaves);
    gl.uniform2f(L.u_mouse, pt.x, pt.y);
    gl.uniform2f(L.u_stir, pt.vx, pt.vy);
    gl.uniform1f(L.u_ratio, this.cur.ratio);
    gl.uniform1f(L.u_violet, this.cur.violet);
    gl.uniform1f(L.u_purge, fluid.purge.v);
    gl.uniform2f(L.u_origin, fluid.origin[0], fluid.origin[1]);
    gl.uniform3f(L.u_bloom, fluid.bloom.x, fluid.bloom.y, (performance.now() - fluid.bloom.t0) / 1000);
    gl.uniform1f(L.u_bright, this.cur.bright);
    gl.drawArrays(gl.TRIANGLES, 0, 3);

    this.stats.frames++;
    this.stats.emaMs = +this.ema.toFixed(2);
    this.stats.uniforms = { ratio: +this.cur.ratio.toFixed(4), violet: +this.cur.violet.toFixed(4), purge: +fluid.purge.v.toFixed(4) };
  }

  destroy() { this.stop(); this.gl.getExtension("WEBGL_lose_context")?.loseContext(); }
}
