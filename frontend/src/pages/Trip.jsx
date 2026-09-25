import React, { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  Check,
  CheckCircle2,
  Clock3,
  MapPin,
  ShieldCheck,
  Star,
  X,
} from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useApp } from "../context";
import { formatDate, money } from "../i18n";
import {
  FormError,
  Modal,
  Photo,
  ResourceState,
  SaveButton,
  useResource,
} from "../components/common";

export default function Trip() {
  const { slug } = useParams();
  const { lang } = useApp();
  const resource = useResource(`/experiences/${slug}?lang=${lang}`);
  return (
    <div className="page-container trip-page">
      <ResourceState resource={resource}>
        {(tour) => (
          <TripContent key={tour.id} tour={tour} reload={resource.reload} />
        )}
      </ResourceState>
    </div>
  );
}

function TripContent({ tour, reload }) {
  const { lang, t, user } = useApp();
  const navigate = useNavigate();
  const [dateId, setDateId] = useState("");
  const [travelers, setTravelers] = useState(1);
  const [bookingOpen, setBookingOpen] = useState(false);
  const today = new Date().toISOString().slice(0, 10);
  const departures = tour.departures.filter((item) => item.start_date >= today);
  const selected =
    departures.find((item) => item.id === dateId) ||
    departures.find((item) => item.available_seats > 0);
  useEffect(() => {
    if (selected)
      setTravelers((value) =>
        Math.max(1, Math.min(value, selected.available_seats, 20)),
      );
  }, [selected?.id, selected?.available_seats]);
  const book = (event) => {
    event.preventDefault();
    if (!user)
      return navigate(
        `/login?next=${encodeURIComponent(`/trips/${tour.slug}`)}`,
      );
    setBookingOpen(true);
  };
  return (
    <>
      <Link className="back-link" to="/explore">
        <ArrowLeft size={16} />
        {t("backCatalog")}
      </Link>
      <div className="trip-heading">
        <div>
          <p className="eyebrow">
            <MapPin size={14} />
            {tour.destination} · {t(tour.continent)}
          </p>
          <h1>{tour.title}</h1>
          <div className="trip-meta">
            <span>
              <Clock3 size={16} />
              {tour.duration_days} {t("days")}
            </span>
            <span>{t(tour.category)}</span>
            <span>
              <Star size={15} />
              {tour.review_count > 0
                ? `${tour.rating} (${tour.review_count})`
                : t("newTrip")}
            </span>
          </div>
        </div>
        <SaveButton tour={tour} className="large-save" />
      </div>
      <div className="trip-cover">
        <Photo src={tour.image_url} alt={tour.title} loading="eager" />
      </div>
      <div className="trip-layout">
        <div className="trip-content">
          <section>
            <p className="eyebrow">
              {t("hostedBy")} · {tour.vendor.name}
            </p>
            <h2>{t("overview")}</h2>
            <p className="trip-description">{tour.description}</p>
            <div className="tags">
              {tour.tags?.map((tag, index) => (
                <span key={`${tag}-${index}`}>{tag}</span>
              ))}
            </div>
          </section>
          <section>
            <h2>{t("itinerary")}</h2>
            <div className="itinerary">
              {tour.itinerary.map((item, index) => (
                <article key={`${item.day}-${index}`}>
                  <div className="day-number">
                    {String(item.day).padStart(2, "0")}
                  </div>
                  <div>
                    <span className="eyebrow">
                      {t("day")} {item.day}
                    </span>
                    <h3>{item.title}</h3>
                    <p>{item.description}</p>
                  </div>
                </article>
              ))}
            </div>
          </section>
          <section className="inclusions">
            <div>
              <h3>{t("included")}</h3>
              <ul>
                {tour.included.map((item, index) => (
                  <li key={index}>
                    <Check size={17} />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3>{t("excluded")}</h3>
              <ul>
                {tour.excluded.map((item, index) => (
                  <li key={index}>
                    <X size={16} />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </section>
          <p className="demo-notice">{t("demo")}</p>
        </div>
        <aside className="booking-sidebar">
          <form className="booking-panel" onSubmit={book}>
            <div className="booking-price">
              <span>{t("from")}</span>
              <strong>{money(selected?.price ?? tour.price_from, lang)}</strong>
              <span>{t("perPerson")}</span>
            </div>
            <div className="booking-divider" />
            {selected ? (
              <>
                <label>
                  {t("chooseDate")}
                  <select
                    value={selected.id}
                    onChange={(event) => setDateId(event.target.value)}
                  >
                    {departures.map((departure) => (
                      <option
                        value={departure.id}
                        key={departure.id}
                        disabled={departure.available_seats < 1}
                      >
                        {formatDate(departure.start_date, lang)} —{" "}
                        {departure.available_seats} {t("seats")}
                      </option>
                    ))}
                  </select>
                </label>
                <p className="date-range">
                  <CalendarDays size={15} />
                  {formatDate(selected.start_date, lang)} —{" "}
                  {formatDate(selected.end_date, lang)}
                </p>
                <label>
                  {t("travelers")}
                  <input
                    type="number"
                    required
                    min="1"
                    max={Math.min(selected.available_seats, 20)}
                    step="1"
                    value={travelers}
                    onChange={(event) =>
                      setTravelers(
                        event.target.value === ""
                          ? ""
                          : Number(event.target.value),
                      )
                    }
                  />
                </label>
                <div className="booking-total">
                  <span>{t("total")}</span>
                  <strong>
                    {money(selected.price * Number(travelers), lang)}
                  </strong>
                </div>
                <button className="button primary full-width" type="submit">
                  {t(user ? "book" : "loginToBook")}
                  <ArrowRight size={17} />
                </button>
              </>
            ) : (
              <div className="no-dates">
                <CalendarDays size={29} />
                <h3>{t("noDates")}</h3>
                <p>{t("noDatesText")}</p>
              </div>
            )}
            <p className="payment-caption">
              <ShieldCheck size={18} />
              {t("noPayment")}
            </p>
          </form>
          <p className="sidebar-note">{t("paymentNote")}</p>
        </aside>
      </div>
      {bookingOpen && selected && (
        <BookingModal
          tour={tour}
          departure={selected}
          travelers={Number(travelers)}
          onClose={() => setBookingOpen(false)}
          reload={reload}
        />
      )}
    </>
  );
}
function BookingModal({ tour, departure, travelers, onClose, reload }) {
  const { user, token, lang, t } = useApp();
  const [name, setName] = useState(user.name);
  const [email, setEmail] = useState(user.email);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [booking, setBooking] = useState(null);
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api("/bookings", {
        token,
        method: "POST",
        body: {
          departure_id: departure.id,
          travelers_count: travelers,
          contact_name: name,
          contact_email: email,
          notes,
        },
      });
      setBooking(result);
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title={t(booking ? "bookingSuccess" : "bookingIntro")}
      onClose={() => {
        if (!busy) {
          onClose();
          if (booking) reload();
        }
      }}
    >
      {booking ? (
        <div className="booking-success">
          <CheckCircle2 size={58} />
          <p>{t("bookingSuccessText")}</p>
          <div className="reference-box">
            <small>{t("reference")}</small>
            <strong>{booking.reference}</strong>
          </div>
          <Link to="/bookings" className="button primary full-width">
            {t("bookings")}
            <ArrowRight size={17} />
          </Link>
        </div>
      ) : (
        <form onSubmit={submit} className="stack-form">
          <div className="booking-summary">
            <Photo src={tour.image_url} alt="" />
            <div>
              <strong>{tour.title}</strong>
              <p>
                {formatDate(departure.start_date, lang)} · {travelers}{" "}
                {t("travelers").toLowerCase()}
              </p>
            </div>
          </div>
          <label>
            {t("contactName")}
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              minLength="2"
              maxLength="120"
              autoComplete="name"
            />
          </label>
          <label>
            {t("contactEmail")}
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              autoComplete="email"
            />
          </label>
          <label>
            {t("notes")} <span className="muted">({t("optional")})</span>
            <textarea
              rows="3"
              maxLength="2000"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
            />
          </label>
          <p className="info-note">{t("paymentNote")}</p>
          <div className="booking-total">
            <span>{t("total")}</span>
            <strong>{money(departure.price * travelers, lang)}</strong>
          </div>
          <FormError error={error} />
          <button className="button primary full-width" disabled={busy}>
            {t(busy ? "sending" : "confirmBooking")}
            <ArrowRight size={17} />
          </button>
        </form>
      )}
    </Modal>
  );
}
