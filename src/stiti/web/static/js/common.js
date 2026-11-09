// Stiti web — shared helpers: navbar (hide on scroll, mobile menu), token handling.
// Plain ES module, no build step.

export const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Text effects are off by owner request: words never turn into random characters (on hover or on load).
 *  Kept as no-op functions so pages that call them keep working. */
export function scramble(el, { text } = {}) {
  if (text != null) el.textContent = text;
}
export function wireScramble() {}

/** Navbar: hide on scroll down, show on scroll up; mobile menu overlay. */
export function wireNav({ onMenu } = {}) {
  const nav = document.querySelector(".nav");
  if (!nav) return;
  let last = scrollY;
  addEventListener("scroll", () => {
    const y = scrollY;
    if (Math.abs(y - last) < 6) return;
    nav.classList.toggle("is-hidden", y > last && y > 120 && !document.body.classList.contains("menu-open"));
    last = y;
  }, { passive: true });
  const btn = nav.querySelector(".nav__menu-btn"), menu = document.querySelector(".menu");
  if (btn && menu) {
    const links = menu.querySelectorAll(".menu__links a span");
    const set = (open) => {
      menu.classList.toggle("is-open", open);
      document.body.classList.toggle("menu-open", open);
      btn.setAttribute("aria-expanded", String(open));
      btn.textContent = open ? "CLOSE" : "MENU";
      links.forEach((s, i) => (s.style.transitionDelay = open ? `${i * 70}ms` : "0ms"));
      onMenu?.(open);
    };
    btn.addEventListener("click", () => set(!menu.classList.contains("is-open")));
    menu.querySelectorAll("a").forEach((a) => a.addEventListener("click", () => set(false)));
    addEventListener("keydown", (e) => e.key === "Escape" && set(false));
  }
  wireScramble(nav);
}

/** Per-install token for the local API: arrives once in the URL fragment, then lives in localStorage. */
export function token() {
  const h = new URLSearchParams(location.hash.slice(1)).get("t");
  try {
    if (h) { localStorage.setItem("stiti_t", h); history.replaceState(null, "", location.pathname); }
    return h || localStorage.getItem("stiti_t") || "";
  } catch { return h || ""; }
}
