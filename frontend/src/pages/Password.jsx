import React, { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useApp } from "../context";
import { FormError, PageHeading } from "../components/common";
export default function Password() {
  const { t } = useApp();
  const [params] = useSearchParams();
  const token = params.get("token");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  return (
    <div className="page-container password-page">
      <PageHeading eyebrow="SAPARTRAVEL" title={t("resetPassword")} />
      <div className="surface">
        {done ? (
          <div className="stack-form">
            <p className="success-message" role="status">
              {t(token ? "passwordResetDone" : "resetSent")}
            </p>
            <Link className="button primary" to="/login">
              {t("login")}
            </Link>
          </div>
        ) : (
          <form
            className="stack-form"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError(null);
              try {
                await api(
                  `/auth/${token ? "reset-password" : "forgot-password"}`,
                  {
                    method: "POST",
                    body: token ? { token, new_password: password } : { email },
                  },
                );
                setDone(true);
              } catch (error) {
                setError(error);
              } finally {
                setBusy(false);
              }
            }}
          >
            {token ? (
              <label>
                {t("newPassword")}
                <input
                  required
                  minLength={10}
                  maxLength={128}
                  autoComplete="new-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <small>{t("passwordHint")}</small>
              </label>
            ) : (
              <label>
                {t("email")}
                <input
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </label>
            )}
            <FormError error={error} />
            <button className="button primary" disabled={busy}>
              {t(busy ? "sending" : token ? "changePassword" : "requestReset")}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
export function ChangePassword() {
  const { t, token, authenticated } = useApp();
  const [form, setForm] = useState({ current_password: "", new_password: "" });
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(null);
  return (
    <section className="surface password-section">
      <form
        className="stack-form"
        onSubmit={async (e) => {
          e.preventDefault();
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
            setDone(true);
          } catch (error) {
            setError(error);
          } finally {
            setBusy(false);
          }
        }}
      >
        <h2>{t("changePassword")}</h2>
        <label>
          {t("currentPassword")}
          <input
            type="password"
            required
            autoComplete="current-password"
            value={form.current_password}
            onChange={(e) =>
              setForm({ ...form, current_password: e.target.value })
            }
          />
        </label>
        <label>
          {t("newPassword")}
          <input
            type="password"
            required
            minLength={10}
            maxLength={128}
            autoComplete="new-password"
            value={form.new_password}
            onChange={(e) => setForm({ ...form, new_password: e.target.value })}
          />
          <small>{t("passwordHint")}</small>
        </label>
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
