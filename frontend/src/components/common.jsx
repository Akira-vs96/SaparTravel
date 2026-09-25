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
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((error) => {
        if (error.name !== "AbortError")
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
  useEffect(() => setFailed(false), [src]);
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
      src={src}
      alt={alt}
      className={className}
      loading="lazy"
      onError={() => setFailed(true)}
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
  const { errorText } = useApp();
  return error ? (
    <p className="form-error" role="alert">
      <AlertCircle size={17} />{" "}
      {typeof error === "string" ? error : errorText(error)}
    </p>
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
