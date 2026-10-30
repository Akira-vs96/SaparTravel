import React, { useRef, useState } from "react";
import { Check, Download, Edit3, Plus, RefreshCw, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { api, download, queryString } from "../api";
import { useApp } from "../context";
import { formatTime, money } from "../i18n";
import {
  EmptyState,
  FormError,
  Modal,
  ResourceState,
  useResource,
} from "../components/common";
export function Analytics() {
  const { t, token, lang, notify, errorText } = useApp();
  const [range, setRange] = useState({ from: "", to: "" });
  const resource = useResource(`/manage/analytics?${queryString(range)}`, {
    auth: true,
  });
  return (
    <section className="management-section">
      <div className="analytics-filters">
        <label>
          {t("periodFrom")}
          <input
            type="date"
            value={range.from}
            onChange={(e) => setRange({ ...range, from: e.target.value })}
          />
        </label>
        <label>
          {t("periodTo")}
          <input
            type="date"
            min={range.from || undefined}
            value={range.to}
            onChange={(e) => setRange({ ...range, to: e.target.value })}
          />
        </label>
        <button
          className="button secondary"
          onClick={async () => {
            try {
              await download(
                `/manage/analytics.csv?${queryString({ ...range, lang })}`,
                token,
                "sapar-analytics.csv",
              );
            } catch (error) {
              notify(errorText(error));
            }
          }}
        >
          <Download size={17} />
          {t("exportCsv")}
        </button>
      </div>
      <ResourceState resource={resource}>
        {(data) => (
          <>
            <div className="metric-grid">
              {[
                ["bookingCount", data.bookings_count],
                ["travelers", data.travelers_count],
                ["turnover", money(data.turnover, lang)],
                ["successfulPayments", money(data.successful_payments, lang)],
                ["refunds", money(data.refunds_amount, lang)],
                ["netReceived", money(data.net_received, lang)],
                ["capacity", data.capacity],
                ["occupiedSeats", data.occupied_seats],
              ].map(([key, value]) => (
                <div className="surface" key={key}>
                  <p>{t(key)}</p>
                  <strong>{value ?? "—"}</strong>
                </div>
              ))}
            </div>
            {data.currencies?.length > 1 && (
              <div className="table-wrapper">
                <table>
                  <caption>{t("currencyReport")}</caption>
                  <thead>
                    <tr>
                      <th>{t("currency")}</th>
                      <th>{t("turnover")}</th>
                      <th>{t("successfulPayments")}</th>
                      <th>{t("refunds")}</th>
                      <th>{t("netReceived")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.currencies.map((row) => (
                      <tr key={row.currency}>
                        <td>
                          <strong>{row.currency}</strong>
                        </td>
                        <td>{money(row.turnover, lang, row.currency)}</td>
                        <td>
                          {money(row.successful_payments, lang, row.currency)}
                        </td>
                        <td>{money(row.refunds_amount, lang, row.currency)}</td>
                        <td>{money(row.net_received, lang, row.currency)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="info-note">{t("analyticsNote")}</p>
          </>
        )}
      </ResourceState>
    </section>
  );
}
export function Moderation({ readonly = false }) {
  const { t, token, lang, notify, errorText } = useApp();
  const resource = useResource("/manage/reviews", { auth: true });
  const [busy, setBusy] = useState("");
  return (
    <ResourceState resource={resource}>
      {(data) =>
        data.items.length ? (
          <div className="review-list">
            {data.items.map((review) => (
              <article className="surface" key={review.id}>
                <div className="review-top">
                  <strong>{review.experience_title || review.title}</strong>
                  <span className={`status-badge ${review.status}`}>
                    {t(review.status)}
                  </span>
                </div>
                <h3>
                  {review.title} · {review.rating}/5
                </h3>
                <p>{review.text}</p>
                <p className="muted">
                  {review.author_name} · {formatTime(review.created_at, lang)}
                </p>
                <div className="button-row">
                  {!readonly &&
                    ["approved", "rejected"].map((status) => (
                      <button
                        className="button secondary small"
                        disabled={
                          busy === review.id || review.status === status
                        }
                        key={status}
                        onClick={async () => {
                          setBusy(review.id);
                          try {
                            await api(`/admin/reviews/${review.id}`, {
                              token,
                              method: "PATCH",
                              body: { status },
                            });
                            resource.reload();
                          } catch (error) {
                            notify(errorText(error));
                          } finally {
                            setBusy("");
                          }
                        }}
                      >
                        {t(status === "approved" ? "approve" : "reject")}
                      </button>
                    ))}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title={t("reviewEmpty")} action={false} />
        )
      }
    </ResourceState>
  );
}
export function FinancialRecords({ kind }) {
  const { t, token, lang, notify, errorText } = useApp();
  const resource = useResource(`/manage/${kind}`, { auth: true });
  const [busy, setBusy] = useState("");
  const [create, setCreate] = useState(false);
  return (
    <div className="management-section">
      {kind === "refunds" && (
        <div className="admin-form-toolbar">
          <button className="button primary" onClick={() => setCreate(true)}>
            <Plus size={17} />
            {t("newRefund")}
          </button>
        </div>
      )}
      <ResourceState resource={resource}>
        {(data) =>
          data.items.length ? (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>{t("reference")}</th>
                    <th>{t("booking")}</th>
                    <th>{t("total")}</th>
                    <th>{t("status")}</th>
                    <th>{t("date")}</th>
                    <th>{t("actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <span title={item.id}>{item.id.slice(0, 8)}</span>
                        {item.masked_card && <p>{item.masked_card}</p>}
                      </td>
                      <td>
                        <Link
                          className="text-link"
                          to={`/manage/bookings/${item.booking_id}`}
                        >
                          {item.booking_id.slice(0, 8)}
                        </Link>
                      </td>
                      <td>{money(item.amount, lang, item.currency)}</td>
                      <td>
                        <span className={`status-badge ${item.status}`}>
                          {t(item.status)}
                        </span>
                        {item.error_code && <p>{t(item.error_code)}</p>}
                      </td>
                      <td>{formatTime(item.created_at, lang)}</td>
                      <td>
                        {((kind === "payments" && item.status === "unknown") ||
                          (kind === "refunds" &&
                            ["failed", "processing"].includes(
                              item.status,
                            ))) && (
                          <button
                            className="button secondary small"
                            disabled={busy === item.id}
                            onClick={async () => {
                              setBusy(item.id);
                              try {
                                await api(
                                  kind === "payments"
                                    ? `/payments/${item.id}/reconcile`
                                    : `/refunds/${item.id}/retry`,
                                  { token, method: "POST" },
                                );
                                resource.reload();
                              } catch (error) {
                                notify(errorText(error));
                              } finally {
                                setBusy("");
                              }
                            }}
                          >
                            <RefreshCw size={14} />
                            {t(kind === "payments" ? "reconcile" : "retry")}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title={t("noRecords")} action={false} />
          )
        }
      </ResourceState>
      {create && (
        <RefundEditor
          onClose={() => setCreate(false)}
          onSaved={() => {
            setCreate(false);
            resource.reload();
          }}
        />
      )}
    </div>
  );
}
function RefundEditor({ onClose, onSaved }) {
  const idempotencyKey = useRef(crypto.randomUUID());
  const { t, token, lang } = useApp();
  const bookings = useResource(`/manage/bookings?lang=${lang}`, { auth: true });
  const [form, setForm] = useState({
    booking_id: "",
    amount: "",
    reason: "",
    scenario: "success",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  return (
    <Modal title={t("newRefund")} onClose={() => !busy && onClose()}>
      <form
        className="stack-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            const { booking_id, ...body } = form;
            await api(`/manage/bookings/${booking_id}/refunds`, {
              token,
              method: "POST",
          headers: { "Idempotency-Key": idempotencyKey.current },
              body,
            });
            onSaved();
          } catch (error) {
            setError(error);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          {t("booking")}
          <select
            required
            value={form.booking_id}
            onChange={(e) => setForm({ ...form, booking_id: e.target.value })}
          >
            <option value="">—</option>
            {bookings.data?.items
              .filter((b) => Number(b.paid_amount) > Number(b.refunded_amount))
              .map((b) => (
                <option key={b.id} value={b.id}>
                  {b.reference} · {b.contact_name} ·{" "}
                  {money(
                    Number(b.paid_amount) - Number(b.refunded_amount),
                    lang,
                  )}
                </option>
              ))}
          </select>
        </label>
        <label>
          {t("total")} · ₸
          <input
            required
            type="number"
            min="0.01"
            max="100000000"
            step="0.01"
            value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })}
          />
        </label>
        <label>
          {t("reason")}
          <input
            required
            minLength={3}
            maxLength={500}
            value={form.reason}
            onChange={(e) => setForm({ ...form, reason: e.target.value })}
          />
        </label>
        <label>
          {t("demoScenario")}
          <select
            value={form.scenario}
            onChange={(e) => setForm({ ...form, scenario: e.target.value })}
          >
            {["success", "temporary_failure", "processing"].map((value) => (
              <option value={value} key={value}>
                {t(value)}
              </option>
            ))}
          </select>
        </label>
        <FormError error={error} />
        <button className="button primary" disabled={busy}>
          {t(busy ? "sending" : "newRefund")}
        </button>
      </form>
    </Modal>
  );
}
export function Audit() {
  const { t, lang } = useApp();
  const [offset, setOffset] = useState(0);
  const resource = useResource(`/admin/audit?limit=30&offset=${offset}`, {
    auth: true,
  });
  return (
    <ResourceState resource={resource}>
      {(data) => (
        <>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>{t("date")}</th>
                  <th>{t("actions")}</th>
                  <th>{t("actor")}</th>
                  <th>{t("resource")}</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.id}>
                    <td>{formatTime(item.created_at, lang)}</td>
                    <td>{t(item.action)}</td>
                    <td>{item.actor_id?.slice(0, 8) || "—"}</td>
                    <td>
                      {item.resource_type} · {item.resource_id?.slice(0, 8)}
                      <p>
                        {Object.entries(item.details || {})
                          .map(
                            ([key, value]) => `${t(key)}: ${t(String(value))}`,
                          )
                          .join(" · ")}
                      </p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination">
            <button
              className="button secondary"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 30))}
            >
              {t("previous")}
            </button>
            <button
              className="button secondary"
              disabled={data.items.length < 30}
              onClick={() => setOffset(offset + 30)}
            >
              {t("next")}
            </button>
          </div>
        </>
      )}
    </ResourceState>
  );
}
const localDate = (value) => {
  const d = new Date(value);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
};
export function Promocodes() {
  const { t, lang } = useApp();
  const resource = useResource("/manage/promocodes", { auth: true });
  const [edit, setEdit] = useState(null);
  return (
    <div className="management-section">
      <div className="admin-form-toolbar">
        <button className="button primary" onClick={() => setEdit({})}>
          <Plus size={17} />
          {t("newPromo")}
        </button>
      </div>
      <ResourceState resource={resource}>
        {(data) =>
          data.items.length ? (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>{t("promoCode")}</th>
                    <th>{t("discount")}</th>
                    <th>{t("limits")}</th>
                    <th>{t("date")}</th>
                    <th>{t("status")}</th>
                    <th>{t("edit")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <strong>{item.code}</strong>
                      </td>
                      <td>
                        {item.kind === "percent"
                          ? `${Number(item.value)}%`
                          : money(item.value, lang)}
                        <p>
                          {t("minPrice")}: {money(item.min_amount, lang)}
                        </p>
                      </td>
                      <td>
                        {item.usage_limit} / {item.per_user_limit}
                      </td>
                      <td>
                        {formatTime(item.starts_at, lang)}
                        <br />
                        {formatTime(item.ends_at, lang)}
                      </td>
                      <td>{t(item.is_active ? "active" : "inactive")}</td>
                      <td>
                        <button
                          className="icon-button"
                          aria-label={`${t("edit")}: ${item.code}`}
                          onClick={() => setEdit(item)}
                        >
                          <Edit3 size={17} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title={t("noRecords")} action={false} />
          )
        }
      </ResourceState>
      {edit && (
        <PromoEditor
          item={edit}
          onClose={() => setEdit(null)}
          onSaved={() => {
            setEdit(null);
            resource.reload();
          }}
        />
      )}
    </div>
  );
}
function PromoEditor({ item, onClose, onSaved }) {
  const { t, token, lang } = useApp();
  const tours = useResource(`/manage/experiences?lang=${lang}`, { auth: true });
  const categories = useResource(`/categories?lang=${lang}`);
  const [form, setForm] = useState({
    code: item.code || "",
    kind: item.kind || "percent",
    value: item.value || "10",
    min_amount: item.min_amount || "0",
    starts_at: localDate(item.starts_at || Date.now()),
    ends_at: localDate(item.ends_at || Date.now() + 30 * 86400000),
    usage_limit: item.usage_limit || 100,
    per_user_limit: item.per_user_limit || 1,
    is_active: item.is_active ?? true,
    category: item.category || "",
    experience_id: item.experience_id || "",
  });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const update = (key, value) =>
    setForm((current) => ({ ...current, [key]: value }));
  return (
    <Modal
      title={t(item.id ? "edit" : "newPromo")}
      onClose={() => !busy && onClose()}
    >
      <form
        className="stack-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            await api(`/manage/promocodes${item.id ? `/${item.id}` : ""}`, {
              token,
              method: item.id ? "PUT" : "POST",
              body: {
                ...form,
                category: form.category || null,
                experience_id: form.experience_id || null,
                usage_limit: Number(form.usage_limit),
                per_user_limit: Number(form.per_user_limit),
                starts_at: new Date(form.starts_at).toISOString(),
                ends_at: new Date(form.ends_at).toISOString(),
              },
            });
            onSaved();
          } catch (error) {
            setError(error);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          {t("promoCode")}
          <input
            required
            minLength={3}
            maxLength={40}
            pattern="[A-Za-z0-9_-]+"
            value={form.code}
            onChange={(e) => update("code", e.target.value.toUpperCase())}
          />
        </label>
        <div className="form-row">
          <label>
            {t("discountType")}
            <select
              value={form.kind}
              onChange={(e) => update("kind", e.target.value)}
            >
              <option value="percent">%</option>
              <option value="fixed">₸</option>
            </select>
          </label>
          <label>
            {t("discount")}
            <input
              required
              type="number"
              min="0.01"
              max={form.kind === "percent" ? 100 : 100000000}
              step="0.01"
              value={form.value}
              onChange={(e) => update("value", e.target.value)}
            />
          </label>
        </div>
        <div className="form-row">
          <label>
            {t("periodFrom")}
            <input
              type="datetime-local"
              required
              value={form.starts_at}
              onChange={(e) => update("starts_at", e.target.value)}
            />
          </label>
          <label>
            {t("periodTo")}
            <input
              type="datetime-local"
              required
              min={form.starts_at}
              value={form.ends_at}
              onChange={(e) => update("ends_at", e.target.value)}
            />
          </label>
        </div>
        <label>
          {t("minPrice")} · ₸
          <input
            required
            min="0"
            max="100000000"
            step="0.01"
            type="number"
            value={form.min_amount}
            onChange={(e) => update("min_amount", e.target.value)}
          />
        </label>
        <div className="form-row">
          <label>
            {t("usageLimit")}
            <input
              required
              type="number"
              min="1"
              max="1000000"
              value={form.usage_limit}
              onChange={(e) => update("usage_limit", e.target.value)}
            />
          </label>
          <label>
            {t("perUserLimit")}
            <input
              required
              type="number"
              min="1"
              max="1000"
              value={form.per_user_limit}
              onChange={(e) => update("per_user_limit", e.target.value)}
            />
          </label>
        </div>
        <label>
          {t("tour")}
          <select
            value={form.experience_id}
            onChange={(e) => update("experience_id", e.target.value)}
          >
            <option value="">{t("allTours")}</option>
            {tours.data?.items.map((tour) => (
              <option key={tour.id} value={tour.id}>
                {tour.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("category")}
          <select value={form.category} onChange={(e) => update("category", e.target.value)}>
            <option value="">{t("allCategories")}</option>
            {categories.data?.items.map((category) => (
              <option key={category.code} value={category.code}>{category.name}</option>
            ))}
          </select>
        </label>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={form.is_active}
            onChange={(e) => update("is_active", e.target.checked)}
          />
          {t("active")}
        </label>
        <FormError error={error} />
        <button className="button primary" disabled={busy}>
          {t(busy ? "saving" : "save")}
        </button>
      </form>
    </Modal>
  );
}
export function Vendors() {
  const { t } = useApp();
  const resource = useResource("/admin/vendors", { auth: true });
  return (
    <ResourceState resource={resource}>
      {(data) => (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>{t("name")}</th>
                <th>{t("email")}</th>
                <th>{t("tourCount")}</th>
                <th>{t("status")}</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((vendor) => (
                <tr key={vendor.id}>
                  <td>{vendor.name}</td>
                  <td>{vendor.email}</td>
                  <td>{vendor.tour_count}</td>
                  <td>{t(vendor.is_active ? "active" : "inactive")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </ResourceState>
  );
}
export function Categories() {
  const { t, token, lang, notify, errorText } = useApp();
  const resource = useResource(`/categories?lang=${lang}`);
  const [edit, setEdit] = useState(null);
  const [busy, setBusy] = useState("");
  return (
    <div>
      <div className="admin-form-toolbar">
        <button className="button primary" onClick={() => setEdit({})}>
          <Plus size={17} />
          {t("newCategory")}
        </button>
      </div>
      <ResourceState resource={resource}>
        {(data) => (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>{t("category")}</th>
                  <th>{t("code")}</th>
                  <th>{t("tourCount")}</th>
                  <th>{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.code}>
                    <td>{item.name}</td>
                    <td>{item.code}</td>
                    <td>{item.tour_count}</td>
                    <td>
                      <div className="button-row">
                        <button
                          className="icon-button"
                          aria-label={`${t("edit")}: ${item.name}`}
                          onClick={() => setEdit(item)}
                        >
                          <Edit3 size={16} />
                        </button>
                        <button
                          className="icon-button danger-text"
                          aria-label={`${t("remove")}: ${item.name}`}
                          disabled={busy === item.code || item.tour_count > 0}
                          onClick={async () => {
                            setBusy(item.code);
                            try {
                              await api(`/admin/categories/${item.code}`, {
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
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </ResourceState>
      {edit && (
        <CategoryEditor
          item={edit}
          onClose={() => setEdit(null)}
          onSaved={() => {
            setEdit(null);
            resource.reload();
          }}
        />
      )}
    </div>
  );
}
function CategoryEditor({ item, onClose, onSaved }) {
  const { t, token } = useApp();
  const [form, setForm] = useState({
    code: item.code || "",
    name_ru: item.name_ru || "",
    name_kk: item.name_kk || "",
    name_en: item.name_en || "",
  });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={t("category")} onClose={() => !busy && onClose()}>
      <form
        className="stack-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            const { code, ...names } = form;
            await api(`/admin/categories${item.code ? `/${item.code}` : ""}`, {
              token,
              method: item.code ? "PATCH" : "POST",
              body: item.code ? names : form,
            });
            onSaved();
          } catch (error) {
            setError(error);
          } finally {
            setBusy(false);
          }
        }}
      >
        {["code", "name_ru", "name_kk", "name_en"].map((key) => (
          <label key={key}>
            {t(
              {
                code: "code",
                name_ru: "russian",
                name_kk: "kazakh",
                name_en: "english",
              }[key],
            )}
            <input
              required
              minLength={2}
              maxLength={key === "code" ? 30 : 100}
              pattern={key === "code" ? "[A-Za-z][A-Za-z0-9_-]+" : undefined}
              readOnly={key === "code" && Boolean(item.code)}
              value={form[key]}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
            />
          </label>
        ))}
        <FormError error={error} />
        <button className="button primary" disabled={busy}>
          {t(busy ? "saving" : "save")}
        </button>
      </form>
    </Modal>
  );
}
