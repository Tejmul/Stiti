// Inline stroke icons for the board dock (no emoji, no icon font). 24×24, drawn with currentColor.
const P: Record<string, React.ReactNode> = {
  back: <><path d="M19 20 9 12l10-8v16Z" /><path d="M5 19V5" /></>,
  next: <><path d="m5 4 10 8-10 8V4Z" /><path d="M19 5v14" /></>,
  pause: <path d="M9 5v14M15 5v14" />,
  play: <path d="M7 4.5v15L19 12 7 4.5Z" />,
  repeat: <><path d="M3 12a9 9 0 1 0 2.6-6.4L3 8" /><path d="M3 3v5h5" /></>,
  slow: <path d="M5 12h14" />,
  fast: <path d="M5 12h14M12 5v14" />,
  pen: <path d="M17 3a2.8 2.8 0 0 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />,
  full: <path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3" />,
  mic: <><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" /></>,
  send: <path d="M12 19V5M6 11l6-6 6 6" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
};

export type IconName = keyof typeof P;

export default function Icon({ name }: { name: IconName }) {
  return <svg className="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">{P[name]}</svg>;
}
