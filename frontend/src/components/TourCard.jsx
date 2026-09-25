import React from "react";
import { ArrowUpRight, Clock3, MapPin, Star } from "lucide-react";
import { Link } from "react-router-dom";
import { useApp } from "../context";
import { money } from "../i18n";
import { Photo, SaveButton } from "./common";

export default function TourCard({ tour }) {
  const { lang, t } = useApp();
  return (
    <article className="tour-card">
      <div className="tour-card-image">
        <Link to={`/trips/${tour.slug}`} aria-label={tour.title}>
          <Photo src={tour.image_url} alt={tour.title} />
        </Link>
        <span className="image-label">{t(tour.category)}</span>
        <SaveButton tour={tour} />
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
          <Link to={`/trips/${tour.slug}`}>{tour.title}</Link>
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
            to={`/trips/${tour.slug}`}
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
