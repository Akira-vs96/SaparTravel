import React, { useState } from "react";
import { ArrowRight, Compass } from "lucide-react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useApp } from "../context";
import { FormError, Photo } from "../components/common";

export default function Auth({ register = false }) {
  const { t, authenticated, user } = useApp();
  const [params] = useSearchParams();
  const rawNext = params.get("next") || "/account";
  const next =
    rawNext.startsWith("/") &&
    !rawNext.startsWith("//") &&
    !rawNext.includes("\\")
      ? rawNext
      : "/account";
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const change = (key) => (event) =>
    setForm({ ...form, [key]: event.target.value });
  if (user) return <Navigate to={next} replace />;
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const data = await api(`/auth/${register ? "register" : "login"}`, {
        method: "POST",
        body: register ? form : { email: form.email, password: form.password },
      });
      authenticated(data);
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="auth-page">
      <div className="auth-image">
        <Photo
          src="https://images.unsplash.com/photo-1519681393784-d120267933ba?auto=format&fit=crop&w=1200&q=85"
          alt=""
        />
        <div>
          <Compass size={36} />
          <h2>{t("tagline")}</h2>
          <p>{t("authText")}</p>
        </div>
      </div>
      <div className="auth-form-container">
        <p className="eyebrow">SAPARTRAVEL</p>
        <h1>{t(register ? "registerTitle" : "welcomeBack")}</h1>
        <p className="intro-text">{t("authText")}</p>
        <form className="stack-form" onSubmit={submit}>
          {register && (
            <label>
              {t("name")}
              <input
                value={form.name}
                onChange={change("name")}
                required
                minLength="2"
                maxLength="120"
                autoComplete="name"
              />
            </label>
          )}
          <label>
            {t("email")}
            <input
              type="email"
              required
              value={form.email}
              onChange={change("email")}
              autoComplete="email"
            />
          </label>
          <label>
            {t("password")}
            <input
              type="password"
              required
              minLength={register ? 10 : 1}
              maxLength="128"
              value={form.password}
              onChange={change("password")}
              autoComplete={register ? "new-password" : "current-password"}
            />
            {register && <small>{t("passwordHint")}</small>}
          </label>
          <FormError error={error} />
          <button disabled={busy} className="button primary full-width">
            {t(busy ? "sending" : register ? "register" : "login")}
            <ArrowRight size={17} />
          </button>
        </form>
        <p className="auth-switch">
          {t(register ? "haveAccount" : "noAccount")}{" "}
          <Link
            to={`${register ? "/login" : "/register"}?next=${encodeURIComponent(next)}`}
          >
            {t(register ? "login" : "register")}
          </Link>
        </p>
      </div>
    </div>
  );
}
