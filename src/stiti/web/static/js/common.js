// Stiti web — shared helpers: scramble text, navbar (hide on scroll, mobile menu), token handling.
// Plain ES module, no build step.

const GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789/\\_-+*<>";
export const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Scramble an element's text: 18 frames × 30 ms, letters resolve left → right. */
export function scramble(el, { frames = 18, ms = 30, text } = {}) {
  if (reducedMotion) return;
  const final = text ?? el.dataset.text ?? el.textContent;
  el.dataset.text = final;
  clearInterval(el._scr);
  let f = 0;
  el._scr = setInterval(() => {
    f++;
    const solved = Math.floor((f / frames) * final.length);
    el.textContent = [...final].map((c, i) =>
      i < solved || c === " " ? c : GLYPHS[(Math.random() * GLYPHS.length) | 0]).join("");
    if (f >= frames) { clearInterval(el._scr); el.textContent = final; }
  }, ms);
}

/** Wire every [data-scramble] (or a parent [data-scramble-host]) to scramble on hover/focus. */
export function wireScramble(root = document) {
  root.querySelectorAll("[data-scramble]").forEach((el) => {
    if (el._wired) return;
    el._wired = true;
    el.setAttribute("aria-hidden", el.getAttribute("aria-hidden") ?? "false");
    const host = el.closest("[data-scramble-host]") || el;
    const go = () => scramble(el);
    host.addEventListener("mouseenter", go);
    host.addEventListener("focus", go);
  });
}

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
