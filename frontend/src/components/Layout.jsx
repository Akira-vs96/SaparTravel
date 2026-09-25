import React, { useEffect, useState } from "react";
import { ArrowUpRight, Compass, Heart, Menu, UserRound, X } from "lucide-react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useApp } from "../context";

export default function Layout() {
  const { user, lang, setLang, t, logout } = useApp();
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  useEffect(() => {
    setMenuOpen(false);
    window.scrollTo({ top: 0, behavior: "instant" });
  }, [location.pathname]);
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        {t("skipContent")}
      </a>
      <header className="site-header">
        <div className="header-inner">
          <Link className="brand" to="/" aria-label="SaparTravel">
            <span className="brand-mark">
              <Compass size={23} strokeWidth={1.7} />
            </span>
            sapar<span className="brand-light">travel</span>
            <span className="brand-dot">.</span>
          </Link>
          <nav className="desktop-nav" aria-label={t("menu")}>
            <NavLink to="/explore">{t("explore")}</NavLink>
            <a href="/#destinations">{t("destinations")}</a>
            <NavLink to="/about">{t("about")}</NavLink>
          </nav>
          <div className="header-actions">
            <select
              className="language-select"
              value={lang}
              onChange={(event) => setLang(event.target.value)}
              aria-label="Language / Тіл / Язык"
            >
              <option value="ru">RU</option>
              <option value="kk">ҚАЗ</option>
              <option value="en">EN</option>
            </select>
            <Link
              className="icon-button desktop-only"
              to="/favorites"
              aria-label={t("favorites")}
            >
              <Heart size={20} />
            </Link>
            <Link
              className="button small secondary account-link"
              to={user ? "/account" : "/login"}
            >
              <UserRound size={17} />
              <span>{t(user ? "account" : "login")}</span>
            </Link>
            <button
              className="icon-button mobile-menu-button"
              onClick={() => setMenuOpen(!menuOpen)}
              aria-expanded={menuOpen}
              aria-controls="mobile-nav"
              aria-label={t(menuOpen ? "close" : "menu")}
            >
              {menuOpen ? <X size={23} /> : <Menu size={23} />}
            </button>
          </div>
        </div>
        {menuOpen && (
          <nav
            id="mobile-nav"
            className="mobile-nav"
            onClick={() => setMenuOpen(false)}
          >
            <Link to="/explore">{t("explore")}</Link>
            <Link to="/favorites">{t("favorites")}</Link>
            <Link to="/bookings">{t("bookings")}</Link>
            <Link to="/about">{t("about")}</Link>
            {user && ["vendor", "admin"].includes(user.role) && (
              <Link to="/manage">{t("manage")}</Link>
            )}
            {user && <button onClick={logout}>{t("logout")}</button>}
          </nav>
        )}
      </header>
      <main id="main-content">
        <Outlet />
      </main>
      <footer className="site-footer">
        <div className="footer-main">
          <div>
            <Link to="/" className="brand">
              sapar<span className="brand-light">travel</span>
              <span className="brand-dot">.</span>
            </Link>
            <p>{t("tagline")}</p>
          </div>
          <nav>
            <Link to="/explore">
              {t("explore")} <ArrowUpRight size={14} />
            </Link>
            <Link to="/bookings">
              {t("bookings")} <ArrowUpRight size={14} />
            </Link>
            <Link to="/about">
              {t("about")} <ArrowUpRight size={14} />
            </Link>
          </nav>
        </div>
        <div className="footer-bottom">
          <span>© {new Date().getFullYear()} SaparTravel</span>
          <span>{t("footerText")}</span>
          <span>USD · {lang.toUpperCase()}</span>
        </div>
      </footer>
    </div>
  );
}
