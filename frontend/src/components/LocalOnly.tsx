// Shown instead of Chat / Memory in the PUBLIC build (STITI_PUBLIC=1 pnpm build): those pages only exist on
// the owner's own Mac, served by Stiti at 127.0.0.1:7317. The public site never contains or fetches personal data.
import Link from "next/link";
import Nav from "@/components/Nav";

export default function LocalOnly({ page }: { page: "chat" | "memory" }) {
  return (
    <>
      <Nav current={page} />
      <main id="main" style={{ minHeight: "100dvh", display: "grid", placeItems: "center", padding: "120px var(--pad) 60px" }}>
        <div style={{ maxWidth: 620 }}>
          <p className="label">{page === "chat" ? "Chat" : "Memory"} · runs on your Mac</p>
          <h1 style={{ fontSize: "var(--fs-h2)", lineHeight: 1, letterSpacing: "-.035em", fontWeight: 400, margin: "14px 0 20px" }}>
            <span className="thin">This part lives</span><br /><span className="bold">on your own Mac.</span>
          </h1>
          <p style={{ color: "var(--ink-2)", margin: "0 0 28px" }}>
            Stiti&apos;s {page === "chat" ? "chat" : "memory"} never runs on a website. Install Stiti and it opens on your Mac at
            {" "}<code style={{ fontFamily: "var(--mono)", fontSize: ".9em" }}>127.0.0.1:7317</code>. Your conversations and everything
            she knows about you stay there.
          </p>
          <Link className="nav__cta" href="/" style={{ display: "inline-flex" }}>Back to home</Link>
        </div>
      </main>
    </>
  );
}
