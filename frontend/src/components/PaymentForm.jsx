import React, { useRef, useState } from "react";
import {
  CreditCard,
  ShieldCheck,
  CheckCircle2,
  RefreshCw,
  TriangleAlert,
} from "lucide-react";
import { api } from "../api";
import { useApp } from "../context";
import { money, formatTime } from "../i18n";
import { FormError, ResourceState, useResource } from "./common";
const scenarios = {
  success: "cardSuccess",
  insufficient_funds: "cardFunds",
  bank_declined: "cardDeclined",
  blocked: "cardDeclined",
  "3ds": "card3ds",
  requires_action: "card3ds",
  provider_unavailable: "cardUnavailable",
  timeout_success: "cardTimeoutSuccess",
  timeout_failure: "cardTimeoutFailure",
  expired: "cardExpired",
};
export default function PaymentForm({ booking, onChange }) {
  const { t, lang, token } = useApp();
  const instruments = useResource("/payments/test-instruments", { auth: true });
  const [form, setForm] = useState({
    card_number: "",
    holder_name: "DEMO TRAVELER",
    expiry_month: "",
    expiry_year: "",
    cvc: "",
  });
  const [payment, setPayment] = useState(
    () =>
      [...(booking.payments || [])]
        .reverse()
        .find((p) => ["requires_action", "unknown"].includes(p.status)) || null,
  );
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const guard = useRef(false);
  const idem = useRef(crypto.randomUUID());
  const update = (key, value) =>
    setForm((current) => ({ ...current, [key]: value }));
  const run = async (path, body) => {
    if (guard.current) return;
    guard.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await api(path, {
        token,
        method: "POST",
        headers: { "Idempotency-Key": idem.current },
        body,
      });
      setPayment(result);
      if (["succeeded", "failed", "cancelled"].includes(result.status))
        idem.current = crypto.randomUUID();
      if (result.status === "succeeded") onChange();
    } catch (error) {
      setError(error);
      if (error.status === 409) onChange();
    } finally {
      setBusy(false);
      guard.current = false;
    }
  };
  const submit = (e) => {
    e.preventDefault();
    run(`/bookings/${booking.id}/payments`, {
      ...form,
      card_number: form.card_number.replace(/\s/g, ""),
      expiry_month: Number(form.expiry_month),
      expiry_year: Number(form.expiry_year),
    });
  };
  const pending =
    payment && ["requires_action", "unknown"].includes(payment.status);
  return (
    <section className="surface payment-surface">
      <div className="payment-title">
        <CreditCard size={27} />
        <div>
          <h2>{t("payment")}</h2>
          <p>{t("demoPayment")}</p>
        </div>
      </div>
      <p className="info-note">{t("testCardOnly")}</p>
      {["failed", "cancelled"].includes(payment?.status) && (
        <div className="payment-status failed" role="alert">
          <TriangleAlert size={22} />
          <div>
            <strong>{t("paymentFailed")}</strong>
            <p>
              {t(payment.error_code) !== payment.error_code
                ? t(payment.error_code)
                : payment.message || t("retryPayment")}
            </p>
          </div>
        </div>
      )}
      {payment?.status === "succeeded" && (
        <div className="payment-status succeeded" role="status">
          <CheckCircle2 size={25} />
          {t("paymentSuccess")}
        </div>
      )}
      {payment?.status === "unknown" && (
        <div className="payment-status unknown">
          <RefreshCw size={24} />
          <div>
            <h3>{t("paymentUnknown")}</h3>
            <p>{t("paymentUnknownText")}</p>
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => run(`/payments/${payment.id}/reconcile`)}
            >
              {t(busy ? "loading" : "reconcile")}
            </button>
          </div>
        </div>
      )}
      {payment?.status === "requires_action" && (
        <div className="secure-panel">
          <ShieldCheck size={34} />
          <h3>{t("secureConfirm")}</h3>
          <p>{t("secureText")}</p>
          {payment.action_expires_at && (
            <p>
              {t("confirmUntil")} {formatTime(payment.action_expires_at, lang)}
            </p>
          )}
          <div className="button-row">
            {[
              ["success", "confirm"],
              ["failure", "reject"],
              ["expired", "secureExpired"],
              ["cancelled", "close"],
            ].map(([outcome, key]) => (
              <button
                key={outcome}
                className={`button ${outcome === "success" ? "primary" : "secondary"}`}
                disabled={busy}
                onClick={() =>
                  run(`/payments/${payment.id}/confirm`, { outcome })
                }
              >
                {t(key)}
              </button>
            ))}
          </div>
        </div>
      )}
      {!pending && payment?.status !== "succeeded" && (
        <form className="stack-form payment-form" onSubmit={submit}>
          <ResourceState resource={instruments}>
            {(data) => (
              <label>
                {t("testInstruments")}
                <select
                  defaultValue=""
                  onChange={(e) => {
                    const card = (data.items || data.cards || []).find(
                      (item) =>
                        String(item.id || item.card_number) === e.target.value,
                    );
                    if (card)
                      setForm({
                        card_number: card.card_number,
                        holder_name: "DEMO TRAVELER",
                        expiry_month: card.expiry_month,
                        expiry_year: card.expiry_year,
                        cvc: card.cvc,
                      });
                  }}
                >
                  <option value="" disabled>
                    {t("chooseTestCard")}
                  </option>
                  {(data.items || data.cards || []).map((card) => (
                    <option
                      key={card.id || card.card_number}
                      value={card.id || card.card_number}
                    >
                      {t(scenarios[card.scenario] || card.scenario) ===
                      card.scenario
                        ? card.name
                        : t(scenarios[card.scenario] || card.scenario)}{" "}
                      · {card.masked_card || card.card_number.slice(-4)}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </ResourceState>
          <label>
            {t("cardNumber")}
            <input
              inputMode="numeric"
              autoComplete="off"
              required
              maxLength={23}
              placeholder="4242 4242 4242 4242"
              value={form.card_number}
              onChange={(e) =>
                update("card_number", e.target.value.replace(/[^\d ]/g, ""))
              }
            />
          </label>
          <label>
            {t("holderName")}
            <input
              required
              minLength={2}
              maxLength={120}
              autoComplete="off"
              value={form.holder_name}
              onChange={(e) => update("holder_name", e.target.value)}
            />
          </label>
          <div className="card-fields">
            <label>
              {t("expiryMonth")}
              <input
                inputMode="numeric"
                required
                maxLength={2}
                placeholder="MM"
                value={form.expiry_month}
                onChange={(e) => update("expiry_month", e.target.value)}
              />
            </label>
            <label>
              {t("expiryYear")}
              <input
                inputMode="numeric"
                required
                maxLength={4}
                placeholder="YYYY"
                value={form.expiry_year}
                onChange={(e) => update("expiry_year", e.target.value)}
              />
            </label>
            <label>
              {t("cardCvc")}
              <input
                inputMode="numeric"
                type="password"
                autoComplete="off"
                required
                maxLength={4}
                placeholder="123"
                value={form.cvc}
                onChange={(e) => update("cvc", e.target.value)}
              />
            </label>
          </div>
          <FormError error={error} />
          <button className="button primary full-width" disabled={busy}>
            {t(
              busy
                ? "sending"
                : payment?.status === "failed"
                  ? "retryPayment"
                  : "pay",
            )}{" "}
            · {money(booking.total_amount, lang)}
            <ShieldCheck size={18} />
          </button>
        </form>
      )}
      {pending && <FormError error={error} />}
    </section>
  );
}
