import React, { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ShieldCheck,
  CalendarDays,
} from "lucide-react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { api } from "../api";
import { useApp } from "../context";
import { money, formatDate } from "../i18n";
import {
  FormError,
  PageHeading,
  Photo,
  ResourceState,
  useResource,
} from "../components/common";
import CancellationPolicy from "../components/CancellationPolicy";
export function CheckoutSteps({ active = 1 }) {
  const { t } = useApp();
  return (
    <ol className="checkout-steps">
      {["tripDetails", "payment", "confirmation"].map((key, index) => (
        <li
          key={key}
          className={active >= index + 1 ? "active" : ""}
          aria-current={active === index + 1 ? "step" : undefined}
        >
          <span>{active > index + 1 ? <Check size={15} /> : index + 1}</span>
          {t(key)}
        </li>
      ))}
    </ol>
  );
}
export default function Checkout() {
  const { slug } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { lang, t, user, token } = useApp();
  const resource = useResource(`/experiences/${slug}?lang=${lang}`);
  const count = Math.max(1, Math.min(20, Number(params.get("travelers")) || 1));
  const draftKey = `sapar-checkout:${user.id}:${slug}:${params.get("departure")}`;
  const [form, setForm] = useState(() => {
    let draft;
    try {
      draft = JSON.parse(sessionStorage.getItem(draftKey));
    } catch {}
    return (
      draft || {
        contact_name: user.name,
        contact_email: user.email,
        participants: Array.from({ length: count }, (_, i) => ({
          name: i === 0 ? user.name : "",
        })),
        service_ids: [],
        promo_code: "",
        notes: "",
        accept_cancellation_policy: false,
      }
    );
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [quote, setQuote] = useState(null);
  const submitGuard = useRef(false);
  useEffect(() => {
    try {
      sessionStorage.setItem(draftKey, JSON.stringify(form));
    } catch {}
    setQuote(null);
  }, [form, draftKey]);
  const update = (key, value) =>
    setForm((current) => ({ ...current, [key]: value }));
  const submit = async (e, departure) => {
    e.preventDefault();
    if (submitGuard.current) return;
    submitGuard.current = true;
    setBusy(true);
    setError(null);
    try {
      const result = await api(quote ? "/bookings" : "/bookings/quote", {
        token,
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: {
          ...form,
          departure_id: departure.id,
          travelers_count: form.participants.length,
          promo_code: form.promo_code.trim(),
        },
      });
      if (!quote) {
        setQuote(result);
        return;
      }
      try {
        sessionStorage.removeItem(draftKey);
      } catch {}
      navigate(`/bookings/${result.id}?pay=1`);
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
      submitGuard.current = false;
    }
  };
  return (
    <div className="page-container checkout-page">
      <Link className="back-link" to={`/trips/${slug}`}>
        <ArrowLeft size={16} />
        {t("tripDetails")}
      </Link>
      <PageHeading eyebrow="SAPARTRAVEL" title={t("checkout")} />
      <CheckoutSteps />
      <ResourceState resource={resource}>
        {(tour) => {
          const departure = tour.departures.find(
            (item) => item.id === params.get("departure"),
          );
          if (!departure) return <FormError error={t("noDatesText")} />;
          const estimate =
            Number(departure.price) * form.participants.length +
            (tour.services || [])
              .filter((s) => form.service_ids.includes(s.id))
              .reduce(
                (sum, s) =>
                  sum +
                  Number(s.price) *
                    (s.per_person ? form.participants.length : 1),
                0,
              );
          return (
            <form
              className="checkout-layout"
              onSubmit={(e) => submit(e, departure)}
            >
              <div className="checkout-main">
                <section className="surface stack-form">
                  <h2>{t("participants")}</h2>
                  <p className="muted">{t("participantHint")}</p>
                  {form.participants.map((person, index) => (
                    <label key={index}>
                      {t("participant")} {index + 1}
                      <input
                        required
                        minLength={2}
                        maxLength={120}
                        autoComplete={index === 0 ? "name" : "off"}
                        value={person.name}
                        onChange={(e) =>
                          update(
                            "participants",
                            form.participants.map((p, i) =>
                              i === index ? { name: e.target.value } : p,
                            ),
                          )
                        }
                      />
                    </label>
                  ))}
                </section>
                <section className="surface stack-form">
                  <h2>{t("contacts")}</h2>
                  <div className="form-row">
                    <label>
                      {t("contactName")}
                      <input
                        required
                        minLength={2}
                        maxLength={120}
                        autoComplete="name"
                        value={form.contact_name}
                        onChange={(e) => update("contact_name", e.target.value)}
                      />
                    </label>
                    <label>
                      {t("contactEmail")}
                      <input
                        required
                        type="email"
                        autoComplete="email"
                        value={form.contact_email}
                        onChange={(e) =>
                          update("contact_email", e.target.value)
                        }
                      />
                    </label>
                  </div>
                  <label>
                    {t("notes")} · {t("optional")}
                    <textarea
                      rows={3}
                      maxLength={2000}
                      value={form.notes}
                      onChange={(e) => update("notes", e.target.value)}
                    />
                  </label>
                </section>
                {tour.services?.length > 0 && (
                  <section className="surface stack-form">
                    <h2>{t("additionalServices")}</h2>
                    {tour.services.map((service) => (
                      <label className="service-option" key={service.id}>
                        <input
                          type="checkbox"
                          checked={form.service_ids.includes(service.id)}
                          onChange={(e) =>
                            update(
                              "service_ids",
                              e.target.checked
                                ? [...form.service_ids, service.id]
                                : form.service_ids.filter(
                                    (id) => id !== service.id,
                                  ),
                            )
                          }
                        />
                        <span>
                          {service.name}
                          <small>
                            {service.per_person ? t("perPerson") : t("total")}
                          </small>
                        </span>
                        <strong>{money(service.price, lang)}</strong>
                      </label>
                    ))}
                  </section>
                )}
                <section className="surface stack-form">
                  <h2>{t("cancellationPolicy")}</h2>
                  <CancellationPolicy policy={tour.cancellation_policy} />
                  <label className="checkbox-label">
                    <input
                      required
                      type="checkbox"
                      checked={form.accept_cancellation_policy}
                      onChange={(e) =>
                        update("accept_cancellation_policy", e.target.checked)
                      }
                    />
                    <span>{t("acceptPolicy")}</span>
                  </label>
                </section>
              </div>
              <aside className="checkout-summary surface">
                <Photo src={tour.image_url} alt={tour.title} />
                <span className="eyebrow">{tour.destination}</span>
                <h2>{tour.title}</h2>
                <p className="summary-date">
                  <CalendarDays size={16} />
                  {formatDate(departure.start_date, lang)} —{" "}
                  {formatDate(departure.end_date, lang)}
                </p>
                <div className="summary-line">
                  <span>
                    {money(departure.price, lang)} × {form.participants.length}
                  </span>
                  <strong>
                    {money(
                      Number(departure.price) * form.participants.length,
                      lang,
                    )}
                  </strong>
                </div>
                {(tour.services || [])
                  .filter((s) => form.service_ids.includes(s.id))
                  .map((s) => (
                    <div className="summary-line" key={s.id}>
                      <span>{s.name}</span>
                      <strong>
                        {money(
                          Number(s.price) *
                            (s.per_person ? form.participants.length : 1),
                          lang,
                        )}
                      </strong>
                    </div>
                  ))}
                <label>
                  {t("promoCode")}
                  <input
                    autoCapitalize="characters"
                    maxLength={40}
                    value={form.promo_code}
                    onChange={(e) =>
                      update("promo_code", e.target.value.toUpperCase())
                    }
                  />
                  <small>{t("promoHint")}</small>
                </label>
                {quote && Number(quote.discount_amount) > 0 && (
                  <div className="summary-line">
                    <span>{t("discount")}</span>
                    <strong>−{money(quote.discount_amount, lang)}</strong>
                  </div>
                )}
                <div className="booking-total">
                  <span>{t("total")}</span>
                  <strong>
                    {money(quote?.total_amount ?? estimate, lang)}
                  </strong>
                </div>
                {quote && (
                  <p className="success-message" role="status">
                    {t("quoteReady")}
                  </p>
                )}
                <FormError error={error} />
                <button className="button primary full-width" disabled={busy}>
                  {t(
                    busy ? "sending" : quote ? "reserveAndPay" : "reviewOrder",
                  )}
                  <ArrowRight size={18} />
                </button>
                <p className="payment-caption">
                  <ShieldCheck size={17} />
                  {t("reserveNote")}
                </p>
              </aside>
            </form>
          );
        }}
      </ResourceState>
    </div>
  );
}
