import React, { useState } from "react";
import {
  CalendarDays,
  CheckCircle2,
  Heart,
  LogOut,
  Settings2,
  UserRound,
} from "lucide-react";
import { Link, NavLink } from "react-router-dom";
import { api } from "../api";
import { useApp } from "../context";
import { formatDate, money } from "../i18n";
import {
  EmptyState,
  ErrorState,
  FormError,
  Loading,
  Modal,
  PageHeading,
  Photo,
  ResourceState,
  useResource,
} from "../components/common";
import TourCard from "../components/TourCard";

export function AccountNav() {
  const { t, user, logout } = useApp();
  return (
    <nav className="account-nav">
      <NavLink to="/account">
        <UserRound size={16} />
        {t("profile")}
      </NavLink>
      <NavLink to="/favorites">
        <Heart size={16} />
        {t("favorites")}
      </NavLink>
      <NavLink to="/bookings">
        <CalendarDays size={16} />
        {t("bookings")}
      </NavLink>
      {["vendor", "admin"].includes(user.role) && (
        <NavLink to="/manage">
          <Settings2 size={16} />
          {t("manage")}
        </NavLink>
      )}
      <button onClick={logout}>
        <LogOut size={16} />
        {t("logout")}
      </button>
    </nav>
  );
}
export function Profile() {
  const { user, setUser, token, t } = useApp();
  const [name, setName] = useState(user.name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const result = await api("/auth/me", {
        token,
        method: "PATCH",
        body: { name },
      });
      setUser(result);
      setSaved(true);
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="page-container account-page">
      <PageHeading eyebrow={t("account")} title={t("profileTitle")} />
      <AccountNav />
      <div className="profile-panel">
        <div className="profile-avatar">
          {user.name.charAt(0).toUpperCase()}
        </div>
        <div>
          <h2>{user.name}</h2>
          <span className="status-badge confirmed">{t(user.role)}</span>
        </div>
        <form className="stack-form" onSubmit={submit}>
          <label>
            {t("name")}
            <input
              required
              minLength="2"
              maxLength="120"
              value={name}
              onChange={(event) => {
                setName(event.target.value);
                setSaved(false);
              }}
              autoComplete="name"
            />
          </label>
          <label>
            {t("email")}
            <input
              type="email"
              value={user.email}
              readOnly
              autoComplete="email"
            />
          </label>
          <FormError error={error} />
          {saved && (
            <p className="success-message" role="status">
              <CheckCircle2 size={18} />
              {t("profileSaved")}
            </p>
          )}
          <button className="button primary" disabled={busy}>
            {t(busy ? "saving" : "save")}
          </button>
        </form>
      </div>
    </div>
  );
}
export function Favorites() {
  const { t, favorites, favoriteError, favoritesLoading, reloadFavorites } =
    useApp();
  return (
    <div className="page-container account-page">
      <PageHeading eyebrow={t("favorites")} title={t("favoritesTitle")} />
      <AccountNav />
      {favoritesLoading ? (
        <Loading />
      ) : favoriteError ? (
        <ErrorState error={favoriteError} retry={reloadFavorites} />
      ) : favorites.length ? (
        <div className="tour-grid">
          {favorites.map((tour) => (
            <TourCard tour={tour} key={tour.id} />
          ))}
        </div>
      ) : (
        <EmptyState title={t("favoritesEmpty")} text={t("favoritesText")} />
      )}
    </div>
  );
}
export function Bookings() {
  const { lang, t } = useApp();
  const resource = useResource(`/bookings?lang=${lang}`, { auth: true });
  return (
    <div className="page-container account-page">
      <PageHeading eyebrow={t("bookings")} title={t("bookingsTitle")} />
      <AccountNav />
      <ResourceState resource={resource}>
        {(data) =>
          data.items.length ? (
            <div className="booking-list">
              {data.items.map((booking) => (
                <BookingCard
                  key={booking.id}
                  booking={booking}
                  reload={resource.reload}
                />
              ))}
            </div>
          ) : (
            <EmptyState title={t("bookingsEmpty")} text={t("bookingsText")} />
          )
        }
      </ResourceState>
    </div>
  );
}
export function BookingCard({ booking, reload, management = false }) {
  const { lang, t, token } = useApp();
  const [cancelOpen, setCancelOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const changeStatus = async (status) => {
    setBusy(true);
    setError(null);
    try {
      await api(
        management
          ? `/manage/bookings/${booking.id}`
          : `/bookings/${booking.id}/cancel`,
        {
          token,
          method: management ? "PATCH" : "POST",
          ...(management ? { body: { status } } : {}),
        },
      );
      setCancelOpen(false);
      reload();
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <article className="booking-card">
      <Photo
        src={booking.experience.image_url}
        alt={booking.experience.title}
      />
      <div className="booking-card-content">
        <div className="booking-topline">
          <span className={`status-badge ${booking.status}`}>
            {t(booking.status)}
          </span>
          <span className="booking-reference">{booking.reference}</span>
        </div>
        <h2>
          <Link to={`/trips/${booking.experience.slug}`}>
            {booking.experience.title}
          </Link>
        </h2>
        <p className="muted">{booking.experience.destination}</p>
        <div className="booking-facts">
          <span>
            <CalendarDays size={16} />
            {formatDate(booking.start_date, lang)} —{" "}
            {formatDate(booking.end_date, lang)}
          </span>
          <span>
            <UserRound size={16} />
            {booking.travelers_count}
          </span>
        </div>
        {management && (
          <p className="booking-contact">
            {booking.contact_name} · {booking.contact_email}
            {booking.notes && <span>{booking.notes}</span>}
          </p>
        )}
        <div className="booking-card-bottom">
          <div>
            <strong>{money(booking.total_amount, lang)}</strong>
            <small>{t("noPayment")}</small>
          </div>
          <div className="button-row">
            {management &&
              booking.status === "pending" &&
              booking.start_date > new Date().toISOString().slice(0, 10) && (
                <button
                  className="button small primary"
                  disabled={busy}
                  onClick={() => changeStatus("confirmed")}
                >
                  {t("confirm")}
                </button>
              )}
            {management &&
              booking.status === "confirmed" &&
              booking.end_date < new Date().toISOString().slice(0, 10) && (
                <button
                  className="button small secondary"
                  disabled={busy}
                  onClick={() => changeStatus("completed")}
                >
                  {t("complete")}
                </button>
              )}
            {["pending", "confirmed"].includes(booking.status) &&
              (management ||
                booking.start_date > new Date().toISOString().slice(0, 10)) && (
                <button
                  className="text-button danger-text"
                  disabled={busy}
                  onClick={() => setCancelOpen(true)}
                >
                  {t("cancelBooking")}
                </button>
              )}
          </div>
        </div>
        {!cancelOpen && <FormError error={error} />}
      </div>
      {cancelOpen && (
        <Modal
          title={t("cancelQuestion")}
          onClose={() => {
            if (!busy) setCancelOpen(false);
          }}
        >
          <p>{booking.experience.title}</p>
          <p className="muted">{booking.reference}</p>
          <FormError error={error} />
          <div className="modal-actions">
            <button
              className="button secondary"
              disabled={busy}
              onClick={() => setCancelOpen(false)}
            >
              {t("keepBooking")}
            </button>
            <button
              className="button danger"
              disabled={busy}
              onClick={() => changeStatus("cancelled")}
            >
              {t(busy ? "sending" : "cancelBooking")}
            </button>
          </div>
        </Modal>
      )}
    </article>
  );
}
