import type { ReactNode } from 'react';

export function PageIntro({ eyebrow, title, children }: { eyebrow: string; title: string; children: ReactNode }) {
  return <header className="page-intro"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="lede">{children}</p></header>;
}
export function Panel({ title, children, className = '' }: { title: string; children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}><h2>{title}</h2>{children}</section>;
}
export function SourceLink({ href, children }: { href: string; children: ReactNode }) {
  return <a className="text-link" href={href}>{children} <span aria-hidden="true">↗</span></a>;
}
export function StatusNote() {
  return <aside className="notice"><span className="status-dot" /> Research platform. Near-real-time detection is a target direction; production surveillance is not claimed.</aside>;
}
