import React, { useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  Compass,
  Mountain,
  Search,
  ShieldCheck,
  UsersRound,
  Utensils,
  Waves,
  Building2,
  Landmark,
  Globe2,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useApp } from "../context";
import { CATEGORIES } from "../i18n";
import { Photo, ResourceState, useResource } from "../components/common";
import TourCard from "../components/TourCard";

const categoryIcons = [Mountain, Landmark, Compass, Utensils, Waves, Building2];
export default function Home() {
  const { lang, t } = useApp();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [date, setDate] = useState("");
  const [travelers, setTravelers] = useState(1);
  const tours = useResource(
    `/experiences?lang=${lang}&page_size=6&sort=recommended`,
  );
  const destinations = useResource(`/destinations?lang=${lang}`);
  return (
    <>
      <section className="journey-hero">
        <Photo
          src="https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?auto=format&fit=crop&w=2000&q=90"
          alt={t("heroLocation")}
          loading="eager"
          fetchPriority="high"
        />
        <div className="journey-overlay" />
        <div className="journey-content">
          <p className="hero-eyebrow">
            <span /> {t("journeyLabel")}
          </p>
          <h1>
            {t("journeyTitle")}
            <br />
            <em>{t("journeyAccent")}</em>
          </h1>
          <p>{t("journeyText")}</p>
          <Link to="/explore" className="button primary">
            {t("findTrip")} <ArrowUpRight size={19} />
          </Link>
        </div>
        <div className="hero-location">
          <MapPinIcon />{" "}
          <span>
            {t("heroLocation")}
            <small>{t("demoShort")}</small>
          </span>
        </div>
        <div className="hero-index">
          <span>01</span> / 24
        </div>
      </section>
      <div className="journey-search-wrap">
        <form
          className="journey-search"
          onSubmit={(event) => {
            event.preventDefault();
            const search = new URLSearchParams({
              travelers: String(travelers),
            });
            if (query) search.set("q", query);
            if (date) search.set("date_from", date);
            navigate(`/explore?${search}`);
          }}
        >
          <label>
            <span>
              <Search size={17} /> {t("where")}
            </span>
            <input
              aria-label={t("destinationLabel")}
              placeholder={t("searchPlaceholder")}
              maxLength={100}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <label>
            <span>
              <CalendarDays size={17} /> {t("dateFrom")}
            </span>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              aria-label={t("dateFrom")}
            />
          </label>
          <label>
            <span>
              <UsersRound size={17} /> {t("travelers")}
            </span>
            <select
              value={travelers}
              onChange={(e) => setTravelers(Number(e.target.value))}
            >
              {[1, 2, 3, 4, 5, 6, 8, 10].map((n) => (
                <option key={n} value={n}>
                  {n} {t("travelers").toLowerCase()}
                </option>
              ))}
            </select>
          </label>
          <button className="button dark">
            <Search size={18} />
            {t("search")}
          </button>
        </form>
      </div>
      <section className="section category-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">SAPAR / {t("category")}</p>
            <h2>{t("travelYourWay")}</h2>
          </div>
          <Link className="text-link" to="/explore">
            {t("viewAll")} <ArrowUpRight size={18} />
          </Link>
        </div>
        <div className="category-grid">
          {CATEGORIES.map((category, index) => {
            const Icon = categoryIcons[index];
            return (
              <Link key={category} to={`/explore?category=${category}`}>
                <span className="category-icon">
                  <Icon size={26} strokeWidth={1.5} />
                </span>
                <span>{t(category)}</span>
                <ArrowUpRight size={16} />
              </Link>
            );
          })}
        </div>
      </section>
      <section className="section home-trips">
        <div className="section-heading">
          <div>
            <p className="eyebrow">{t("curatedLabel")}</p>
            <h2>{t("handpicked")}</h2>
            <p>{t("handpickedText")}</p>
          </div>
          <Link to="/explore" className="text-link">
            {t("viewAll")} <ArrowRight size={17} />
          </Link>
        </div>
        <ResourceState resource={tours}>
          {(data) => (
            <div className="tour-grid">
              {data.items.map((tour) => (
                <TourCard tour={tour} key={tour.id} />
              ))}
            </div>
          )}
        </ResourceState>
      </section>
      <section className="section destinations-section" id="destinations">
        <div className="section-heading">
          <div>
            <p className="eyebrow">{t("continentsLabel")}</p>
            <h2>{t("worldTitle")}</h2>
          </div>
          <Link className="text-link" to="/explore">
            {t("viewAll")} <ArrowRight size={17} />
          </Link>
        </div>
        <ResourceState resource={destinations}>
          {(data) => (
            <div className="destination-grid">
              {data.items
                .filter((item) => item.tour_count > 0)
                .slice(0, 4)
                .map((destination) => (
                  <Link
                    className="destination-card"
                    to={`/explore?destination=${destination.slug}`}
                    key={destination.id}
                  >
                    <Photo src={destination.image_url} alt={destination.name} />
                    <div>
                      <span>{t(destination.continent)}</span>
                      <h3>{destination.name}</h3>
                      <p>
                        {destination.tour_count} {t("results")}
                      </p>
                    </div>
                    <ArrowUpRight size={23} />
                  </Link>
                ))}
            </div>
          )}
        </ResourceState>
      </section>
      <section className="section recommendation-teaser">
        <div>
          <p className="eyebrow">{t("yourPace")}</p>
          <h2>{t("recommendations")}</h2>
          <p>{t("recommendationsText")}</p>
        </div>
        <Link
          className="button dark"
          to="/recommendations?budget=500000&duration_max=7&travelers=1"
        >
          {t("findMatch")}
          <ArrowUpRight size={19} />
        </Link>
      </section>
      <section className="how-section">
        <div className="how-intro">
          <span className="tiny-star">✳</span>
          <h2>{t("howTitle")}</h2>
          <Link className="text-link" to="/about">
            {t("learnMore")} <ArrowUpRight size={17} />
          </Link>
        </div>
        <div className="how-steps">
          {[Compass, ShieldCheck, Globe2].map((Icon, index) => (
            <div key={index}>
              <div className="step-top">
                <Icon size={25} />
                <span>0{index + 1}</span>
              </div>
              <h3>{t(`step${index + 1}`)}</h3>
              <p>{t(`step${index + 1}Text`)}</p>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
function MapPinIcon() {
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
    >
      <path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z" />
      <circle cx="12" cy="10" r="2.5" />
    </svg>
  );
}
