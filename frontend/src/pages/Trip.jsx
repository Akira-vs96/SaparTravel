import React, { useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  Check,
  Clock3,
  MapPin,
  ShieldCheck,
  Star,
  X,
  GitCompareArrows,
  Images,
} from "lucide-react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { useApp } from "../context";
import { formatDate, money } from "../i18n";
import {
  Modal,
  Photo,
  ResourceState,
  SaveButton,
  useResource,
} from "../components/common";
import Reviews from "../components/Reviews";
import CancellationPolicy from "../components/CancellationPolicy";
export default function Trip() {
  const { slug } = useParams();
  const { lang } = useApp();
  const resource = useResource(`/experiences/${slug}?lang=${lang}`);
  return (
    <div className="page-container trip-page">
      <ResourceState resource={resource}>
        {(tour) => <TripContent key={tour.id} tour={tour} />}
      </ResourceState>
    </div>
  );
}
function TripContent({ tour }) {
  const { lang, t, user, comparison, toggleCompare } = useApp();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [dateId, setDateId] = useState(params.get("departure") || "");
  const [travelers, setTravelers] = useState(
    Number(params.get("travelers") || tour.min_participants || 1),
  );
  const [gallery, setGallery] = useState(null);
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Almaty",
  }).format(new Date());
  const departures = tour.departures.filter(
    (item) => item.start_date >= today && item.status !== "cancelled",
  );
  const selected =
    departures.find((item) => item.id === dateId) ||
    departures.find((item) => item.available_seats > 0);
  const pictures = [
    ...new Set(
      [
        tour.image_url,
        ...(tour.gallery || []).map((image) =>
          typeof image === "string" ? image : image.url || image.image_url,
        ),
      ].filter(Boolean),
    ),
  ];
  const maxTravelers = Math.min(
    selected?.available_seats || 0,
    tour.max_participants || 20,
  );
  const compared = comparison.some((item) => item.id === tour.id);
  const book = (e) => {
    e.preventDefault();
    const next = `/checkout/${tour.slug}?departure=${selected.id}&travelers=${travelers}`;
    navigate(user ? next : `/login?next=${encodeURIComponent(next)}`);
  };
  return (
    <>
      <Link
        className="back-link"
        to={params.get("from") ? `/explore?${params.get("from")}` : "/explore"}
      >
        <ArrowLeft size={16} />
        {t("backCatalog")}
      </Link>
      <div className="trip-heading">
        <div>
          <p className="eyebrow">
            <MapPin size={14} />
            {tour.destination} · {t(tour.category)}
          </p>
          <h1>{tour.title}</h1>
          <div className="trip-meta">
            <span>
              <Clock3 size={16} />
              {tour.duration_days} {t("days")}
            </span>
            <a href="#reviews">
              <Star size={15} />
              {tour.review_count > 0
                ? `${tour.rating} (${tour.review_count})`
                : t("newTrip")}
            </a>
            <span>
              {t("hostedBy")} {tour.vendor.name}
            </span>
          </div>
        </div>
        <div className="trip-heading-actions">
          <button
            className={`icon-button ${compared ? "selected" : ""}`}
            onClick={() => toggleCompare(tour)}
            aria-label={t(compared ? "compareRemove" : "compareAdd")}
            aria-pressed={compared}
          >
            <GitCompareArrows size={21} />
          </button>
          <SaveButton tour={tour} className="large-save" />
        </div>
      </div>
      <div
        className={`trip-gallery ${pictures.length > 1 ? "has-gallery" : ""}`}
      >
        <button
          className="gallery-main"
          onClick={() => setGallery(0)}
          aria-label={t("gallery")}
        >
          <Photo src={pictures[0]} alt={tour.title} loading="eager" />
          <span>
            <Images size={17} />
            {t("gallery")} · {pictures.length}
          </span>
        </button>
        {pictures.length > 1 && (
          <div className="gallery-thumbnails">
            {pictures.slice(1, 3).map((src, index) => (
              <button
                key={src}
                onClick={() => setGallery(index + 1)}
                aria-label={`${t("gallery")} ${index + 2}`}
              >
                <Photo src={src} alt={`${tour.title} ${index + 2}`} />
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="trip-layout">
        <div className="trip-content">
          <nav className="trip-section-nav">
            <a href="#overview">{t("overview")}</a>
            <a href="#itinerary">{t("itinerary")}</a>
            <a href="#included">{t("included")}</a>
            <a href="#reviews">{t("reviews")}</a>
          </nav>
          <section id="overview">
            <p className="eyebrow">
              {t("hostedBy")} · {tour.vendor.name}
            </p>
            <h2>{t("overview")}</h2>
            <p className="trip-description">{tour.description}</p>
            <div className="tags">
              {tour.tags?.map((tag, i) => (
                <span key={i}>{tag}</span>
              ))}
            </div>
          </section>
          <section id="itinerary">
            <h2>{t("itinerary")}</h2>
            <div className="itinerary">
              {tour.itinerary.map((item, index) => (
                <article key={index}>
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
          <section className="inclusions" id="included">
            <div>
              <h3>{t("included")}</h3>
              <ul>
                {tour.included.map((item, i) => (
                  <li key={i}>
                    <Check size={17} />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3>{t("excluded")}</h3>
              <ul>
                {tour.excluded.map((item, i) => (
                  <li key={i}>
                    <X size={16} />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </section>
          {tour.services?.length > 0 && (
            <section>
              <h2>{t("additionalServices")}</h2>
              <div className="service-list">
                {tour.services.map((service) => (
                  <div key={service.id}>
                    <span>{service.name}</span>
                    <strong>
                      {money(service.price, lang)}
                      {service.per_person ? ` / ${t("perPerson")}` : ""}
                    </strong>
                  </div>
                ))}
              </div>
            </section>
          )}
          <section>
            <h2>{t("restrictions")}</h2>
            <p>
              {t("travelers")}: {tour.min_participants || 1}–
              {tour.max_participants || 20}
            </p>
            {tour.restrictions && <p>{tour.restrictions}</p>}
            <h3 className="policy-heading">{t("cancellationPolicy")}</h3>
            <CancellationPolicy policy={tour.cancellation_policy} />
          </section>
          <Reviews experienceId={tour.id} />
        </div>
        <aside className="booking-sidebar">
          <form className="booking-panel" onSubmit={book}>
            <div className="booking-price">
              <span>{t("from")}</span>
              <strong>{money(tour.price_from, lang)}</strong>
              <span>{t("perPerson")}</span>
            </div>
            <div className="booking-divider" />
            {selected ? (
              <>
                <label>
                  {t("chooseDate")}
                  <select
                    value={selected.id}
                    onChange={(e) => {
                      setDateId(e.target.value);
                      setTravelers(Number(tour.min_participants || 1));
                    }}
                  >
                    {departures.map((departure) => (
                      <option
                        value={departure.id}
                        key={departure.id}
                        disabled={departure.available_seats < 1}
                      >
                        {formatDate(departure.start_date, lang)} ·{" "}
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
                    min={tour.min_participants || 1}
                    max={maxTravelers}
                    value={travelers}
                    onChange={(e) =>
                      setTravelers(
                        e.target.value === "" ? "" : Number(e.target.value),
                      )
                    }
                  />
                </label>
                <div className="booking-total">
                  <span>
                    {money(selected.price, lang)} × {travelers}
                  </span>
                  <strong>
                    {money(Number(selected.price) * Number(travelers), lang)}
                  </strong>
                </div>
                <button className="button primary full-width">
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
          <p className="sidebar-note">{t("reserveNote")}</p>
        </aside>
      </div>
      {gallery !== null && (
        <Modal title={tour.title} onClose={() => setGallery(null)}>
          <div className="gallery-dialog">
            <Photo
              src={pictures[gallery]}
              alt={`${tour.title} ${gallery + 1}`}
              loading="eager"
            />
            <div className="gallery-controls">
              <button
                className="button secondary"
                disabled={gallery === 0}
                onClick={() => setGallery(gallery - 1)}
                aria-label={t("previous")}
              >
                <ArrowLeft size={18} />
              </button>
              <span>
                {gallery + 1} / {pictures.length}
              </span>
              <button
                className="button secondary"
                disabled={gallery === pictures.length - 1}
                onClick={() => setGallery(gallery + 1)}
                aria-label={t("next")}
              >
                <ArrowRight size={18} />
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
