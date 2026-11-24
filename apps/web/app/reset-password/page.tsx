"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";

export default function ResetPasswordPage() {
  const supabase = useMemo(() => createClient(), []);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [recovery, setRecovery] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setRecovery(params.get("auth") === "recovery");
    if (params.get("auth") === "error") {
      setMessage("This reset link is invalid or expired. Request a new one.");
    }
  }, []);

  async function requestReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supabase) return;
    setBusy(true);
    setMessage("");
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), {
        redirectTo: `${window.location.origin}/auth/callback?next=/reset-password`,
      });
      setMessage(
        error
          ? error.message
          : "If an account exists for this email, a password-reset link has been sent.",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not send the reset link.");
    } finally {
      setBusy(false);
    }
  }

  async function savePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!supabase) return;
    setBusy(true);
    setMessage("");
    try {
      const { error } = await supabase.auth.updateUser({ password });
      if (error) {
        setMessage(error.message);
      } else {
        await supabase.auth.signOut();
        setPassword("");
        setMessage("Password updated. You can now sign in with your new password.");
        window.setTimeout(() => {
          window.location.assign("/");
        }, 900);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Password update failed.");
    } finally {
      setBusy(false);
    }
  }

  if (!supabase) {
    return <main className="auth-shell"><section className="auth-card"><h1>Authentication is not configured.</h1><p className="muted">Charvi needs its Supabase project URL and publishable key.</p></section></main>;
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <div className="brand-mark">C</div>
        <p className="eyebrow">CHARVI / ACCOUNT SECURITY</p>
        <h1>{recovery ? "Choose a new password." : "Reset your password."}</h1>
        <p className="muted">{recovery ? "Enter a new password for your Charvi account." : "We'll send a secure password-reset link to your email address."}</p>
        <form className="stack" onSubmit={recovery ? savePassword : requestReset}>
          {!recovery ? (
            <label>Email<input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
          ) : (
            <label>New password<input type="password" autoComplete="new-password" minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          )}
          {message && <p className="error" role="status">{message}</p>}
          <button className="primary" disabled={busy}>{busy ? "Please wait…" : recovery ? "Update password" : "Send reset link"}</button>
        </form>
        <p className="muted" style={{ marginTop: 18 }}><Link href="/">Back to sign in</Link></p>
      </section>
    </main>
  );
}
