// Pre-split words for the masked "rise" reveals (the original split them at runtime; doing it in JSX keeps
// React's DOM untouched). mask=false gives bare word spans (used by the quote's scrubbed opacity).
export default function Split({ t, mask = true }: { t: string; mask?: boolean }) {
  return (
    <>
      {t.split(/(\s+)/).map((tok, i) =>
        !tok ? null
          : /^\s+$/.test(tok) ? " "
          : mask ? <span className="wm" key={i}><span className="w">{tok}</span></span>
          : <span className="w" key={i}>{tok}</span>,
      )}
    </>
  );
}
