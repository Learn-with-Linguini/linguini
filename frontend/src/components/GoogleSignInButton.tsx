import { useEffect, useRef } from "react";

type CredentialResponse = {
  credential?: string;
};

type GoogleAccounts = {
  id: {
    initialize: (config: {
      client_id: string;
      callback: (response: CredentialResponse) => void;
      auto_select?: boolean;
      cancel_on_tap_outside?: boolean;
      use_fedcm_for_prompt?: boolean;
    }) => void;
    renderButton: (parent: HTMLElement, options: {
      type: "standard";
      theme: "outline";
      size: "large";
      text: "continue_with";
      shape: "rectangular";
      logo_alignment: "left";
      width: number;
    }) => void;
  };
};

declare global {
  interface Window {
    google?: { accounts: GoogleAccounts };
  }
}

const GOOGLE_SCRIPT_ID = "google-identity-services";
const GOOGLE_SCRIPT_SRC = "https://accounts.google.com/gsi/client";
let googleScriptPromise: Promise<GoogleAccounts> | null = null;

function loadGoogleAccounts(): Promise<GoogleAccounts> {
  if (window.google?.accounts) return Promise.resolve(window.google.accounts);
  if (googleScriptPromise) return googleScriptPromise;

  const scriptPromise = new Promise<GoogleAccounts>((resolve, reject) => {
    const existingScript = document.getElementById(GOOGLE_SCRIPT_ID) as HTMLScriptElement | null;
    const script = existingScript ?? document.createElement("script");

    const handleLoad = () => {
      if (window.google?.accounts) resolve(window.google.accounts);
      else reject(new Error("Google Identity Services did not initialize."));
    };
    const handleError = () => reject(new Error("Google Identity Services could not be loaded."));

    script.addEventListener("load", handleLoad, { once: true });
    script.addEventListener("error", handleError, { once: true });
    if (!existingScript) {
      script.id = GOOGLE_SCRIPT_ID;
      script.src = GOOGLE_SCRIPT_SRC;
      script.async = true;
      document.head.appendChild(script);
    }
  }).catch(error => {
    googleScriptPromise = null;
    throw error;
  });
  googleScriptPromise = scriptPromise;

  return scriptPromise;
}

type GoogleSignInButtonProps = {
  clientId: string;
  disabled?: boolean;
  onCredential: (credential: string) => void;
  onError: () => void;
};

export function GoogleSignInButton({ clientId, disabled = false, onCredential, onError }: GoogleSignInButtonProps) {
  const buttonRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    const button = buttonRef.current;
    if (!button) return;

    void loadGoogleAccounts().then(accounts => {
      if (!active || !buttonRef.current) return;
      accounts.id.initialize({
        client_id: clientId,
        callback: response => {
          if (response.credential) onCredential(response.credential);
          else onError();
        },
        auto_select: false,
        cancel_on_tap_outside: true,
        use_fedcm_for_prompt: true,
      });
      button.replaceChildren();
      accounts.id.renderButton(button, {
        type: "standard",
        theme: "outline",
        size: "large",
        text: "continue_with",
        shape: "rectangular",
        logo_alignment: "left",
        width: Math.min(400, Math.max(240, button.clientWidth)),
      });
    }).catch(() => {
      if (active) onError();
    });

    return () => {
      active = false;
      button.replaceChildren();
    };
  }, [clientId, onCredential, onError]);

  return (
    <div
      className="google-signin"
      ref={buttonRef}
      aria-disabled={disabled}
      style={disabled ? { pointerEvents: "none", opacity: 0.55 } : undefined}
    />
  );
}
