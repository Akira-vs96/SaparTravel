import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { api } from "./api";
import { LANGUAGES, translate } from "./i18n";

const AppContext = createContext(null);
export const useApp = () => useContext(AppContext);
const readStorage = (key, fallback = "") => {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
};
const writeStorage = (key, value) => {
  try {
    value ? localStorage.setItem(key, value) : localStorage.removeItem(key);
  } catch {
    /* Storage may be disabled. */
  }
};

export function AppProvider({ children }) {
  const [lang, setLanguage] = useState(() => {
    const stored = readStorage("sapar-language", "ru");
    return LANGUAGES.includes(stored) ? stored : "ru";
  });
  const [token, setToken] = useState(() => readStorage("sapar-token"));
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(Boolean(token));
  const [authError, setAuthError] = useState(null);
  const [authAttempt, setAuthAttempt] = useState(0);
  const [favorites, setFavorites] = useState([]);
  const [favoriteError, setFavoriteError] = useState(null);
  const [favoritesLoading, setFavoritesLoading] = useState(Boolean(token));
  const favoriteRequest = useRef({ version: 0, controller: null });
  const activeToken = useRef(token);
  activeToken.current = token;
  const [toast, setToast] = useState("");
  const [comparison, setComparison] = useState(() => {
    try {
      return JSON.parse(readStorage("sapar-compare", "[]")).slice(0, 3);
    } catch {
      return [];
    }
  });
  const toggleCompare = (tour) => {
    setComparison((current) => {
      let next;
      if (current.some((item) => item.id === tour.id))
        next = current.filter((item) => item.id !== tour.id);
      else if (current.length >= 3) {
        setToast(translate(lang, "compareLimit"));
        return current;
      } else
        next = [
          ...current,
          { id: tour.id, slug: tour.slug, title: tour.title },
        ];
      writeStorage("sapar-compare", JSON.stringify(next));
      return next;
    });
  };
  const t = useCallback((key) => translate(lang, key), [lang]);
  const setLang = (value) => {
    setLanguage(value);
    writeStorage("sapar-language", value);
  };
  const logout = useCallback(() => {
    if (activeToken.current)
      api("/auth/logout", { token: activeToken.current, method: "POST" }).catch(
        () => {},
      );
    favoriteRequest.current.controller?.abort();
    favoriteRequest.current.version += 1;
    activeToken.current = "";
    setFavoritesLoading(false);
    writeStorage("sapar-token", "");
    setToken("");
    setUser(null);
    setFavorites([]);
    setAuthError(null);
    setFavoriteError(null);
  }, []);
  useEffect(() => {
    const unauthorized = (event) => {
      if (event.detail.token === activeToken.current) logout();
    };
    window.addEventListener("sapar:unauthorized", unauthorized);
    return () => window.removeEventListener("sapar:unauthorized", unauthorized);
  }, [logout]);
  const authenticated = (data) => {
    setFavorites([]);
    setFavoriteError(null);
    activeToken.current = data.access_token;
    writeStorage("sapar-token", data.access_token);
    setToken(data.access_token);
    setUser(data.user);
    setAuthError(null);
  };
  useEffect(() => {
    document.documentElement.lang = lang;
    document.title = `SaparTravel · ${translate(lang, "tagline")}`;
  }, [lang]);
  useEffect(() => {
    if (!token) {
      setAuthLoading(false);
      return;
    }
    const controller = new AbortController();
    setAuthLoading(true);
    setAuthError(null);
    api("/auth/me", { token, signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted && token === activeToken.current)
          setUser(data);
      })
      .catch((error) => {
        if (error.name === "AbortError" || token !== activeToken.current)
          return;
        if (error.status === 401) logout();
        else setAuthError(error);
      })
      .finally(() => {
        if (!controller.signal.aborted) setAuthLoading(false);
      });
    return () => controller.abort();
  }, [token, logout, authAttempt]);
  const reloadFavorites = useCallback(async () => {
    favoriteRequest.current.controller?.abort();
    const version = ++favoriteRequest.current.version;
    if (!token) return;
    const controller = new AbortController();
    favoriteRequest.current.controller = controller;
    setFavoritesLoading(true);
    try {
      const data = await api(`/favorites?lang=${lang}`, {
        token,
        signal: controller.signal,
      });
      if (
        version === favoriteRequest.current.version &&
        token === activeToken.current
      ) {
        setFavorites(data.items);
        setFavoriteError(null);
      }
    } catch (error) {
      if (
        error.name !== "AbortError" &&
        version === favoriteRequest.current.version &&
        token === activeToken.current
      )
        setFavoriteError(error);
    } finally {
      if (version === favoriteRequest.current.version)
        setFavoritesLoading(false);
    }
  }, [token, lang]);
  useEffect(() => {
    reloadFavorites();
    return () => {
      favoriteRequest.current.controller?.abort();
      favoriteRequest.current.version += 1;
    };
  }, [reloadFavorites]);
  useEffect(() => {
    if (!toast) return;
    const timeout = setTimeout(() => setToast(""), 5000);
    return () => clearTimeout(timeout);
  }, [toast]);
  const errorText = useCallback(
    (error) => {
      if (error?.code === "network") return t("network");
      if (error?.code === "invalid_response") return t("invalidResponse");
      const specific = {
        "Неверный адрес электронной почты или пароль.": "invalidCredentials",
        "Аккаунт с таким адресом уже существует.": "emailExists",
        "Некорректный номер тестовой карты или контрольная сумма.":
          "invalid_card",
        "Разрешены только документированные тестовые карты. Не вводите реальные банковские данные.":
          "testCardOnly",
        "Срок действия тестовой карты истёк.": "card_expired",
        "CVC тестовой карты должен содержать 3 цифры.": "invalid_cvc",
        "Минимальная цена не может быть больше максимальной.":
          "priceRangeError",
        "Нельзя менять длительность тура с созданными заездами. Создайте новый тур.":
          "durationLocked",
        "Для этого тура уже есть заезд на выбранную дату.": "duplicateDate",
        "Нельзя изменить роль последнего администратора.": "lastAdmin",
        "Направление с таким адресом уже существует.": "duplicateSlug",
        "Дни программы должны быть уникальными и укладываться в длительность тура.":
          "itineraryError",
      };
      if (specific[error?.message]) return t(specific[error.message]);
      if (
        error?.status === 422 &&
        (error?.message?.includes("expiry_month") ||
          error.fields?.some((item) => item.field?.endsWith("expiry_month")))
      )
        return t("invalid_expiry_month");
      if (
        error?.status === 422 &&
        (error?.message?.includes("expiry_year") ||
          error.fields?.some((item) => item.field?.endsWith("expiry_year")))
      )
        return t("invalid_expiry_year");
      if (
        error?.status === 422 &&
        (error?.message?.includes("cvc") ||
          error.fields?.some((item) => item.field?.endsWith("cvc")))
      )
        return t("invalid_cvc");
      if (error?.message?.startsWith("Недостаточно свободных мест."))
        return t("seatsChanged");
      const statusKey = {
        401: "sessionExpired",
        403: "permissionError",
        404: "notFoundText",
        409: "conflictError",
        422: "validationError",
        429: "rateLimit",
      }[error?.status];
      if (statusKey) return t(statusKey);
      if (error?.status >= 500) return t("network");
      return error?.message || t("errorTitle");
    },
    [t],
  );
  const toggleFavorite = async (tour) => {
    const saved = favorites.some((item) => item.id === tour.id);
    await api(`/favorites/${tour.id}`, {
      token,
      method: saved ? "DELETE" : "PUT",
    });
    if (token !== activeToken.current) return;
    favoriteRequest.current.controller?.abort();
    favoriteRequest.current.version += 1;
    setFavoritesLoading(false);
    setFavorites((current) =>
      saved
        ? current.filter((item) => item.id !== tour.id)
        : [...current, tour],
    );
  };
  return (
    <AppContext.Provider
      value={{
        lang,
        setLang,
        t,
        token,
        user,
        setUser,
        authenticated,
        logout,
        authLoading,
        authError,
        retryAuth: () => setAuthAttempt((n) => n + 1),
        favorites,
        favoriteError,
        favoritesLoading,
        reloadFavorites,
        toggleFavorite,
        comparison,
        toggleCompare,
        errorText,
        notify: setToast,
      }}
    >
      {children}
      {toast && (
        <div className="toast" role="status">
          {toast}
          <button onClick={() => setToast("")} aria-label={t("close")}>
            ×
          </button>
        </div>
      )}
    </AppContext.Provider>
  );
}
