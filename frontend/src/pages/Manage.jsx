import React, { useState } from "react";
import {
  ArrowUpRight,
  CalendarPlus,
  Check,
  Edit3,
  Plus,
  Trash2,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useApp } from "../context";
import { CATEGORIES, formatDate, money } from "../i18n";
import {
  EmptyState,
  FormError,
  Modal,
  PageHeading,
  Photo,
  ResourceState,
  useResource,
} from "../components/common";
import ManageDestinations from "./ManageDestinations";
import { AccountNav, BookingCard } from "./Account";
import {
  Analytics,
  Moderation,
  FinancialRecords,
  Audit,
  Promocodes,
  Vendors,
  Categories,
} from "./ManageExtras";
import Support from "./Support";
import MailDelivery from "./MailDelivery";

export default function Manage() {
  const { user, lang, t, token, notify, errorText } = useApp();
  const [tab, setTab] = useState("tours");
  const [editing, setEditing] = useState(null);
  const [departureTour, setDepartureTour] = useState(null);
  const [busyId, setBusyId] = useState("");
  const tours = useResource(`/manage/experiences?lang=${lang}`, { auth: true });
  const togglePublish = async (tour) => {
    setBusyId(tour.id);
    try {
      await api(`/manage/experiences/${tour.id}`, {
        token,
        method: "PATCH",
        body: {
          publication_status: tour.is_published ? "unpublished" : "published",
        },
      });
      tours.reload();
    } catch (error) {
      notify(errorText(error));
    } finally {
      setBusyId("");
    }
  };
  return (
    <div className="page-container manage-page">
      <PageHeading
        eyebrow={t("manage")}
        title={t(user.role === "admin" ? "adminDashboard" : "dashboard")}
      />
      <AccountNav />
      <div className="manage-toolbar">
        <nav className="tabs">
          <button
            className={tab === "tours" ? "active" : ""}
            onClick={() => setTab("tours")}
          >
            {t(user.role === "admin" ? "allTours" : "yourTours")}
          </button>
          <button
            className={tab === "bookings" ? "active" : ""}
            onClick={() => setTab("bookings")}
          >
            {t("bookings")}
          </button>
          {user.role === "admin" && (
            <button
              className={tab === "destinations" ? "active" : ""}
              onClick={() => setTab("destinations")}
            >
              {t("destinations")}
            </button>
          )}
          {[
            "analytics",
            "support",
            "reviews",
            ...(user.role === "admin"
              ? [
                  "moderation",
                  "payments",
                  "refunds",
                  "promos",
                  "vendors",
                  "categories",
                  "auditLog",
                  "mailDelivery",
                ]
              : []),
          ].map((key) => (
            <button
              key={key}
              className={tab === key ? "active" : ""}
              onClick={() => setTab(key)}
            >
              {t(key)}
            </button>
          ))}
          {user.role === "admin" && (
            <button
              className={tab === "users" ? "active" : ""}
              onClick={() => setTab("users")}
            >
              {t("users")}
            </button>
          )}
        </nav>
        {tab === "tours" && (
          <button
            className="button primary small"
            onClick={() => setEditing({})}
          >
            <Plus size={17} />
            {t("newTour")}
          </button>
        )}
      </div>
      {tab === "tours" && (
        <ResourceState resource={tours}>
          {(data) =>
            data.items.length ? (
              <div className="manage-tour-list">
                {data.items.map((tour) => (
                  <article className="manage-tour-card" key={tour.id}>
                    <Photo src={tour.image_url} alt={tour.title} />
                    <div className="manage-tour-info">
                      <span
                        className={`status-badge ${tour.is_published ? "confirmed" : "pending"}`}
                      >
                        {t(
                          tour.publication_status ||
                            (tour.is_published ? "published" : "draft"),
                        )}
                      </span>
                      <h2>{tour.title}</h2>
                      <p>
                        {tour.destination} · {tour.duration_days} {t("days")} ·{" "}
                        {money(tour.price_from, lang)}
                      </p>
                      <div className="manage-tour-actions">
                        <button
                          className="button secondary small"
                          onClick={() => setEditing(tour)}
                        >
                          <Edit3 size={15} />
                          {t("edit")}
                        </button>
                        <button
                          className="button secondary small"
                          onClick={() => setDepartureTour(tour)}
                        >
                          <CalendarPlus size={15} />
                          {t("departures")}
                        </button>
                        <button
                          className="text-button"
                          disabled={busyId === tour.id}
                          onClick={() => togglePublish(tour)}
                        >
                          {t(tour.is_published ? "unpublish" : "publish")}
                        </button>
                        {tour.is_published && (
                          <Link
                            className="icon-button"
                            to={`/trips/${tour.slug}`}
                            aria-label={t("details")}
                          >
                            <ArrowUpRight size={19} />
                          </Link>
                        )}
                        {tour.publication_status !== "archived" && (
                          <button
                            className="text-button danger-text"
                            disabled={busyId === tour.id}
                            onClick={async () => {
                              setBusyId(tour.id);
                              try {
                                await api(`/manage/experiences/${tour.id}`, {
                                  token,
                                  method: "PATCH",
                                  body: { publication_status: "archived" },
                                });
                                tours.reload();
                              } catch (error) {
                                notify(errorText(error));
                              } finally {
                                setBusyId("");
                              }
                            }}
                          >
                            {t("archive")}
                          </button>
                        )}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState
                title={t("manageEmpty")}
                text={t("manageEmptyText")}
                action={false}
              />
            )
          }
        </ResourceState>
      )}
      {tab === "destinations" && user.role === "admin" && (
        <ManageDestinations />
      )}
      {tab === "bookings" && <ManageBookings />}
      {tab === "users" && user.role === "admin" && <ManageUsers />}
      {tab === "analytics" && <Analytics />}
      {tab === "support" && <Support embedded />}
      {tab === "reviews" && <Moderation readonly />}
      {user.role === "admin" && (
        <>
          {tab === "moderation" && <Moderation />}
          {tab === "payments" && <FinancialRecords kind="payments" />}
          {tab === "refunds" && <FinancialRecords kind="refunds" />}
          {tab === "promos" && <Promocodes />}
          {tab === "vendors" && <Vendors />}
          {tab === "categories" && <Categories />}
          {tab === "auditLog" && <Audit />}
          {tab === "mailDelivery" && <MailDelivery />}
        </>
      )}
      {editing && (
        <TourEditor
          tour={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            tours.reload();
          }}
        />
      )}
      {departureTour && (
        <DepartureEditor
          tour={departureTour}
          onClose={() => setDepartureTour(null)}
          onSaved={tours.reload}
        />
      )}
    </div>
  );
}
function ManageBookings() {
  const { lang, t } = useApp();
  const resource = useResource(`/manage/bookings?lang=${lang}`, { auth: true });
  return (
    <ResourceState resource={resource}>
      {(data) =>
        data.items.length ? (
          <div className="booking-list">
            {data.items.map((booking) => (
              <BookingCard
                key={booking.id}
                booking={booking}
                reload={resource.reload}
                management
              />
            ))}
          </div>
        ) : (
          <EmptyState title={t("noManageBookings")} action={false} />
        )
      }
    </ResourceState>
  );
}
function ManageUsers() {
  const { t } = useApp();
  const resource = useResource("/admin/users", { auth: true });
  return (
    <ResourceState resource={resource}>
      {(data) => (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t("name")}</th>
                <th>{t("email")}</th>
                <th>{t("status")}</th>
                <th>{t("role")}</th>
                <th>{t("save")}</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((user) => (
                <UserRow key={user.id} user={user} reload={resource.reload} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </ResourceState>
  );
}
function UserRow({ user, reload }) {
  const { token, t, setUser, user: currentUser, notify, errorText } = useApp();
  const [role, setRole] = useState(user.role);
  const [active, setActive] = useState(user.is_active);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const result = await api(`/admin/users/${user.id}`, {
        token,
        method: "PATCH",
        body: { role, is_active: active },
      });
      if (currentUser.id === user.id) setUser(result);
      reload();
    } catch (error) {
      notify(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <tr>
      <td>{user.name}</td>
      <td>{user.email}</td>
      <td>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
          />
          {t("active")}
        </label>
      </td>
      <td>
        <select
          aria-label={`${t("role")}: ${user.email}`}
          value={role}
          onChange={(event) => setRole(event.target.value)}
        >
          {["traveler", "vendor", "admin"].map((value) => (
            <option value={value} key={value}>
              {t(value)}
            </option>
          ))}
        </select>
      </td>
      <td>
        <button
          className="button small secondary"
          onClick={save}
          disabled={busy || (role === user.role && active === user.is_active)}
        >
          <Check size={15} />
          {t("save")}
        </button>
      </td>
    </tr>
  );
}
const listToText = (list) => (list || []).join("\n");
const textToList = (value) =>
  value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
function initialTour(tour) {
  const form = {
    destination_id: tour.destination_id || "",
    category: tour.category || "Nature",
    duration_days: tour.duration_days || 1,
    price_from: tour.price_from || 100,
    image_url: tour.image_url || "",
    is_published: tour.is_published || false,
    publication_status:
      tour.publication_status || (tour.is_published ? "published" : "draft"),
    min_participants: tour.min_participants || 1,
    max_participants: tour.max_participants || 20,
    gallery: listToText(tour.gallery),
    services: (tour.services || []).map((item) => ({ ...item })),
    cancellation_rules: tour.cancellation_rules || [
      { days_before: 7, refund_percent: 100 },
      { days_before: 2, refund_percent: 80 },
      { days_before: 0, refund_percent: 50 },
    ],
  };
  ["", "_en", "_kk"].forEach((suffix) => {
    form[`title${suffix}`] = tour[`title${suffix}`] || "";
    form[`description${suffix}`] = tour[`description${suffix}`] || "";
    form[`tags${suffix}`] = (tour[`tags${suffix}`] || []).join(", ");
    form[`included${suffix}`] = listToText(tour[`included${suffix}`]);
    form[`excluded${suffix}`] = listToText(tour[`excluded${suffix}`]);
    form[`itinerary${suffix}`] = (tour[`itinerary${suffix}`] || []).map(
      (item) => ({ ...item }),
    );
  });
  return form;
}
function TourEditor({ tour, onClose, onSaved }) {
  const { t, token, lang } = useApp();
  const destinations = useResource(`/destinations?lang=${lang}`);
  const categories = useResource(`/categories?lang=${lang}`);
  const [form, setForm] = useState(() => initialTour(tour));
  const [editLang, setEditLang] = useState("ru");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const suffix = editLang === "ru" ? "" : `_${editLang}`;
  const update = (key) => (event) =>
    setForm((current) => ({
      ...current,
      [key]:
        event.target.type === "checkbox"
          ? event.target.checked
          : event.target.value,
    }));
  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    if (form.title.trim().length < 3 || form.description.trim().length < 20) {
      setEditLang("ru");
      setError(`${t("russian")}: ${t("validationError")}`);
      return;
    }
    const body = {
      destination_id: form.destination_id,
      category: form.category,
      duration_days: Number(form.duration_days),
      price_from: String(form.price_from),
      image_url: form.image_url,
      publication_status: form.publication_status,
      min_participants: Number(form.min_participants),
      max_participants: Number(form.max_participants),
      gallery: textToList(form.gallery),
      services: form.services.map((service) => ({
        ...(service.id ? { id: service.id } : {}),
        name: service.name,
        name_en: service.name_en || "",
        name_kk: service.name_kk || "",
        price: String(service.price),
        per_person: service.per_person,
        is_active: service.is_active ?? true,
      })),
      cancellation_rules: form.cancellation_rules.map((rule) => ({
        days_before: Number(rule.days_before),
        refund_percent: Number(rule.refund_percent),
      })),
    };
    try {
      ["", "_en", "_kk"].forEach((key) => {
        body[`title${key}`] = form[`title${key}`].trim();
        body[`description${key}`] = form[`description${key}`].trim();
        body[`tags${key}`] = form[`tags${key}`]
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
        body[`included${key}`] = textToList(form[`included${key}`]);
        body[`excluded${key}`] = textToList(form[`excluded${key}`]);
        const dayNumbers = new Set();
        body[`itinerary${key}`] = form[`itinerary${key}`].map((item) => {
          const day = Number(item.day);
          if (
            !Number.isInteger(day) ||
            day < 1 ||
            day > body.duration_days ||
            dayNumbers.has(day) ||
            !item.title.trim() ||
            !item.description.trim()
          )
            throw new Error(t("itineraryError"));
          dayNumbers.add(day);
          return {
            day,
            title: item.title.trim(),
            description: item.description.trim(),
          };
        });
      });
    } catch (error) {
      setError(error);
      return;
    }
    setBusy(true);
    try {
      await api(
        tour.id ? `/manage/experiences/${tour.id}` : "/manage/experiences",
        { token, method: tour.id ? "PATCH" : "POST", body },
      );
      onSaved();
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title={t(tour.id ? "editTour" : "newTour")}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <form className="stack-form tour-editor" onSubmit={submit}>
        <div className="tabs language-tabs">
          {[
            ["ru", "russian"],
            ["kk", "kazakh"],
            ["en", "english"],
          ].map(([value, label]) => (
            <button
              className={editLang === value ? "active" : ""}
              key={value}
              type="button"
              onClick={() => setEditLang(value)}
            >
              {t(label)}
            </button>
          ))}
        </div>
        <label>
          {t("title")} (
          {t(
            editLang === "ru"
              ? "russian"
              : editLang === "kk"
                ? "kazakh"
                : "english",
          )}
          )
          <input
            maxLength="180"
            value={form[`title${suffix}`]}
            onChange={update(`title${suffix}`)}
          />
        </label>
        <label>
          {t("description")}
          <textarea
            rows="4"
            maxLength="10000"
            value={form[`description${suffix}`]}
            onChange={update(`description${suffix}`)}
          />
        </label>
        <label>
          {t("tags")}
          <input
            value={form[`tags${suffix}`]}
            onChange={update(`tags${suffix}`)}
          />
        </label>
        <div className="form-row">
          <label>
            {t("included")} <small>({t("onePerLine")})</small>
            <textarea
              rows="4"
              value={form[`included${suffix}`]}
              onChange={update(`included${suffix}`)}
            />
          </label>
          <label>
            {t("excluded")} <small>({t("onePerLine")})</small>
            <textarea
              rows="4"
              value={form[`excluded${suffix}`]}
              onChange={update(`excluded${suffix}`)}
            />
          </label>
        </div>
        <fieldset className="itinerary-editor">
          <legend>{t("itinerary")}</legend>
          {form[`itinerary${suffix}`].map((item, index) => (
            <div className="itinerary-edit-day" key={index}>
              <div className="form-row">
                <label>
                  {t("day")}
                  <input
                    type="number"
                    required
                    min="1"
                    max={form.duration_days}
                    value={item.day}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        [`itinerary${suffix}`]: current[
                          `itinerary${suffix}`
                        ].map((day, i) =>
                          i === index
                            ? { ...day, day: event.target.value }
                            : day,
                        ),
                      }))
                    }
                  />
                </label>
                <label>
                  {t("title")}
                  <input
                    required
                    maxLength="180"
                    value={item.title}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        [`itinerary${suffix}`]: current[
                          `itinerary${suffix}`
                        ].map((day, i) =>
                          i === index
                            ? { ...day, title: event.target.value }
                            : day,
                        ),
                      }))
                    }
                  />
                </label>
                <button
                  type="button"
                  className="icon-button danger-text"
                  aria-label={`${t("removeDay")} ${item.day}`}
                  onClick={() =>
                    setForm((current) => ({
                      ...current,
                      [`itinerary${suffix}`]: current[
                        `itinerary${suffix}`
                      ].filter((_, i) => i !== index),
                    }))
                  }
                >
                  <Trash2 size={17} />
                </button>
              </div>
              <label>
                {t("description")}
                <textarea
                  required
                  maxLength="3000"
                  rows="3"
                  value={item.description}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      [`itinerary${suffix}`]: current[`itinerary${suffix}`].map(
                        (day, i) =>
                          i === index
                            ? { ...day, description: event.target.value }
                            : day,
                      ),
                    }))
                  }
                />
              </label>
            </div>
          ))}
          <button
            type="button"
            className="button secondary small"
            disabled={
              form[`itinerary${suffix}`].length >= Number(form.duration_days)
            }
            onClick={() =>
              setForm((current) => {
                const days = current[`itinerary${suffix}`];
                const number = Array.from(
                  { length: Number(current.duration_days) },
                  (_, index) => index + 1,
                ).find((day) => !days.some((item) => Number(item.day) === day));
                return {
                  ...current,
                  [`itinerary${suffix}`]: [
                    ...days,
                    { day: number, title: "", description: "" },
                  ],
                };
              })
            }
          >
            <Plus size={16} />
            {t("addDay")}
          </button>
        </fieldset>
        <hr />
        <div className="form-row">
          <label>
            {t("destinationLabel")}
            <select
              required
              value={form.destination_id}
              onChange={update("destination_id")}
            >
              <option value="">—</option>
              {destinations.data?.items.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.name === item.country
                    ? item.name
                    : `${item.name} · ${item.country}`}
                </option>
              ))}
            </select>
            {destinations.error && <FormError error={destinations.error} />}
          </label>
          <label>
            {t("category")}
            <select value={form.category} onChange={update("category")}>
              {(
                categories.data?.items ||
                CATEGORIES.map((code) => ({ code, name: t(code) }))
              ).map((item) => (
                <option value={item.code} key={item.code}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="form-row">
          <label>
            {t("duration")}
            <input
              type="number"
              required
              min="1"
              max="90"
              step="1"
              disabled={Boolean(tour.departures?.length)}
              title={tour.departures?.length ? t("durationLocked") : undefined}
              value={form.duration_days}
              onChange={update("duration_days")}
            />
          </label>
          <label>
            {t("price")}
            <input
              type="number"
              required
              min="1"
              max="100000000"
              step="0.01"
              value={form.price_from}
              onChange={update("price_from")}
            />
          </label>
        </div>
        <label>
          {t("imageUrl")}
          <input
            type="url"
            required
            value={form.image_url}
            onChange={update("image_url")}
            placeholder="https://…"
          />
        </label>
        <label>
          {t("gallery")} <small>{t("onePerLine")}</small>
          <textarea
            rows={3}
            value={form.gallery}
            onChange={update("gallery")}
            placeholder="https://…"
          />
        </label>
        <div className="form-row">
          <label>
            {t("minParticipants")}
            <input
              type="number"
              required
              min="1"
              max="20"
              value={form.min_participants}
              onChange={update("min_participants")}
            />
          </label>
          <label>
            {t("maxParticipants")}
            <input
              type="number"
              required
              min={form.min_participants}
              max="20"
              value={form.max_participants}
              onChange={update("max_participants")}
            />
          </label>
        </div>
        <fieldset className="itinerary-editor stack-form">
          <legend>{t("additionalServices")}</legend>
          {form.services.map((service, index) => (
            <div className="service-editor-row" key={service.id || index}>
              {["name", "name_kk", "name_en"].map((key) => (
                <label key={key}>
                  {t("name")} ·{" "}
                  {key === "name" ? "RU" : key === "name_kk" ? "ҚАЗ" : "EN"}
                  <input
                    required={key === "name"}
                    minLength={key === "name" ? 3 : undefined}
                    maxLength="180"
                    value={service[key] || ""}
                    onChange={(e) =>
                      setForm((current) => ({
                        ...current,
                        services: current.services.map((s, i) =>
                          i === index ? { ...s, [key]: e.target.value } : s,
                        ),
                      }))
                    }
                  />
                </label>
              ))}
              <div className="form-row">
                <label>
                  {t("price")} · ₸
                  <input
                    type="number"
                    required
                    min="0"
                    max="100000000"
                    step="0.01"
                    value={service.price}
                    onChange={(e) =>
                      setForm((current) => ({
                        ...current,
                        services: current.services.map((s, i) =>
                          i === index ? { ...s, price: e.target.value } : s,
                        ),
                      }))
                    }
                  />
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={service.per_person}
                    onChange={(e) =>
                      setForm((current) => ({
                        ...current,
                        services: current.services.map((s, i) =>
                          i === index
                            ? { ...s, per_person: e.target.checked }
                            : s,
                        ),
                      }))
                    }
                  />
                  {t("perPerson")}
                </label>
              </div>
              <button
                type="button"
                className="text-button danger-text"
                onClick={() =>
                  setForm((current) => ({
                    ...current,
                    services: current.services.filter((_, i) => i !== index),
                  }))
                }
              >
                {t("remove")}
              </button>
            </div>
          ))}
          <button
            type="button"
            className="button secondary"
            disabled={form.services.length >= 20}
            onClick={() =>
              setForm((current) => ({
                ...current,
                services: [
                  ...current.services,
                  {
                    name: "",
                    name_en: "",
                    name_kk: "",
                    price: "0",
                    per_person: true,
                    is_active: true,
                  },
                ],
              }))
            }
          >
            <Plus size={16} />
            {t("addService")}
          </button>
        </fieldset>
        <fieldset className="itinerary-editor stack-form">
          <legend>{t("cancellationPolicy")}</legend>
          {form.cancellation_rules.map((rule, index) => (
            <div className="form-row" key={index}>
              <label>
                {t("daysBefore")}
                <input
                  type="number"
                  min="0"
                  max="365"
                  required
                  value={rule.days_before}
                  onChange={(e) =>
                    setForm((current) => ({
                      ...current,
                      cancellation_rules: current.cancellation_rules.map(
                        (r, i) =>
                          i === index
                            ? { ...r, days_before: e.target.value }
                            : r,
                      ),
                    }))
                  }
                />
              </label>
              <label>
                {t("refund")} %
                <input
                  type="number"
                  min="0"
                  max="100"
                  required
                  value={rule.refund_percent}
                  onChange={(e) =>
                    setForm((current) => ({
                      ...current,
                      cancellation_rules: current.cancellation_rules.map(
                        (r, i) =>
                          i === index
                            ? { ...r, refund_percent: e.target.value }
                            : r,
                      ),
                    }))
                  }
                />
              </label>
            </div>
          ))}
        </fieldset>
        <label>
          {t("status")}
          <select
            value={form.publication_status}
            onChange={update("publication_status")}
          >
            {["draft", "published", "unpublished", "archived"].map((status) => (
              <option value={status} key={status}>
                {t(status)}
              </option>
            ))}
          </select>
        </label>
        <FormError error={error} />
        <div className="modal-actions">
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={onClose}
          >
            {t("cancel")}
          </button>
          <button className="button primary" disabled={busy}>
            {t(busy ? "saving" : "save")}
          </button>
        </div>
      </form>
    </Modal>
  );
}
function DepartureEditor({ tour, onClose, onSaved }) {
  const { t, lang, token } = useApp();
  const [departures, setDepartures] = useState(tour.departures || []);
  const [form, setForm] = useState({
    start_date: "",
    capacity: 12,
    price: tour.price_from,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const departure = await api(`/manage/experiences/${tour.id}/departures`, {
        token,
        method: "POST",
        body: {
          start_date: form.start_date,
          capacity: Number(form.capacity),
          price: String(form.price),
        },
      });
      setDepartures((items) =>
        [...items, departure].sort((a, b) =>
          a.start_date.localeCompare(b.start_date),
        ),
      );
      setForm({ ...form, start_date: "" });
      onSaved();
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title={t("departures")}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <h3>{tour.title}</h3>
      {departures.length ? (
        <div className="departure-list">
          {departures.map((item) => (
            <DepartureRow
              key={item.id}
              item={item}
              tourId={tour.id}
              onChange={(value) => {
                setDepartures((rows) =>
                  value
                    ? rows.map((row) => (row.id === value.id ? value : row))
                    : rows.filter((row) => row.id !== item.id),
                );
                onSaved();
              }}
            />
          ))}
        </div>
      ) : (
        <p className="muted">{t("noDepartures")}</p>
      )}
      <form className="stack-form" onSubmit={submit}>
        <h3>{t("addDeparture")}</h3>
        <label>
          {t("startDate")}
          <input
            type="date"
            required
            min={new Date(Date.now() + 86400000).toISOString().slice(0, 10)}
            value={form.start_date}
            onChange={(event) =>
              setForm({ ...form, start_date: event.target.value })
            }
          />
        </label>
        <div className="form-row">
          <label>
            {t("capacity")}
            <input
              type="number"
              required
              min="1"
              max="1000"
              value={form.capacity}
              onChange={(event) =>
                setForm({ ...form, capacity: event.target.value })
              }
            />
          </label>
          <label>
            {t("price")}
            <input
              type="number"
              required
              min="1"
              max="100000000"
              step="0.01"
              value={form.price}
              onChange={(event) =>
                setForm({ ...form, price: event.target.value })
              }
            />
          </label>
        </div>
        <FormError error={error} />
        <button className="button primary" disabled={busy}>
          {t(busy ? "saving" : "addDeparture")}
          <Plus size={17} />
        </button>
      </form>
    </Modal>
  );
}
function DepartureRow({ item, tourId, onChange }) {
  const { t, lang, token } = useApp();
  const [editing, setEditing] = useState(false);
  const [capacity, setCapacity] = useState(item.capacity);
  const [price, setPrice] = useState(item.price);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [cancel, setCancel] = useState(false);
  const save = async (status) => {
    setBusy(true);
    setError(null);
    try {
      const result = await api(
        `/manage/experiences/${tourId}/departures/${item.id}`,
        {
          token,
          method: "PATCH",
          body: {
            capacity: Number(capacity),
            price: String(price),
            ...(status ? { status } : {}),
          },
        },
      );
      onChange(result);
      setEditing(false);
      setCancel(false);
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="departure-edit-row">
      <div className="summary-line">
        <span>
          {formatDate(item.start_date, lang)}
          <small>
            {item.available_seats} / {item.capacity} {t("seats")} ·{" "}
            {t(item.status || "scheduled")}
          </small>
        </span>
        <strong>{money(item.price, lang)}</strong>
      </div>
      {editing ? (
        <div className="form-row">
          <label>
            {t("capacity")}
            <input
              required
              type="number"
              min={Math.max(1, item.capacity - item.available_seats)}
              max="1000"
              value={capacity}
              onChange={(e) => setCapacity(e.target.value)}
            />
          </label>
          <label>
            {t("price")} · ₸
            <input
              required
              type="number"
              min="0.01"
              max="100000000"
              step="0.01"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={() => save()}
          >
            {t("save")}
          </button>
        </div>
      ) : (
        <div className="button-row">
          <button className="text-button" onClick={() => setEditing(true)}>
            {t("edit")}
          </button>
          {item.status !== "cancelled" && (
            <button
              className="text-button danger-text"
              disabled={busy}
              onClick={() => setCancel(true)}
            >
              {t("cancelDeparture")}
            </button>
          )}
          <button
            className="text-button danger-text"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                await api(`/manage/departures/${item.id}`, {
                  token,
                  method: "DELETE",
                });
                onChange(null);
              } catch (error) {
                setError(error);
              } finally {
                setBusy(false);
              }
            }}
          >
            {t("remove")}
          </button>
        </div>
      )}
      <FormError error={error} />
      {cancel && (
        <div className="info-note">
          <p>{t("cancelDepartureText")}</p>
          <div className="button-row">
            <button
              className="button danger small"
              disabled={busy}
              onClick={() => save("cancelled")}
            >
              {t("confirm")}
            </button>
            <button
              className="button secondary small"
              disabled={busy}
              onClick={() => setCancel(false)}
            >
              {t("cancel")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
