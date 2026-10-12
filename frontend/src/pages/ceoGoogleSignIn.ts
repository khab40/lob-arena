type CredentialReply = { credential: string };
type GoogleIdentity = {
  initialize(options: { client_id: string; nonce: string; callback: (reply: CredentialReply) => void }): void;
  renderButton(element: HTMLElement, options: { theme: string; size: string; text: string }): void;
};

declare global {
  interface Window { google?: { accounts: { id: GoogleIdentity } } }
}

let scriptPromise: Promise<void> | undefined;

export function loadGoogleSignIn(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve();
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => window.google?.accounts?.id ? resolve() : reject(new Error("Google sign-in is unavailable."));
    script.onerror = () => { script.remove(); reject(new Error("Google sign-in is unavailable.")); };
    document.head.appendChild(script);
  }).catch((error: unknown) => { scriptPromise = undefined; throw error; });
  return scriptPromise;
}

export function renderGoogleSignIn(element: HTMLElement, clientId: string, nonce: string,
                                   callback: (credential: string) => void) {
  const google = window.google?.accounts?.id;
  if (!google) throw new Error("Google sign-in is unavailable.");
  element.replaceChildren();
  google.initialize({ client_id: clientId, nonce, callback: (reply) => callback(reply.credential) });
  google.renderButton(element, { theme: "outline", size: "large", text: "signin_with" });
}
