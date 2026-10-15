import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { getDemoAuthConfig, getDemoSession, signInToDemo, signOutOfDemo } from "@/api/ceoAuth";
import type { DemoSession } from "@/api/ceoAuthContract";
import { loadGoogleSignIn, renderGoogleSignIn } from "./ceoGoogleSignIn";
import { CeoJourney } from "./CeoJourney";
import { startSessionRequests } from "@/api/sessionRequests";
import { clearControlCenterIncident } from "@/controlCenterIncident";

export function CeoDemoPage({ children }: { children: ReactNode }) {
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

  return <>
    <section className="panel" aria-label={session ? "Demo workspace" : "Google sign-in"}>
      {session ? <>
        <div className="toolbar"><strong>{session.user.name} · {session.user.email}</strong>
          <button className="secondary-button" disabled={busy} onClick={logout} type="button">Sign out</button></div>
        <p role="status">Signed in to the demo workspace.</p>
      </> : <>
        <h2>Google sign-in</h2>
        <p>Sign in to use LOB Arena and its verified saved research.</p>
        {checking ? <p role="status">Checking access…</p> : configured === false
          ? <p role="status">The demo is being prepared. Sign-in is not configured yet.</p> : null}
        <div ref={button} aria-label="Sign in with Google"
          hidden={checking || configured === false} />
        {busy ? <p role="status">Completing sign-in…</p> : null}
      </>}
      {error ? <p role="alert">{error}</p> : null}
      {!session && !checking && (error || configured === false) && !busy ? <button className="secondary-button" onClick={() => {
        setError(""); setAttempt((value) => value + 1);
      }} type="button">Try again</button> : null}
    </section>
    {session ? <SessionWorkspace key={JSON.stringify([session.workspace_id, session.user.id])}
      onAccessEnded={() => { setSession(null); setError("Your session ended. Sign in to continue."); }}>{children}</SessionWorkspace> : null}
  </>;
}

function SessionWorkspace({ children, onAccessEnded }: { children: ReactNode; onAccessEnded: () => void }) {
  const ended = useRef(onAccessEnded); ended.current = onAccessEnded;
  const [ready, setReady] = useState(false);
  useLayoutEffect(() => {
    clearControlCenterIncident();
    const stop = startSessionRequests(() => ended.current());
    setReady(true);
    return () => { stop(); clearControlCenterIncident(); };
  }, []);
  return ready ? <CeoJourney onAccessEnded={() => ended.current()}>{children}</CeoJourney> : null;
}
