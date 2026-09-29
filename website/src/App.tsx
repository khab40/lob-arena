import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { Link, NavLink, Route, Routes, useLocation } from 'react-router';
import { repository } from './data/research';
import Home from './pages/Home';
import Research from './pages/Research';
import Architecture from './pages/Architecture';
import Detectors from './pages/Detectors';
import About from './pages/About';

const Demo = lazy(() => import('./pages/Demo'));
const pages = [
  ['/', 'Home', '01'], ['/demo', 'Arena Demo', '02'], ['/research', 'Research', '03'],
  ['/architecture', 'Architecture', '04'], ['/detectors', 'Detectors / ML', '05'], ['/about', 'About / Docs', '06'],
];
export default function App() {
  const { pathname, hash } = useLocation();
  const [open, setOpen] = useState(false);
  const main = useRef<HTMLElement>(null);
  useEffect(() => {
    document.title = `${pages.find(([path]) => path === pathname)?.[1] ?? 'Page not found'} · LOB Arena`;
    const contact = pathname === '/about' && hash === '#contact'
      ? document.getElementById('contact') : null;
    if (contact) {
      contact.scrollIntoView({ block: 'start' });
      contact.focus({ preventScroll: true });
    } else {
      window.scrollTo(0, 0);
      main.current?.focus();
    }
  }, [pathname, hash]);
  return <div className="app-shell">
    <a className="skip-link" href="#main-content" onClick={(event) => { event.preventDefault(); main.current?.focus(); }}>Skip to content</a>
    <aside className="sidebar">
      <Link to="/" className="brand" aria-label="LOB Arena home"><span className="brand-mark" aria-hidden="true">▥</span><span>LOB <b>ARENA</b><small>RESEARCH & VALIDATION</small></span></Link>
      <button className="menu-toggle" aria-expanded={open} aria-controls="navigation" onClick={() => setOpen(!open)}>{open ? 'Close menu' : 'Open menu'}</button>
      <nav id="navigation" className={open ? 'navigation is-open' : 'navigation'} aria-label="Main navigation">
        {pages.map(([path, label, number]) => <NavLink end={path === '/'} key={path} to={path} onClick={() => setOpen(false)}><span className="nav-number">{number}</span>{label}</NavLink>)}
      </nav>
      <div className="sidebar-bottom"><span className="pill">PUBLIC RESEARCH</span><p>Reproducible scenarios.<br />Inspectable evidence.</p><a href={repository}>View on GitHub ↗</a></div>
    </aside>
    <div className="main-shell">
      <div className="topbar"><span>MARKET ABUSE · RED TEAM VS BLUE TEAM</span><span className="local-badge"><i /> Static research showcase</span></div>
      <main id="main-content" tabIndex={-1} ref={main}>
        <Suspense fallback={<p role="status">Loading the bundled replay…</p>}>
          <Routes>
            <Route path="/" element={<Home />} /><Route path="/demo" element={<Demo />} />
            <Route path="/research" element={<Research />} /><Route path="/architecture" element={<Architecture />} />
            <Route path="/detectors" element={<Detectors />} /><Route path="/about" element={<About />} />
            <Route path="*" element={<section className="page-intro"><p className="eyebrow">404</p><h1>That page is outside the arena.</h1><Link className="button" to="/">Back to Home</Link></section>} />
          </Routes>
        </Suspense>
      </main>
      <footer><span>LOB Arena · Research, replay, evidence.</span><Link to="/about">Scope & documentation ↗</Link></footer>
    </div>
  </div>;
}
