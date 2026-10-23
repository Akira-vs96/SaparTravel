import React from "react";
import {
  ArrowUpRight,
  Clock3,
  MapPin,
  Star,
  GitCompareArrows,
} from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { useApp } from "../context";
import { money } from "../i18n";
import { Photo, SaveButton } from "./common";

export default function TourCard({ tour }) {
  const { lang, t, comparison, toggleCompare } = useApp();
  const compared = comparison.some((item) => item.id === tour.id);
  const location = useLocation();
  const href = `/trips/${tour.slug}${location.pathname === "/explore" && location.search ? `?from=${encodeURIComponent(location.search.slice(1))}` : tour.recommended_departure ? `?departure=${encodeURIComponent(tour.recommended_departure.id)}&travelers=${new URLSearchParams(location.search).get("travelers") || "1"}` : ""}`;
  return (
    <article className="tour-card">
      <div className="tour-card-image">
        <Link to={href} aria-label={tour.title}>
          <Photo src={tour.image_url} alt={tour.title} />
        </Link>
        <span className="image-label">{t(tour.category)}</span>
        <SaveButton tour={tour} />
        <button
          className={`compare-card-button ${compared ? "selected" : ""}`}
          onClick={() => toggleCompare(tour)}
          aria-label={t(compared ? "compareRemove" : "compareAdd")}
          aria-pressed={compared}
          title={t("compare")}
        >
          <GitCompareArrows size={17} />
        </button>
      </div>
      <div className="tour-card-body">
        <div className="tour-location">
          <MapPin size={13} />
          <span>{tour.destination || tour.country}</span>
          <span className="tour-rating">
            {tour.review_count > 0 ? (
              <>
                <Star size={12} fill="currentColor" /> {tour.rating}{" "}
                <small>({tour.review_count})</small>
              </>
            ) : (
              t("newTrip")
            )}
          </span>
        </div>
        <h3>
          <Link to={href}>{tour.title}</Link>
        </h3>
        <p className="tour-duration">
          <Clock3 size={14} />
          {tour.duration_days} {t("days")}
        </p>
        <div className="tour-card-footer">
          <span>
            <small>{t("from")} </small>
            <strong>{money(tour.price_from, lang)}</strong>
            <small> / {t("perPerson")}</small>
          </span>
          <Link
            to={href}
            className="round-link"
            aria-label={`${t("details")}: ${tour.title}`}
          >
            <ArrowUpRight size={19} />
          </Link>
        </div>
      </div>
    </article>
  );
}
