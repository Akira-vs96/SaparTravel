import React, { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Search, SlidersHorizontal } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useApp } from "../context";
import { CATEGORIES, CONTINENTS } from "../i18n";
import {
  EmptyState,
  PageHeading,
  ResourceState,
  useResource,
} from "../components/common";
import TourCard from "../components/TourCard";

export default function Catalog() {
  const { lang, t } = useApp();
  const [params, setParams] = useSearchParams();
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [query, setQuery] = useState(params.get("q") || "");
  useEffect(() => setQuery(params.get("q") || ""), [params]);
  const apiParams = new URLSearchParams(params);
  apiParams.set("lang", lang);
  apiParams.set("page_size", "12");
  const tours = useResource(`/experiences?${apiParams}`);
  const destinations = useResource(`/destinations?lang=${lang}`);
  const update = (key, value) => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      value ? next.set(key, value) : next.delete(key);
      if (key !== "page") next.delete("page");
      return next;
    });
  };
  const reset = () => {
    setParams({});
    setQuery("");
  };
  return (
    <div className="page-container">
      <PageHeading eyebrow={t("catalogLabel")} title={t("catalogTitle")} />
      <p className="demo-notice">{t("demo")}</p>
      <form
        className="catalog-search"
        onSubmit={(event) => {
          event.preventDefault();
          update("q", query);
        }}
      >
        <Search size={21} />
        <input
          maxLength="100"
          aria-label={t("search")}
          placeholder={t("searchPlaceholder")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <button className="button dark" type="submit">
          {t("search")}
        </button>
      </form>
      <div className="catalog-layout">
        <aside className={`filter-panel ${filtersOpen ? "open" : ""}`}>
          <div className="filter-title">
            <h2>
              <SlidersHorizontal size={18} /> {t("filters")}
            </h2>
            <button className="text-button" onClick={reset}>
              {t("reset")}
            </button>
          </div>
          <label>
            {t("destinationLabel")}
            <select
              value={params.get("destination") || ""}
              onChange={(event) => update("destination", event.target.value)}
            >
              <option value="">{t("allDestinations")}</option>
              {destinations.data?.items.map((item) => (
                <option value={item.slug} key={item.id}>
                  {item.name === item.country ? item.name : `${item.name} · ${item.country}`}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("continent")}
            <select
              value={params.get("continent") || ""}
              onChange={(event) => update("continent", event.target.value)}
            >
              <option value="">{t("allContinents")}</option>
              {CONTINENTS.map((item) => (
                <option key={item} value={item}>
                  {t(item)}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("category")}
            <select
              value={params.get("category") || ""}
              onChange={(event) => update("category", event.target.value)}
            >
              <option value="">{t("allCategories")}</option>
              {CATEGORIES.map((item) => (
                <option key={item} value={item}>
                  {t(item)}
                </option>
              ))}
            </select>
          </label>
          <div className="form-row">
            <label>
              {t("minPrice")}
              <input
                type="number"
                min="0"
                value={params.get("min_price") || ""}
                placeholder="0"
                onChange={(event) => update("min_price", event.target.value)}
              />
            </label>
            <label>
              {t("maxPrice")}
              <input
                type="number"
                min="0"
                value={params.get("max_price") || ""}
                placeholder="∞"
                onChange={(event) => update("max_price", event.target.value)}
              />
            </label>
          </div>
          <label>
            {t("durationMax")}
            <input
              type="number"
              min="1"
              max="90"
              value={params.get("duration_max") || ""}
              placeholder="∞"
              onChange={(event) => update("duration_max", event.target.value)}
            />
          </label>
        </aside>
        <div className="catalog-results">
          <div className="results-toolbar">
            <button
              className="button secondary filter-toggle"
              onClick={() => setFiltersOpen(!filtersOpen)}
              aria-expanded={filtersOpen}
            >
              <SlidersHorizontal size={16} />
              {t("filters")}
            </button>
            <span>
              {tours.data?.total ?? "…"} {t("results")}
            </span>
            <select
              aria-label={t("sort")}
              value={params.get("sort") || "recommended"}
              onChange={(event) => update("sort", event.target.value)}
            >
              {["recommended", "price_asc", "price_desc", "rating"].map(
                (item) => (
                  <option key={item} value={item}>
                    {t(item)}
                  </option>
                ),
              )}
            </select>
          </div>
          <ResourceState resource={tours}>
            {(data) =>
              data.items.length ? (
                <>
                  <div className="tour-grid catalog-grid">
                    {data.items.map((tour) => (
                      <TourCard tour={tour} key={tour.id} />
                    ))}
                  </div>
                  {data.pages > 1 && (
                    <nav className="pagination" aria-label={t("page")}>
                      <button
                        className="button secondary"
                        disabled={data.page <= 1}
                        onClick={() => update("page", data.page - 1)}
                      >
                        <ArrowLeft size={16} />
                        <span>{t("previous")}</span>
                      </button>
                      <span>
                        {t("page")} {data.page} {t("of")} {data.pages}
                      </span>
                      <button
                        className="button secondary"
                        disabled={data.page >= data.pages}
                        onClick={() => update("page", data.page + 1)}
                      >
                        <span>{t("next")}</span>
                        <ArrowRight size={16} />
                      </button>
                    </nav>
                  )}
                </>
              ) : (
                <>
                  <EmptyState
                    title={t("noResults")}
                    text={t("noResultsText")}
                    action={false}
                  />
                  <button
                    className="button secondary reset-empty"
                    onClick={reset}
                  >
                    {t("reset")}
                  </button>
                </>
              )
            }
          </ResourceState>
        </div>
      </div>
    </div>
  );
}
