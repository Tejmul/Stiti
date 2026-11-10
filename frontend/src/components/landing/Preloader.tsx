// Preloader markup (logo + 000% counter + line). Its timeline lives in Landing, because it hands off to the
// particle sphere and the hero. The logo only fades/scales in — it never rotates (owner request).
export default function Preloader() {
  return (
    <div className="loader" aria-hidden="true">
      <svg className="loader__logo" viewBox="0 0 32 32" fill="none">
        <circle cx="16" cy="16" r="6.5" fill="currentColor" />
        <ellipse cx="16" cy="16" rx="14" ry="5.2" stroke="currentColor" strokeWidth="2.2" transform="rotate(-24 16 16)" />
      </svg>
      <div className="loader__count">
        <div className="loader__num">000%</div>
        <div className="loader__line" />
      </div>
    </div>
  );
}
