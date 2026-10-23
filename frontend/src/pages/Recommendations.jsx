import React, { useEffect, useState } from "react";
import { ArrowRight, Compass, SlidersHorizontal } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useApp } from "../context";
import { queryString } from "../api";
import { CATEGORIES } from "../i18n";
import {
  EmptyState,
  PageHeading,
  ResourceState,
  useResource,
} from "../components/common";
import TourCard from "../components/TourCard";
export default function Recommendations() {
  const { t, lang } = useApp();
  const [params, setParams] = useSearchParams();
  const [form, setForm] = useState({
    budget: params.get("budget") || "500000",
    category: params.get("category") || "",
    duration_max: params.get("duration_max") || "7",
    travelers: params.get("travelers") || "1",
  });
  const resource = useResource(
    `/recommendations?${queryString({ budget: params.get("budget") || "500000", category: params.get("category") || "", duration_max: params.get("duration_max") || "7", travelers: params.get("travelers") || "1", lang })}`,
  );
  const categories = useResource(`/categories?lang=${lang}`);
  const update = (key, value) =>
    setForm((current) => ({ ...current, [key]: value }));
  return (
    <div className="page-container recommendation-page">
      <PageHeading
        eyebrow="SAPAR / DISCOVER"
        title={t("recommendations")}
        text={t("recommendationsText")}
      />
      <form
        className="surface recommendation-form"
        onSubmit={(e) => {
          e.preventDefault();
          setParams(form);
        }}
      >
        <label>
          {t("groupBudget")}
          <input
            type="number"
            min="1"
            max="100000000"
            step="1"
            required
            value={form.budget}
            onChange={(e) => update("budget", e.target.value)}
          />
        </label>
        <label>
          {t("category")}
          <select
            value={form.category}
            onChange={(e) => update("category", e.target.value)}
          >
            <option value="">{t("allCategories")}</option>
            {(
              categories.data?.items ||
              CATEGORIES.map((code) => ({ code, name: t(code) }))
            ).map((item) => (
              <option key={item.code} value={item.code}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("durationMax")}
          <input
            required
            type="number"
            min="1"
            max="90"
            value={form.duration_max}
            onChange={(e) => update("duration_max", e.target.value)}
          />
        </label>
        <label>
          {t("travelers")}
          <input
            required
            type="number"
            min="1"
            max="20"
            value={form.travelers}
            onChange={(e) => update("travelers", e.target.value)}
          />
        </label>
        <button className="button primary">
          <Compass size={18} />
          {t("findMatch")}
        </button>
      </form>
      <ResourceState resource={resource}>
        {(data) =>
          data.items.length ? (
            <>
              <div className="recommendation-reason">
                <Compass size={24} />
                <div>
                  <h2>{t("whyRecommended")}</h2>
                  <p>{data.notice || t("recommendationReason")}</p>
                </div>
              </div>
              <div className="tour-grid">
                {data.items.map((tour) => (
                  <div className="recommendation-item" key={tour.id}>
                    <TourCard tour={tour} />
                    {(tour.reason || tour.recommendation_reason) && (
                      <p>{tour.reason || tour.recommendation_reason}</p>
                    )}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <EmptyState
              title={t("noResults")}
              text={t("recommendationEmpty")}
              action={false}
            />
          )
        }
      </ResourceState>
    </div>
  );
}
