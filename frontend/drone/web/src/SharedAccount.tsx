import { useEffect, useState } from "react";
import { api } from "./api";
import type { User, Workspace } from "./types";

const errors: Record<string, string> = {
  identity_cancelled:
    "Sign-in was cancelled. You can try again when you are ready.",
  identity_callback_invalid:
    "That sign-in link has expired. Start again to continue.",
  identity_rejected: "Your Onesa session has ended. Sign in again to continue.",
  identity_unavailable:
    "Onesa sign-in is temporarily unavailable. Please try again.",
  identity_account_changed:
    "Use the same Onesa account when confirming administrator access.",
  identity_reauthentication_expired:
    "Your session changed while you were confirming access. Sign in again to continue.",
  identity_reauthentication_required:
    "Confirm your Onesa account with MFA to continue.",
  identity_mfa_required:
    "Complete MFA in your Onesa account to use administrator access.",
  application_access_required:
    "Your account is ready. Ask an administrator for Drone access.",
};

export function accountError(): string {
  const url = new URL(location.href);
  const code = url.searchParams.get("account_error");
  if (!code) return "";
  url.searchParams.delete("account_error");
  history.replaceState(null, "", url.pathname + url.search + url.hash);
  return errors[code] || "Sign-in could not be completed. Please try again.";
}

export async function startSharedSignIn(reauthenticate = false) {
  const result = await api<{ authorization_url: string }>(
    "/auth/identity/start",
    "POST",
    { reauthenticate },
  );
  const target = new URL(result.authorization_url);
  const local =
    ["127.0.0.1", "localhost"].includes(location.hostname) &&
    ["127.0.0.1", "localhost"].includes(target.hostname);
  if (target.protocol !== "https:" && !(local && target.protocol === "http:"))
    throw new Error("The Onesa sign-in address is unavailable.");
  window.location.assign(target.href);
}

export function WorkspaceChooser({
  user,
  busy,
  notice,
  onSelect,
  onBack,
  onConfirm,
  onSignOut,
}: {
  user: User;
  busy: boolean;
  notice: string;
  onSelect: (id: string) => void;
  onBack?: () => void;
  onConfirm: () => void;
  onSignOut: () => void;
}) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(user.tenant_id || "");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api<{ workspaces: Workspace[] }>("/auth/workspaces")
      .then((result) => {
        if (active) setWorkspaces(result.workspaces);
      })
      .catch((failure) => {
        if (active) setError(failure.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [user.id, attempt]);
  return (
    <main className="identity-workspace" aria-labelledby="workspace-title">
      <a className="wordmark" href="/">
        ONESA <small>DRONE</small>
      </a>
      <p className="eyebrow">YOUR ONESA ACCOUNT</p>
      <h1 id="workspace-title">Choose your workspace</h1>
      <p>
        Signed in as <strong>{user.email}</strong>.
      </p>
      {user.global_admin && (
        <p className="identity-role">Onesa administrator · All applications</p>
      )}
      <p>
        Each workspace keeps its fleet, missions and access separate. Changing
        workspace clears open drafts.
      </p>
      {loading ? (
        <p role="status">Loading your workspaces…</p>
      ) : error ? (
        <div role="alert">
          <p>{error}</p>
          <button onClick={() => setAttempt(attempt + 1)}>Try again</button>
        </div>
      ) : workspaces.length ? (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (selected) onSelect(selected);
          }}
        >
          <label htmlFor="identity-workspace">Workspace</label>
          <select
            id="identity-workspace"
            required
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
          >
            <option value="" disabled>
              Select a workspace
            </option>
            {workspaces.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>
                {workspace.name} · {workspace.role}
              </option>
            ))}
          </select>
          <button className="primary" disabled={busy || !selected}>
            {busy ? "Opening workspace…" : "Open workspace"}
          </button>
        </form>
      ) : (
        <section className="identity-empty">
          <h2>Your account is ready</h2>
          <p>
            {user.global_admin
              ? "No Drone workspace is available yet. An existing simulation workspace must be configured before operations can open."
              : "Ask your Onesa administrator to add you to a Drone workspace. You do not need another account."}
          </p>
        </section>
      )}
      {notice && (
        <p role="alert" className="error">
          {notice}
        </p>
      )}
      <div className="identity-actions">
        {user.tenant_id && onBack && (
          <button disabled={busy} onClick={onBack}>
            Return to workspace
          </button>
        )}
        {user.global_admin && (
          <button disabled={busy} onClick={onConfirm}>
            Confirm administrator sign-in
          </button>
        )}
        {user.account_url && (
          <a href={user.account_url}>Account &amp; application access</a>
        )}
        <button disabled={busy} onClick={onSignOut}>
          Sign out of Onesa
        </button>
      </div>
      <p className="fine">
        Simulation only. Shared administrator access does not enable physical
        flight.
      </p>
    </main>
  );
}
