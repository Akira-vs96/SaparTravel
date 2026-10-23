import React, { useState } from "react";
import {
  Bell,
  Check,
  ChevronRight,
  GitCompareArrows,
  Heart,
  Search,
  Trash2,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api, queryString } from "../api";
import { useApp } from "../context";
import { formatDate, formatTime, money } from "../i18n";
import {
  EmptyState,
  PageHeading,
  Photo,
  ResourceState,
  useResource,
} from "../components/common";
import { AccountNav } from "./Account";
export function Notifications() {
  const { t, lang, token, notify, errorText } = useApp();
  const resource = useResource("/notifications", { auth: true });
  const [busy, setBusy] = useState(false);
  const read = async (id) => {
    setBusy(true);
    try {
      await api(`/notifications/${id ? `${id}/read` : "read-all"}`, {
        token,
        method: "POST",
      });
      resource.reload();
    } catch (error) {
      notify(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="page-container account-page">
      <PageHeading eyebrow={t("account")} title={t("notifications")}>
        <button
          className="button secondary"
          disabled={busy}
          onClick={() => read()}
        >
          <Check size={17} />
          {t("markAllRead")}
        </button>
      </PageHeading>
      <AccountNav />
      <ResourceState resource={resource}>
        {(data) =>
          data.items.length ? (
            <div className="notification-list">
              {data.items.map((item) => (
                <article
                  className={`surface notification-card ${item.is_read ? "" : "unread"}`}
                  key={item.id}
                >
                  <span className="notification-icon">
                    <Bell size={21} />
                  </span>
                  <div>
                    <h2>
                      {(lang !== "ru" && item[`title_${lang}`]) || item.title}
                    </h2>
                    <p>
                      {(lang !== "ru" && item[`body_${lang}`]) || item.body}
                    </p>
                    <small>{formatTime(item.created_at, lang)}</small>
                    {item.booking_id && (
                      <Link
                        className="text-link"
                        to={`/bookings/${item.booking_id}`}
                      >
                        {t("tripDetails")} <ChevronRight size={15} />
                      </Link>
                    )}
                  </div>
                  {!item.is_read && (
                    <button
                      className="icon-button"
                      aria-label={t("markRead")}
                      title={t("markRead")}
                      disabled={busy}
                      onClick={() => read(item.id)}
                    >
                      <Check size={19} />
                    </button>
                  )}
                </article>
              ))}
            </div>
          ) : (
            <EmptyState title={t("notificationEmpty")} action={false} />
          )
        }
      </ResourceState>
    </div>
  );
}
export function SavedSearches() {
  const { t, token, notify, errorText } = useApp();
  const resource = useResource("/saved-searches", { auth: true });
  const [busy, setBusy] = useState("");
  return (
    <div className="page-container account-page">
      <PageHeading eyebrow={t("account")} title={t("savedSearches")} />
      <AccountNav />
      <ResourceState resource={resource}>
        {(data) =>
          data.items.length ? (
            <div className="saved-search-list">
              {data.items.map((search) => (
                <article className="surface saved-search" key={search.id}>
                  <Search size={23} />
                  <div>
                    <h2>{search.name}</h2>
                    <p>
                      {Object.entries(search.filters)
                        .filter(([k, v]) => v && !["page", "lang"].includes(k))
                        .map(
                          ([key, value]) =>
                            `${t({ q: "search", destination: "destinationLabel", category: "category", min_price: "minPrice", max_price: "maxPrice", date_from: "dateFrom", date_to: "dateTo", duration_max: "durationMax", travelers: "travelers", sort: "sort", continent: "continent" }[key] || key)}: ${t(String(value))}`,
                        )
                        .join(" · ")}
                    </p>
                  </div>
                  <Link
                    className="button secondary"
                    to={`/explore?${queryString(search.filters)}`}
                  >
                    {t("search")}
                    <ChevronRight size={16} />
                  </Link>
                  <button
                    className="icon-button danger-text"
                    aria-label={`${t("remove")}: ${search.name}`}
                    disabled={busy === search.id}
                    onClick={async () => {
                      setBusy(search.id);
                      try {
                        await api(`/saved-searches/${search.id}`, {
                          token,
                          method: "DELETE",
                        });
                        resource.reload();
                      } catch (error) {
                        notify(errorText(error));
                      } finally {
                        setBusy("");
                      }
                    }}
                  >
                    <Trash2 size={18} />
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState title={t("savedSearchEmpty")} text={t("compareText")} />
          )
        }
      </ResourceState>
    </div>
  );
}
export function Compare() {
  const { t, comparison } = useApp();
  return (
    <div className="page-container compare-page">
      <PageHeading
        eyebrow="SAPARTRAVEL"
        title={`${t("compare")} (${comparison.length}/3)`}
      />
      {comparison.length ? (
        <div className="comparison-grid">
          {comparison.map((item) => (
            <CompareColumn key={item.id} item={item} />
          ))}
        </div>
      ) : (
        <EmptyState title={t("compareEmpty")} text={t("compareText")} />
      )}
    </div>
  );
}
function CompareColumn({ item }) {
  const { lang, t, toggleCompare } = useApp();
  const resource = useResource(`/experiences/${item.slug}?lang=${lang}`);
  return (
    <article className="surface compare-column">
      <button
        className="text-button danger-text compare-remove"
        onClick={() => toggleCompare(item)}
      >
        <Trash2 size={14} />
        {t("remove")}
      </button>
      <ResourceState resource={resource}>
        {(tour) => (
          <>
            <Photo src={tour.image_url} alt={tour.title} />
            <h2>{tour.title}</h2>
            <p className="muted">{tour.destination}</p>
            <dl>
              <div>
                <dt>{t("from")}</dt>
                <dd>{money(tour.price_from, lang)}</dd>
              </div>
              <div>
                <dt>{t("durationMax")}</dt>
                <dd>
                  {tour.duration_days} {t("days")}
                </dd>
              </div>
              <div>
                <dt>{t("nextDeparture")}</dt>
                <dd>
                  {tour.departures.find(
                    (d) =>
                      d.available_seats > 0 &&
                      d.start_date >= new Date().toISOString().slice(0, 10),
                  )?.start_date
                    ? formatDate(
                        tour.departures.find(
                          (d) =>
                            d.available_seats > 0 &&
                            d.start_date >=
                              new Date().toISOString().slice(0, 10),
                        ).start_date,
                        lang,
                      )
                    : t("noDates")}
                </dd>
              </div>
              <div>
                <dt>{t("included")}</dt>
                <dd>{tour.included.join(" · ")}</dd>
              </div>
              <div>
                <dt>{t("additionalServices")}</dt>
                <dd>
                  {tour.services
                    ?.map((s) => `${s.name} (${money(s.price, lang)})`)
                    .join(" · ") || "—"}
                </dd>
              </div>
              <div>
                <dt>{t("restrictions")}</dt>
                <dd>
                  {tour.min_participants || 1}–{tour.max_participants || 20}{" "}
                  {t("travelers").toLowerCase()}
                </dd>
              </div>
            </dl>
            <Link
              className="button primary full-width"
              to={`/trips/${tour.slug}`}
            >
              {t("details")}
              <ChevronRight size={17} />
            </Link>
          </>
        )}
      </ResourceState>
    </article>
  );
}
