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
        body: { is_published: !tour.is_published },
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
                        {t(tour.is_published ? "published" : "draft")}
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
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const result = await api(`/admin/users/${user.id}`, {
        token,
        method: "PATCH",
        body: { role },
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
          disabled={busy || role === user.role}
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
      price_from: Number(form.price_from),
      image_url: form.image_url,
      is_published: form.is_published,
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
                  {item.name === item.country ? item.name : `${item.name} · ${item.country}`}
                </option>
              ))}
            </select>
            {destinations.error && <FormError error={destinations.error} />}
          </label>
          <label>
            {t("category")}
            <select value={form.category} onChange={update("category")}>
              {CATEGORIES.map((item) => (
                <option value={item} key={item}>
                  {t(item)}
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
              max="1000000"
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
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={form.is_published}
            onChange={update("is_published")}
          />
          {t("publish")}
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
          price: Number(form.price),
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
            <div key={item.id}>
              <span>
                {formatDate(item.start_date, lang)}
                <small>
                  {item.available_seats} / {item.capacity} {t("seats")}
                </small>
              </span>
              <strong>{money(item.price, lang)}</strong>
            </div>
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
              max="1000000"
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
