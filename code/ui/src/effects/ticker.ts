// The single animation loop. All canvas effects subscribe here; GSAP's ticker is the one rAF behind it,
// so GSAP timelines and canvas effects share a frame. The loop sleeps when nobody is subscribed and when
// the tab is hidden.
import { gsap } from "gsap";

type Fn = (dt: number, t: number) => void;
const subs = new Set<Fn>();
let attached = false;
let last = 0;

function tick(time: number) {
  const t = time * 1000;
  const dt = Math.min(48, last ? t - last : 16);
  last = t;
  subs.forEach((fn) => fn(dt, t));
}

function sync() {
  const want = subs.size > 0 && !document.hidden;
  if (want && !attached) { last = 0; gsap.ticker.add(tick); attached = true; }
  if (!want && attached) { gsap.ticker.remove(tick); attached = false; }
}

document.addEventListener("visibilitychange", sync);
gsap.ticker.lagSmoothing(500, 33);

export function subscribe(fn: Fn): () => void {
  subs.add(fn);
  sync();
  return () => { subs.delete(fn); sync(); };
}
