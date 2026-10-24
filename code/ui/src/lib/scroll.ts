// Programmatic scrolling that cooperates with Lenis (native scrollIntoView is overridden while Lenis is active).
import type Lenis from "lenis";

let lenis: Lenis | null = null;
export const setLenis = (l: Lenis | null) => { lenis = l; };

export function scrollToCenter(el: Element, smooth = true) {
  const r = el.getBoundingClientRect();
  const target = scrollY + r.top + r.height / 2 - innerHeight / 2;
  if (lenis) lenis.scrollTo(target, { immediate: !smooth, duration: 0.9 });
  else window.scrollTo({ top: target, behavior: smooth ? "smooth" : "auto" });
}
