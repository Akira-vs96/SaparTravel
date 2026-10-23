import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppProvider, useApp } from "./context";
import Layout from "./components/Layout";
import { EmptyState, PageHeading, Protected } from "./components/common";
import Home from "./pages/Home";
import Catalog from "./pages/Catalog";
import Trip from "./pages/Trip";
import Auth from "./pages/Auth";
import { Bookings, Favorites, Profile } from "./pages/Account";
import Manage from "./pages/Manage";
import Checkout from "./pages/Checkout";
import BookingDetail from "./pages/BookingDetail";
import { Compare, Notifications, SavedSearches } from "./pages/TravelTools";
import Support, { SupportDetail } from "./pages/Support";
import Password from "./pages/Password";
import Recommendations from "./pages/Recommendations";
import "./styles.css";

function About() {
  const { t } = useApp();
  return (
    <div className="page-container prose-page">
      <PageHeading eyebrow="SAPARTRAVEL" title={t("aboutTitle")} />
      <p>{t("aboutText")}</p>
      <div className="info-note">
        <p>{t("aboutHonest")}</p>
        <p>{t("aboutPrivacy")}</p>
      </div>
      <h2>{t("howTitle")}</h2>
      {[1, 2, 3].map((step) => (
        <section key={step}>
          <h3>
            0{step} · {t(`step${step}`)}
          </h3>
          <p>{t(`step${step}Text`)}</p>
        </section>
      ))}
    </div>
  );
}
function Privacy() {
  const { t } = useApp();
  return (
    <div className="page-container prose-page">
      <PageHeading eyebrow="SAPARTRAVEL" title={t("privacyTitle")} />
      <p>{t("privacyIntro")}</p>
      <section>
        <h2>{t("privacyCollectedTitle")}</h2>
        <p>{t("privacyCollectedText")}</p>
      </section>
      <section>
        <h2>{t("privacyUseTitle")}</h2>
        <p>{t("privacyUseText")}</p>
      </section>
      <section>
        <h2>{t("privacyRetentionTitle")}</h2>
        <p>{t("privacyRetentionText")}</p>
      </section>
      <section>
        <h2>{t("privacyDemoTitle")}</h2>
        <p>{t("privacyDemoText")}</p>
      </section>
      <div className="info-note">
        <p>{t("privacyDisclaimer")}</p>
      </div>
    </div>
  );
}
function NotFound() {
  const { t } = useApp();
  return (
    <div className="page-container">
      <EmptyState title={t("notFound")} text={t("notFoundText")} />
    </div>
  );
}
function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="explore" element={<Catalog />} />
            <Route path="recommendations" element={<Recommendations />} />
            <Route path="trips/:slug" element={<Trip />} />
            <Route path="login" element={<Auth key="login" />} />
            <Route path="register" element={<Auth key="register" register />} />
            <Route path="reset-password" element={<Password />} />
            <Route path="forgot-password" element={<Password />} />
            <Route path="compare" element={<Compare />} />
            <Route
              path="checkout/:slug"
              element={
                <Protected>
                  <Checkout />
                </Protected>
              }
            />
            <Route
              path="bookings/:id"
              element={
                <Protected>
                  <BookingDetail />
                </Protected>
              }
            />
            <Route
              path="manage/bookings/:id"
              element={
                <Protected roles={["vendor", "admin"]}>
                  <BookingDetail management />
                </Protected>
              }
            />
            <Route
              path="notifications"
              element={
                <Protected>
                  <Notifications />
                </Protected>
              }
            />
            <Route
              path="saved-searches"
              element={
                <Protected>
                  <SavedSearches />
                </Protected>
              }
            />
            <Route
              path="support"
              element={
                <Protected>
                  <Support />
                </Protected>
              }
            />
            <Route
              path="support/:id"
              element={
                <Protected>
                  <SupportDetail />
                </Protected>
              }
            />
            <Route
              path="account"
              element={
                <Protected>
                  <Profile />
                </Protected>
              }
            />
            <Route
              path="favorites"
              element={
                <Protected>
                  <Favorites />
                </Protected>
              }
            />
            <Route
              path="bookings"
              element={
                <Protected>
                  <Bookings />
                </Protected>
              }
            />
            <Route
              path="manage"
              element={
                <Protected roles={["vendor", "admin"]}>
                  <Manage />
                </Protected>
              }
            />
            <Route path="about" element={<About />} />
            <Route path="privacy" element={<Privacy />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
  );
}
createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
