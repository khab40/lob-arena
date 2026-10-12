import { useEffect, useRef, useState } from "react";
import { getDemoAuthConfig, getDemoSession, signInToDemo, signOutOfDemo } from "@/api/ceoAuth";
import type { DemoSession } from "@/api/ceoAuthContract";
import { loadGoogleSignIn, renderGoogleSignIn } from "./ceoGoogleSignIn";
import { CeoJourney } from "./CeoJourney";
import "./ceoDemo.css";

export function CeoDemoPage() {
  const [session, setSession] = useState<DemoSession | null>(null);
  const [checking, setChecking] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [attempt, setAttempt] = useState(0);
  const button = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    getDemoSession(controller.signal).then((value) => {
      if (!controller.signal.aborted) { setSession(value); setChecking(false); }
    }).catch(() => {
      if (!controller.signal.aborted) { setError("Sign-in is unavailable. Please try again."); setChecking(false); }
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (checking || session) return;
    const controller = new AbortController();
    const target = button.current;
    getDemoAuthConfig(controller.signal).then(async (config) => {
      if (controller.signal.aborted) return;
      setConfigured(config.configured);
      if (!config.configured) return;
      await loadGoogleSignIn();
      if (controller.signal.aborted || !target) return;
      renderGoogleSignIn(target, config.client_id!, config.nonce!, (credential) => {
        if (controller.signal.aborted) return;
        setBusy(true); setError("");
        signInToDemo(credential, controller.signal).then((value) => {
          if (!controller.signal.aborted) { setSession(value); setBusy(false); }
        }).catch(() => {
          if (!controller.signal.aborted) {
            setBusy(false); setError("Sign-in could not be completed. Please try again.");
            setAttempt((value) => value + 1);
          }
        });
      });
    }).catch(() => {
      if (!controller.signal.aborted) setError("Google sign-in is unavailable. Please try again.");
    });
    return () => { controller.abort(); target?.replaceChildren(); };
  }, [checking, session, attempt]);

  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      getDemoSession(controller.signal).then((value) => {
        if (!controller.signal.aborted) {
          setSession(value);
          if (!value) setError("Your session ended. Sign in to continue.");
        }
      }).catch(() => {
        if (!controller.signal.aborted) { setSession(null); setError("Access could not be confirmed. Sign in again."); }
      });
    }, 60000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [session]);

  async function logout() {
    setBusy(true); setError("");
    try {
      await signOutOfDemo(new AbortController().signal);
      setSession(null); setAttempt((value) => value + 1);
    } catch {
      setError("Sign-out could not be confirmed. Please try again.");
    } finally { setBusy(false); }
  }

  return <main className="ceo-demo">
    <header className="ceo-demo-header"><strong>LOB Arena</strong><span>Research demonstration</span></header>
    <section className="ceo-demo-card" aria-label={session ? "Demo workspace" : "Google sign-in"}>
      {session ? <>
        <div className="ceo-demo-account"><span>{session.user.name} · {session.user.email}</span>
          <button disabled={busy} onClick={logout} type="button">Sign out</button></div>
        <h1>Prepared research campaign</h1>
        <p>Inspect verified saved Transformer and LightGBM predictions, review an anomaly and retain its evidence.</p>
        <p role="status">Signed in to the demo workspace.</p>
        <CeoJourney key={JSON.stringify([session.workspace_id, session.user.id])}
          onAccessEnded={() => { setSession(null); setError("Your session ended. Sign in to continue."); }} />
      </> : <>
        <h1>Follow an anomaly from result to evidence</h1>
        <p>Sign in to open the prepared research campaign.</p>
        {checking ? <p role="status">Checking access…</p> : configured === false
          ? <p role="status">The demo is being prepared. Sign-in is not configured yet.</p> : null}
        <div className="ceo-google-button" ref={button} aria-label="Sign in with Google"
          hidden={checking || configured === false} />
        {busy ? <p role="status">Completing sign-in…</p> : null}
      </>}
      {error ? <p role="alert">{error}</p> : null}
      {!session && !checking && (error || configured === false) && !busy ? <button onClick={() => {
        setError(""); setAttempt((value) => value + 1);
      }} type="button">Try again</button> : null}
    </section>
    <footer>Saved research predictions · synthetic research labels</footer>
  </main>;
}
