import React, { useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  Compass,
  Globe2,
  Search,
  Send,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useApp } from "../context";
import { CONTINENTS } from "../i18n";
import { Photo, ResourceState, useResource } from "../components/common";
import TourCard from "../components/TourCard";

export default function Home() {
  const { lang, t } = useApp();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const tours = useResource(
    `/experiences?lang=${lang}&page_size=6&sort=recommended`,
  );
  const destinations = useResource(`/destinations?lang=${lang}`);
  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">
            <span className="tiny-star">✳</span> {t("heroLabel")}
          </p>
          <h1>
            {t("heroTitle")}
            <br />
            <em>{t("heroAccent")}</em>
          </h1>
          <p className="hero-description">{t("heroText")}</p>
          <Link className="button primary" to="/explore">
            {t("findTrip")} <ArrowUpRight size={19} />
          </Link>
          <div className="hero-footnote">
            <Globe2 size={19} />
            <span>{t("continentsLabel")}</span>
          </div>
        </div>
        <div className="hero-visual">
          <Photo
            src="https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?auto=format&fit=crop&w=1600&q=85"
            alt={t("heroLocation")}
            loading="eager"
            fetchPriority="high"
          />
          <div className="hero-photo-caption">
            <Globe2 size={17} /> {t("heroLocation")}
            <span>{t("heroPhotoNote")}</span>
          </div>
          <div className="hero-stamp">
            <Compass size={32} strokeWidth={1.2} />
            <span>
              {t("stampExplore")}
              <br />
              {t("stampWorld")}
            </span>
          </div>
        </div>
      </section>
      <div className="home-search-wrap">
        <form
          className="home-search"
          onSubmit={(event) => {
            event.preventDefault();
            navigate(`/explore?q=${encodeURIComponent(query)}`);
          }}
        >
          <Search size={24} />
          <label>
            <span>{t("where")}</span>
            <input
              maxLength="100"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t("searchPlaceholder")}
            />
          </label>
          <button className="button dark">
            {t("search")} <ArrowRight size={18} />
          </button>
        </form>
      </div>
      <section className="section destinations-section" id="destinations">
        <div className="section-heading">
          <div>
            <p className="eyebrow">{t("continentsLabel")}</p>
            <h2>{t("worldTitle")}</h2>
          </div>
          <Link to="/explore" className="text-link">
            {t("viewAll")} <ArrowRight size={17} />
          </Link>
        </div>
        <div className="continent-links">
          {CONTINENTS.map((continent) => (
            <Link
              key={continent}
              to={`/explore?continent=${encodeURIComponent(continent)}`}
            >
              {t(continent)} <ArrowUpRight size={13} />
            </Link>
          ))}
        </div>
        <ResourceState resource={destinations}>
          {(data) => (
            <div className="destination-grid">
              {CONTINENTS.map((continent) =>
                data.items.find((item) => item.continent === continent && item.tour_count > 0),
              ).filter(Boolean).map((destination) => (
                <Link
                  className="destination-card"
                  to={`/explore?destination=${destination.slug}`}
                  key={destination.id}
                >
                  <Photo src={destination.image_url} alt={destination.name} />
                  <div>
                    <span>{t(destination.continent)}</span>
                    <h3>{destination.name}</h3>
                  </div>
                  <ArrowUpRight size={21} />
                </Link>
              ))}
            </div>
          )}
        </ResourceState>
      </section>
      <section className="section home-trips">
        <div className="section-heading">
          <div>
            <p className="eyebrow">{t("curatedLabel")}</p>
            <h2>{t("curatedTitle")}</h2>
            <p>{t("curatedText")}</p>
          </div>
          <Link to="/explore" className="text-link">
            {t("viewAll")} <ArrowRight size={17} />
          </Link>
        </div>
        <p className="demo-notice">{t("demo")}</p>
        <ResourceState resource={tours}>
          {(data) => (
            <div className="tour-grid">
              {data.items.map((tour) => (
                <TourCard key={tour.id} tour={tour} />
              ))}
            </div>
          )}
        </ResourceState>
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
          {[Compass, CalendarDays, Send].map((Icon, index) => (
            <div key={index}>
              <div className="step-top">
                <Icon size={23} />
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
