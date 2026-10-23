import React, { useState } from "react";
import { Star, ShieldCheck } from "lucide-react";
import { api } from "../api";
import { useApp } from "../context";
import { formatDate } from "../i18n";
import { FormError, ResourceState, useResource } from "./common";
export default function Reviews({ experienceId }) {
  const { t, lang } = useApp();
  const resource = useResource(`/experiences/${experienceId}/reviews`);
  return (
    <section id="reviews">
      <h2>{t("reviews")}</h2>
      <ResourceState resource={resource}>
        {(data) =>
          data.items.length ? (
            <div className="review-list">
              {data.items.map((review) => (
                <article className="review-card" key={review.id}>
                  <div className="review-top">
                    <strong>
                      {review.author_name || review.user_name || t("traveler")}
                    </strong>
                    <span
                      className="review-stars"
                      aria-label={`${review.rating}/5`}
                    >
                      {Array.from({ length: 5 }, (_, i) => (
                        <Star
                          key={i}
                          size={14}
                          fill={i < review.rating ? "currentColor" : "none"}
                        />
                      ))}
                    </span>
                  </div>
                  <h3>{review.title}</h3>
                  <p>{review.text}</p>
                  <small>
                    <ShieldCheck size={13} />
                    {t("verifiedTrip")} · {formatDate(review.created_at, lang)}
                  </small>
                </article>
              ))}
            </div>
          ) : (
            <p className="muted">{t("reviewEmpty")}</p>
          )
        }
      </ResourceState>
    </section>
  );
}
export function ReviewForm({ bookingId, onSaved }) {
  const { t, token, notify } = useApp();
  const [form, setForm] = useState({ rating: 5, title: "", text: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  if (sent)
    return (
      <p className="success-message" role="status">
        {t("reviewSent")}
      </p>
    );
  return (
    <form
      className="stack-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
          await api("/reviews", {
            token,
            method: "POST",
            body: { booking_id: bookingId, ...form },
          });
          setSent(true);
          notify(t("reviewSent"));
          onSaved?.();
        } catch (error) {
          setError(error);
        } finally {
          setBusy(false);
        }
      }}
    >
      <h2>{t("reviewTitle")}</h2>
      <label>
        {t("rating")}
        <select
          value={form.rating}
          onChange={(e) => setForm({ ...form, rating: Number(e.target.value) })}
        >
          {[5, 4, 3, 2, 1].map((n) => (
            <option key={n} value={n}>
              {n} / 5
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("title")}
        <input
          required
          minLength={3}
          maxLength={180}
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
        />
      </label>
      <label>
        {t("message")}
        <textarea
          required
          minLength={10}
          maxLength={5000}
          rows={4}
          value={form.text}
          onChange={(e) => setForm({ ...form, text: e.target.value })}
        />
      </label>
      <FormError error={error} />
      <button disabled={busy} className="button primary">
        {t(busy ? "sending" : "leaveReview")}
      </button>
    </form>
  );
}
export function BookingReview({ bookingId }) {
  const { t } = useApp();
  const resource = useResource("/reviews/mine", { auth: true });
  const [editing, setEditing] = useState(false);
  return (
    <ResourceState resource={resource}>
      {(data) => {
        const review = data.items.find((item) => item.booking_id === bookingId);
        if (review)
          return (
            <div className="review-card">
              <span className={`status-badge ${review.status}`}>
                {t(
                  review.status === "pending" ? "reviewPending" : review.status,
                )}
              </span>
              <h3>
                {review.title} · {review.rating}/5
              </h3>
              <p>{review.text}</p>
            </div>
          );
        return editing ? (
          <ReviewForm bookingId={bookingId} onSaved={resource.reload} />
        ) : (
          <button className="button secondary" onClick={() => setEditing(true)}>
            {t("leaveReview")}
          </button>
        );
      }}
    </ResourceState>
  );
}
