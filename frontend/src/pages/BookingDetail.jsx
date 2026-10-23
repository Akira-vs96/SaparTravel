import React, { useState } from "react";
import {
  ArrowLeft,
  CalendarDays,
  CheckCircle2,
  Download,
  UsersRound,
  Clock3,
  MessageCircle,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { api, download } from "../api";
import { useApp } from "../context";
import { formatDate, formatTime, money } from "../i18n";
import {
  FormError,
  Modal,
  PageHeading,
  Photo,
  ResourceState,
  useResource,
} from "../components/common";
import PaymentForm from "../components/PaymentForm";
import { BookingReview } from "../components/Reviews";
import { CheckoutSteps } from "./Checkout";
import CancellationPolicy, {
  refundPercent,
} from "../components/CancellationPolicy";
export default function BookingDetail({ management = false }) {
  const { id } = useParams();
  const { lang } = useApp();
  const resource = useResource(
    `${management ? "/manage" : ""}/bookings/${id}?lang=${lang}`,
    { auth: true },
  );
  return (
    <div className="page-container booking-detail">
      <ResourceState resource={resource}>
        {(booking) => (
          <Detail
            booking={booking}
            reload={resource.reload}
            management={management}
          />
        )}
      </ResourceState>
    </div>
  );
}
function Detail({ booking, reload, management }) {
  const { t, lang, token, notify, errorText } = useApp();
  const [cancelOpen, setCancelOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const cancel = async () => {
    setBusy(true);
    setError(null);
    try {
      await api(
        management
          ? `/manage/bookings/${booking.id}`
          : `/bookings/${booking.id}/cancel`,
        {
          token,
          method: management ? "PATCH" : "POST",
          body: management
            ? { status: "cancelled" }
            : { reason: "traveler_request" },
        },
      );
      setCancelOpen(false);
      reload();
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  };
  const doc = async (path, filename) => {
    try {
      await download(
        `/bookings/${booking.id}/${path}?lang=${lang}`,
        token,
        filename,
      );
    } catch (error) {
      notify(errorText(error));
    }
  };
  const paid = ["confirmed", "completed"].includes(booking.status);
  const unresolved = (booking.payments || []).some((p) =>
    ["unknown", "requires_action"].includes(p.status),
  );
  return (
    <>
      <Link to={management ? "/manage" : "/bookings"} className="back-link">
        <ArrowLeft size={16} />
        {t("bookings")}
      </Link>
      <PageHeading eyebrow={booking.reference} title={t("tripDetails")}>
        <span className={`status-badge ${booking.status}`}>
          {t(booking.status)}
        </span>
      </PageHeading>
      <CheckoutSteps active={paid ? 3 : booking.status === "pending" ? 2 : 1} />
      {paid && (
        <div className="confirmation-banner">
          <CheckCircle2 size={38} />
          <div>
            <h2>
              {t(
                Number(booking.paid_amount) > 0
                  ? "paymentSuccess"
                  : "confirmed",
              )}
            </h2>
            <p>
              {t(
                Number(booking.paid_amount) > 0
                  ? "paymentSuccessText"
                  : "legacyBookingText",
              )}
            </p>
          </div>
        </div>
      )}
      <div className="detail-layout">
        <div className="detail-main">
          <section className="surface detail-tour">
            <Photo
              src={booking.experience.image_url}
              alt={booking.experience.title}
            />
            <div>
              <span className="eyebrow">{booking.experience.destination}</span>
              <h2>
                <Link to={`/trips/${booking.experience.slug}`}>
                  {booking.experience.title}
                </Link>
              </h2>
              <p>
                <CalendarDays size={17} />
                {formatDate(booking.start_date, lang)} —{" "}
                {formatDate(booking.end_date, lang)}
              </p>
              <p>
                <UsersRound size={17} />
                {booking.travelers_count} {t("travelers").toLowerCase()}
              </p>
            </div>
          </section>
          {!management && (booking.status === "pending" || unresolved) && (
            <PaymentForm booking={booking} onChange={reload} />
          )}
          {booking.status === "expired" && (
            <div className="info-note">
              <h3>{t("expired")}</h3>
              <p>{t("reserveExpiredText")}</p>
              <Link
                to={`/trips/${booking.experience.slug}`}
                className="text-link"
              >
                {t("chooseDate")}
              </Link>
            </div>
          )}
          <section className="surface">
            <h2>{t("participants")}</h2>
            <div className="detail-participants">
              {(booking.participants || []).map((p, i) => (
                <div key={p.id || i}>
                  <span>{String(i + 1).padStart(2, "0")}</span>
                  <strong>{p.name}</strong>
                </div>
              ))}
            </div>
            <h3>{t("contacts")}</h3>
            <p>
              {booking.contact_name}
              <br />
              {booking.contact_email}
            </p>
            {booking.notes && <p className="muted">{booking.notes}</p>}
          </section>
          {booking.refunds?.length > 0 && (
            <section className="surface">
              <h2>{t("refunds")}</h2>
              {booking.refunds.map((refund) => (
                <div className="transaction-row" key={refund.id}>
                  <div>
                    <strong>
                      {money(refund.amount, lang, refund.currency)}
                    </strong>
                    <p>
                      {t(refund.reason) === refund.reason
                        ? refund.reason
                        : t(refund.reason)}
                    </p>
                    <small>
                      {refund.created_at && formatTime(refund.created_at, lang)}
                    </small>
                  </div>
                  <div className="button-row">
                    <span className={`status-badge ${refund.status}`}>
                      {t(
                        refund.status === "pending"
                          ? "processing"
                          : refund.status,
                      )}
                    </span>
                    {["failed", "pending", "processing"].includes(
                      refund.status,
                    ) && (
                      <button
                        className="button secondary small"
                        disabled={busy}
                        onClick={async () => {
                          setBusy(true);
                          try {
                            await api(`/refunds/${refund.id}/retry`, {
                              token,
                              method: "POST",
                            });
                            reload();
                          } catch (error) {
                            notify(errorText(error));
                          } finally {
                            setBusy(false);
                          }
                        }}
                      >
                        {t("retry")}
                      </button>
                    )}
                  </div>
                  {refund.history?.length > 0 && (
                    <details className="transaction-history">
                      <summary>{t("refundTimeline")}</summary>
                      <ol>
                        {refund.history.map((event, index) => (
                          <li key={index}>
                            <strong>
                              {t(
                                event.status === "pending"
                                  ? "processing"
                                  : event.status,
                              )}
                            </strong>
                            <span>{t(event.reason)}</span>
                            <small>{formatTime(event.created_at, lang)}</small>
                          </li>
                        ))}
                      </ol>
                    </details>
                  )}
                </div>
              ))}
            </section>
          )}
          <section className="surface">
            <h2>{t("history")}</h2>
            <ol className="booking-timeline">
              {(booking.history || []).map((event, i) => (
                <li key={event.id || i}>
                  <span className="timeline-dot" />
                  <div>
                    <strong>
                      {t(
                        event.status ||
                          event.to_status ||
                          event.event ||
                          event.action,
                      )}
                    </strong>
                    <p>
                      {event.reason && t(event.reason) !== event.reason
                        ? t(event.reason)
                        : event.reason || event.message}
                    </p>
                    <small>
                      {event.created_at && formatTime(event.created_at, lang)}{" "}
                      {event.actor_name
                        ? `· ${event.actor_name}`
                        : event.actor_id
                          ? ` · ${t("actor")}: ${event.actor_id.slice(0, 8)}`
                          : ""}
                    </small>
                  </div>
                </li>
              ))}
            </ol>
          </section>
          {booking.payments?.length > 0 && (
            <section className="surface">
              <h2>{t("paymentHistory")}</h2>
              {booking.payments.map((payment) => (
                <div className="transaction-row" key={payment.id}>
                  <div>
                    <strong>
                      {money(payment.amount, lang, payment.currency)}
                    </strong>
                    <p>{payment.masked_card}</p>
                    <small>
                      {payment.created_at &&
                        formatTime(payment.created_at, lang)}
                    </small>
                  </div>
                  <span className={`status-badge ${payment.status}`}>
                    {t(payment.status)}
                  </span>
                  {payment.history?.length > 0 && (
                    <details className="transaction-history">
                      <summary>{t("paymentTimeline")}</summary>
                      <ol>
                        {payment.history.map((event, index) => (
                          <li key={index}>
                            <strong>
                              {t(
                                event.status === "pending"
                                  ? "processing"
                                  : event.status,
                              )}
                            </strong>
                            <span>{t(event.reason)}</span>
                            <small>{formatTime(event.created_at, lang)}</small>
                          </li>
                        ))}
                      </ol>
                    </details>
                  )}
                </div>
              ))}
            </section>
          )}
          {!management && booking.status === "completed" && (
            <section className="surface">
              <BookingReview bookingId={booking.id} />
            </section>
          )}
        </div>
        <aside className="surface detail-summary">
          <p className="eyebrow">{t("reference")}</p>
          <h2>{booking.reference}</h2>
          {booking.items?.map((item, i) => (
            <div className="summary-line" key={item.id || i}>
              <span>
                {item.name || item.title || t("tripDetails")}
                {item.quantity > 1 ? ` × ${item.quantity}` : ""}
              </span>
              <strong>
                {money(
                  item.total_amount ??
                    item.total ??
                    Number(item.unit_amount || 0) * Number(item.quantity || 1),
                  lang,
                  item.currency || booking.currency,
                )}
              </strong>
            </div>
          ))}
          {Number(booking.discount_amount) > 0 && (
            <div className="summary-line">
              <span>{t("discount")}</span>
              <strong>
                −{money(booking.discount_amount, lang, booking.currency)}
              </strong>
            </div>
          )}
          <div className="booking-total">
            <span>{t("total")}</span>
            <strong>
              {money(booking.total_amount, lang, booking.currency)}
            </strong>
          </div>
          {booking.currency_conversion && (
            <p className="info-note">
              {t("historicalEquivalent")}:{" "}
              <strong>
                {money(booking.currency_conversion.equivalent_amount, lang)}
              </strong>
              <br />
              {t("educationalFactor")} {booking.currency_conversion.factor}.{" "}
              {t("historicalOriginal")}:{" "}
              {money(
                booking.currency_conversion.original_amount,
                lang,
                booking.currency_conversion.original_currency,
              )}
            </p>
          )}
          {booking.expires_at && booking.status === "pending" && (
            <p className="reserve-timer">
              <Clock3 size={16} />
              {t("reservationUntil")} {formatTime(booking.expires_at, lang)}
            </p>
          )}
          {!management && (
            <div className="document-actions">
              <button
                disabled={!paid}
                className="button secondary"
                onClick={() => doc("confirmation", `${booking.reference}.html`)}
              >
                <Download size={16} />
                {t("downloadConfirmation")}
              </button>
              <button
                disabled={!paid}
                className="button secondary"
                onClick={() => doc("calendar.ics", `${booking.reference}.ics`)}
              >
                <CalendarDays size={16} />
                {t("addCalendar")}
              </button>
              <Link
                className="button secondary"
                to={`/support?booking=${booking.id}`}
              >
                <MessageCircle size={16} />
                {t("support")}
              </Link>
            </div>
          )}
          {!paid && !management && (
            <p className="muted">{t("documentsAfterConfirmation")}</p>
          )}
          <details className="policy-details">
            <summary>{t("cancellationPolicy")}</summary>
            <CancellationPolicy policy={booking.cancellation_policy} />
          </details>
          {["pending", "confirmed"].includes(booking.status) && (
            <button
              className="text-button danger-text"
              onClick={() => setCancelOpen(true)}
            >
              {t("cancelBooking")}
            </button>
          )}
        </aside>
      </div>
      {cancelOpen && (
        <Modal
          title={t("cancelQuestion")}
          onClose={() => !busy && setCancelOpen(false)}
        >
          <p>{booking.experience.title}</p>
          <CancellationPolicy policy={booking.cancellation_policy} />
          <p className="info-note">
            {t("estimatedRefund")}:{" "}
            {money(
              (Number(booking.paid_amount || 0) * refundPercent(booking)) / 100,
              lang,
              booking.currency,
            )}
          </p>
          <p>{t("refundNotice")}</p>
          <FormError error={error} />
          <div className="modal-actions">
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => setCancelOpen(false)}
            >
              {t("keepBooking")}
            </button>
            <button className="button danger" disabled={busy} onClick={cancel}>
              {t(busy ? "sending" : "cancelBooking")}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
