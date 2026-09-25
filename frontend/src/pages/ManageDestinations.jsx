import React, { useState } from "react";
import { Edit3, Plus } from "lucide-react";
import { api } from "../api";
import { useApp } from "../context";
import { CONTINENTS } from "../i18n";
import {
  FormError,
  Modal,
  Photo,
  ResourceState,
  useResource,
} from "../components/common";

export default function ManageDestinations() {
  const { t, lang } = useApp();
  const resource = useResource("/manage/destinations", { auth: true });
  const [editing, setEditing] = useState(null);
  const localized = (item, key) =>
    lang !== "ru" && item[`${key}_${lang}`]
      ? item[`${key}_${lang}`]
      : item[key];
  return (
    <>
      <div className="destination-toolbar">
        <button className="button primary small" onClick={() => setEditing({})}>
          <Plus size={17} />
          {t("newDestination")}
        </button>
      </div>
      <ResourceState resource={resource}>
        {(data) => (
          <div className="manage-destination-grid">
            {data.items.map((item) => (
              <article className="manage-destination-card" key={item.id}>
                <Photo src={item.image_url} alt={localized(item, "name")} />
                <div>
                  <small>
                    {localized(item, "country")} · {t(item.continent)}
                  </small>
                  <h3>{localized(item, "name")}</h3>
                  <button
                    className="button secondary small"
                    onClick={() => setEditing(item)}
                  >
                    <Edit3 size={14} />
                    {t("edit")}
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </ResourceState>
      {editing && (
        <DestinationEditor
          destination={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            resource.reload();
          }}
        />
      )}
    </>
  );
}
function initialDestination(destination) {
  const form = {
    slug: destination.slug || "",
    continent: destination.continent || "Asia",
    image_url: destination.image_url || "",
  };
  ["", "_kk", "_en"].forEach((suffix) =>
    ["name", "country", "description"].forEach((field) => {
      form[field + suffix] = destination[field + suffix] || "";
    }),
  );
  return form;
}
function DestinationEditor({ destination, onClose, onSaved }) {
  const { token, t } = useApp();
  const [form, setForm] = useState(() => initialDestination(destination));
  const [editLang, setEditLang] = useState("ru");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const suffix = editLang === "ru" ? "" : `_${editLang}`;
  const update = (field) => (event) =>
    setForm((current) => ({ ...current, [field]: event.target.value }));
  const submit = async (event) => {
    event.preventDefault();
    setError(null);
    if (
      form.name.trim().length < 2 ||
      form.country.trim().length < 2 ||
      form.description.trim().length < 20
    ) {
      setEditLang("ru");
      setError(`${t("russian")}: ${t("validationError")}`);
      return;
    }
    const body = { ...form };
    if (destination.id) delete body.slug;
    setBusy(true);
    try {
      await api(
        destination.id
          ? `/manage/destinations/${destination.id}`
          : "/manage/destinations",
        { method: destination.id ? "PATCH" : "POST", token, body },
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
      title={t(destination.id ? "editDestination" : "newDestination")}
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <form className="stack-form" onSubmit={submit}>
        <nav className="tabs language-tabs">
          {[
            ["ru", "russian"],
            ["kk", "kazakh"],
            ["en", "english"],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={editLang === value ? "active" : ""}
              onClick={() => setEditLang(value)}
            >
              {t(label)}
            </button>
          ))}
        </nav>
        <label>
          {t("title")}
          <input
            maxLength="160"
            value={form[`name${suffix}`]}
            onChange={update(`name${suffix}`)}
          />
        </label>
        <label>
          {t("country")}
          <input
            maxLength="120"
            value={form[`country${suffix}`]}
            onChange={update(`country${suffix}`)}
          />
        </label>
        <label>
          {t("description")}
          <textarea
            maxLength="10000"
            rows="4"
            value={form[`description${suffix}`]}
            onChange={update(`description${suffix}`)}
          />
        </label>
        <hr />
        <label>
          {t("slugLabel")}
          <input
            required
            readOnly={Boolean(destination.id)}
            minLength="2"
            maxLength="100"
            pattern="[a-z0-9]+(?:-[a-z0-9]+)*"
            value={form.slug}
            onChange={update("slug")}
            placeholder="buenos-aires"
          />
          <small>{t("slugHint")}</small>
        </label>
        <label>
          {t("continent")}
          <select value={form.continent} onChange={update("continent")}>
            {CONTINENTS.map((value) => (
              <option key={value} value={value}>
                {t(value)}
              </option>
            ))}
          </select>
        </label>
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
        <FormError error={error} />
        <div className="modal-actions">
          <button
            className="button secondary"
            type="button"
            onClick={onClose}
            disabled={busy}
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
