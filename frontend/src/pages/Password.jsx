import React, { useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useApp } from "../context";
import { FormError, PageHeading } from "../components/common";
import PasswordField from "../components/PasswordField";

export default function Password() {
  const [params] = useSearchParams();
  const { pathname } = useLocation();
  const token = pathname === "/reset-password" ? params.get("token") : null;
  return <RecoveryForm key={token || pathname} token={token} />;
}

function RecoveryForm({ token }) {
  const { t, logout } = useApp();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [done, setDone] = useState(false);
  const [delivery, setDelivery] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => {
    if (!cooldown) return;
    const timer = setTimeout(() => setCooldown(cooldown - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);
  const submit = async (event) => {
    event?.preventDefault();
    if (busy) return;
    setError(null);
    if (token && password !== confirmation) {
      setError({ code: "passwords_mismatch" });
      return;
    }
    setBusy(true);
    try {
      const result = await api(`/auth/${token ? "reset-password" : "forgot-password"}`, {
        method: "POST", body: token ? { token, new_password: password } : { email },
      });
      if (token) {
        logout();
        setPassword("");
        setConfirmation("");
      } else {
        setDelivery(result.delivery);
        setCooldown(60);
      }
      setDone(true);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="page-container password-page">
      <PageHeading eyebrow="SAPARTRAVEL" title={t("resetPassword")} />
      <div className="surface">
        {done ? (
          <div className="stack-form">
            <p className="success-message" role="status">{t(token ? "passwordResetDone" : "resetSent")}</p>
            {!token && <>
              <p>{t("resetCheckSpam")}</p>
              {delivery === "local" && <p className="info-note">{t("resetLocalNote")}</p>}
              <FormError error={error} />
              <button type="button" className="button secondary" disabled={busy || cooldown > 0} onClick={() => submit()}>
                {t(busy ? "sending" : "resetRetry")}{cooldown > 0 ? ` (${cooldown})` : ""}
              </button>
              <button type="button" className="text-button" onClick={() => { setDone(false); setError(null); setEmail(""); }}>{t("resetChangeEmail")}</button>
            </>}
            <Link className="button primary" to="/login">{t("backToLogin")}</Link>
          </div>
        ) : (
          <form className="stack-form" onSubmit={submit}>
            {token ? <>
              <PasswordField label={t("newPassword")} required minLength={10} maxLength={128} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} hint={t("passwordHint")} />
              <PasswordField label={t("confirmPassword")} required minLength={10} maxLength={128} autoComplete="new-password" value={confirmation} onChange={(e) => setConfirmation(e.target.value)} />
            </> : <>
              <p>{t("resetInstructions")}</p>
              <label>{t("email")}<input type="email" required maxLength={254} autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
            </>}
            <FormError error={error} />
            <button className="button primary" disabled={busy}>{t(busy ? "sending" : token ? "changePassword" : "requestReset")}</button>
            {token && <Link className="text-link" to="/forgot-password">{t("requestReset")}</Link>}
            <Link className="text-link" to="/login">{t("backToLogin")}</Link>
          </form>
        )}
      </div>
    </div>
  );
}
export function ChangePassword() {
  const { t, token, authenticated } = useApp();
  const [form, setForm] = useState({ current_password: "", new_password: "" });
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(null);
  return (
    <section className="surface password-section">
      <form
        className="stack-form"
        onSubmit={async (e) => {
          e.preventDefault();
          if (form.new_password !== confirmation) {
            setError({ code: "passwords_mismatch" });
            setDone(false);
            return;
          }
          setBusy(true);
          setError(null);
          setDone(false);
          try {
            const response = await api("/auth/change-password", {
              token,
              method: "POST",
              body: form,
            });
            authenticated(response);
            setForm({ current_password: "", new_password: "" });
            setConfirmation("");
            setDone(true);
          } catch (error) {
            setError(error);
          } finally {
            setBusy(false);
          }
        }}
      >
        <h2>{t("changePassword")}</h2>
        <PasswordField label={t("currentPassword")}
            required
            autoComplete="current-password"
            value={form.current_password}
            onChange={(e) =>
              setForm({ ...form, current_password: e.target.value })
            }
          />
        <PasswordField label={t("newPassword")}
            required
            minLength={10}
            maxLength={128}
            autoComplete="new-password"
            value={form.new_password}
            onChange={(e) => setForm({ ...form, new_password: e.target.value })}
            hint={t("passwordHint")}
          />
        <PasswordField label={t("confirmPassword")} required minLength={10} maxLength={128} autoComplete="new-password" value={confirmation} onChange={(e) => setConfirmation(e.target.value)} />
        <FormError error={error} />
        {done && (
          <p className="success-message" role="status">
            {t("passwordChanged")}
          </p>
        )}
        <button className="button primary" disabled={busy}>
          {t(busy ? "saving" : "changePassword")}
        </button>
      </form>
    </section>
  );
}
