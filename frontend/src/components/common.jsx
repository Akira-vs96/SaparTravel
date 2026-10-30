import React, { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  Compass,
  Heart,
  LoaderCircle,
  X,
} from "lucide-react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useApp } from "../context";
import { photoCache } from "../photoCache";

export function useResource(path, options = {}) {
  const { token } = useApp();
  const [state, setState] = useState({
    data: null,
    loading: true,
    error: null,
  });
  const [attempt, setAttempt] = useState(0);
  const auth = options.auth || false;
  useEffect(() => {
    const controller = new AbortController();
    setState((old) => ({ ...old, loading: true, error: null }));
    api(path, { signal: controller.signal, token: auth ? token : undefined })
      .then((data) => {
        if (!controller.signal.aborted)
          setState({ data, loading: false, error: null });
      })
      .catch((error) => {
        if (!controller.signal.aborted && error.name !== "AbortError")
          setState({ data: null, loading: false, error });
      });
    return () => controller.abort();
  }, [path, auth, token, attempt]);
  return { ...state, reload: () => setAttempt((n) => n + 1) };
}

export function Loading() {
  const { t } = useApp();
  return (
    <div className="state-panel" role="status">
      <LoaderCircle className="spin" size={28} />
      <p>{t("loading")}</p>
    </div>
  );
}
export function ErrorState({ error, retry }) {
  const { t, errorText } = useApp();
  return (
    <div className="state-panel error-state" role="alert">
      <AlertCircle size={30} />
      <h3>{t("errorTitle")}</h3>
      <p>{errorText(error)}</p>
      {retry && (
        <button className="button secondary" onClick={retry}>
          {t("retry")}
        </button>
      )}
    </div>
  );
}
export function EmptyState({ title, text, action = true }) {
  const { t } = useApp();
  return (
    <div className="state-panel">
      <Compass size={34} />
      <h3>{title}</h3>
      <p>{text}</p>
      {action && (
        <Link to="/explore" className="button primary">
          {t("findTrip")} <ArrowRight size={17} />
        </Link>
      )}
    </div>
  );
}
export function ResourceState({ resource, children }) {
  if (resource.loading) return <Loading />;
  if (resource.error)
    return <ErrorState error={resource.error} retry={resource.reload} />;
  return children(resource.data);
}
export function Photo({ src, alt, className = "", ...props }) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const imgRef = useRef(null);
  const timeoutRef = useRef(null);
  const photoId =
    typeof src === "string"
      ? src.match(
          /^https:\/\/images\.unsplash\.com\/(photo-[A-Za-z0-9-]+)/,
        )?.[1]
      : null;
  const resolved = photoCache[photoId] || src;
  useEffect(() => {
    setFailed(false);
    setLoaded(false);
    clearTimeout(timeoutRef.current);
    const img = imgRef.current;
    if (!img || !resolved) return;
    if (img.complete && img.naturalWidth) {
      setLoaded(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          observer.disconnect();
          timeoutRef.current = setTimeout(() => setFailed(true), 10000);
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(img);
    return () => {
      observer.disconnect();
      clearTimeout(timeoutRef.current);
    };
  }, [resolved]);
  if (failed || !src)
    return (
      <div
        className={`image-fallback ${className}`}
        role="img"
        aria-label={alt}
      >
        <Compass size={44} />
      </div>
    );
  return (
    <img
      ref={imgRef}
      src={resolved}
      alt={alt}
      className={`${className} ${loaded ? "" : "photo-loading"}`}
      loading="lazy"
      onLoad={() => {
        setLoaded(true);
        clearTimeout(timeoutRef.current);
      }}
      onError={() => {
        setFailed(true);
        clearTimeout(timeoutRef.current);
      }}
      {...props}
    />
  );
}
export function SaveButton({ tour, className = "" }) {
  const {
    user,
    favorites,
    favoritesLoading,
    toggleFavorite,
    notify,
    errorText,
    t,
  } = useApp();
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const saved = favorites.some((item) => item.id === tour.id);
  const onClick = async () => {
    if (!user)
      return navigate(
        `/login?next=${encodeURIComponent(location.pathname + location.search)}`,
      );
    setBusy(true);
    try {
      await toggleFavorite(tour);
    } catch (error) {
      notify(errorText(error));
    } finally {
      setBusy(false);
    }
  };
  return (
    <button
      className={`save-button ${saved ? "is-saved" : ""} ${className}`}
      onClick={onClick}
      disabled={busy || (user && favoritesLoading)}
      aria-label={t(saved ? "removeSaved" : "saveTrip")}
      aria-pressed={saved}
      title={t(saved ? "removeSaved" : "saveTrip")}
    >
      <Heart size={19} fill={saved ? "currentColor" : "none"} />
    </button>
  );
}
export function Protected({ children, roles }) {
  const { user, authLoading, authError, retryAuth, t } = useApp();
  const location = useLocation();
  if (authLoading) return <Loading />;
  if (authError) return <ErrorState error={authError} retry={retryAuth} />;
  if (!user)
    return (
      <Navigate
        to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`}
        replace
      />
    );
  if (roles && !roles.includes(user.role))
    return <EmptyState title={t("forbidden")} />;
  return children;
}
export function Modal({ title, children, onClose }) {
  const ref = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const { t } = useApp();
  useEffect(() => {
    const dialog = ref.current;
    dialog.showModal();
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onCancel = (event) => {
      event.preventDefault();
      closeRef.current();
    };
    dialog.addEventListener("cancel", onCancel);
    return () => {
      dialog.removeEventListener("cancel", onCancel);
      document.body.style.overflow = oldOverflow;
      dialog.close();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby="modal-title"
      onClick={(event) => {
        if (event.target === ref.current) onClose();
      }}
    >
      <div className="modal-heading">
        <h2 id="modal-title">{title}</h2>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label={t("close")}
        >
          <X size={22} />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function FormError({ error }) {
  const { errorText, t } = useApp();
  const labels = {
    name: "name",
    email: "email",
    password: "password",
    current_password: "currentPassword",
    new_password: "newPassword",
    contact_name: "contactName",
    contact_email: "contactEmail",
    travelers_count: "travelers",
    participants: "participants",
    service_ids: "additionalServices",
    promo_code: "promoCode",
    notes: "notes",
    accept_cancellation_policy: "cancellationPolicy",
    departure_id: "chooseDate",
    card_number: "cardNumber",
    holder_name: "holderName",
    expiry_month: "expiryMonth",
    expiry_year: "expiryYear",
    cvc: "cardCvc",
    title: "title",
    title_en: "title",
    title_kk: "title",
    description: "description",
    description_en: "description",
    description_kk: "description",
    rating: "rating",
    text: "message",
    subject: "subject",
    body: "message",
    price: "price",
    price_from: "price",
    capacity: "capacity",
    start_date: "startDate",
    destination_id: "destinationLabel",
    category: "category",
    duration_days: "duration",
    gallery: "gallery",
    image_url: "imageUrl",
    services: "additionalServices",
    min_participants: "minParticipants",
    max_participants: "maxParticipants",
    cancellation_rules: "cancellationPolicy",
    itinerary: "itinerary",
    itinerary_en: "itinerary",
    itinerary_kk: "itinerary",
    publication_status: "status",
    status: "status",
    code: "code",
    value: "discount",
    min_amount: "minPrice",
    starts_at: "periodFrom",
    ends_at: "periodTo",
    usage_limit: "usageLimit",
    per_user_limit: "perUserLimit",
    amount: "total",
    reason: "reason",
    role: "role",
    name_ru: "russian",
    name_en: "english",
    name_kk: "kazakh",
  };
  const fields = error?.fields || error?.errors || [];
  const fieldLabels = Array.isArray(fields)
    ? [
        ...new Set(
          fields.map((item) => {
            const path = String(
              item.field || item.loc?.join(".") || "",
            ).replace(/^body\./, "");
            const key = path.split(".")[0];
            return t(labels[key] || "invalidField");
          }),
        ),
      ]
    : [];
  return error ? (
    <div className="form-error" role="alert">
      <AlertCircle size={17} />{" "}
      <div>
        <p>{typeof error === "string" ? error : errorText(error)}</p>
        {fieldLabels.length > 0 && (
          <ul>
            {fieldLabels.map((label) => (
              <li key={label}>
                <strong>{label}</strong> — {t("invalidValue")}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  ) : null;
}
export function PageHeading({ eyebrow, title, text, children }) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {text && <p className="intro-text">{text}</p>}
      </div>
      {children}
    </div>
  );
}
