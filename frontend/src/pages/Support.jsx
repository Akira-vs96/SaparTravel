import React, { useState } from "react";
import { ArrowLeft, ArrowRight, MessageCircle, Plus, Send } from "lucide-react";
import {
  Link,
  useParams,
  useSearchParams,
  useNavigate,
} from "react-router-dom";
import { api } from "../api";
import { useApp } from "../context";
import { formatTime } from "../i18n";
import {
  EmptyState,
  FormError,
  Modal,
  PageHeading,
  ResourceState,
  useResource,
} from "../components/common";
import { AccountNav } from "./Account";
export default function Support({ embedded = false }) {
  const { t, lang, token } = useApp();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [open, setOpen] = useState(Boolean(params.get("booking")));
  const [form, setForm] = useState({
    subject: "",
    body: "",
    booking_id: params.get("booking") || null,
    priority: "P3",
  });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const resource = useResource("/support/tickets", { auth: true });
  return (
    <div className={embedded ? "" : "page-container account-page"}>
      {!embedded && (
        <>
          <PageHeading
            eyebrow={t("support")}
            title={t("supportTitle")}
            text={t("supportText")}
          />
          <AccountNav />
        </>
      )}
      <div className="support-toolbar">
        <button className="button primary" onClick={() => setOpen(true)}>
          <Plus size={18} />
          {t("newTicket")}
        </button>
      </div>
      <ResourceState resource={resource}>
        {(data) =>
          data.items.length ? (
            <div className="ticket-list">
              {data.items.map((ticket) => (
                <Link
                  className="surface ticket-card"
                  to={`/support/${ticket.id}`}
                  key={ticket.id}
                >
                  <MessageCircle size={25} />
                  <div>
                    <h2>{ticket.subject}</h2>
                    <small>{ticket.priority} · {t(`priority${ticket.priority}`)}</small>
                    <small>
                      {formatTime(ticket.updated_at || ticket.created_at, lang)}
                    </small>
                  </div>
                  <span className={`status-badge ${ticket.status}`}>
                    {t(ticket.status)}
                  </span>
                  <ArrowRight size={18} />
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState title={t("noTickets")} action={false} />
          )
        }
      </ResourceState>
      {open && (
        <Modal title={t("newTicket")} onClose={() => !busy && setOpen(false)}>
          <form
            className="stack-form"
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError(null);
              try {
                const ticket = await api("/support/tickets", {
                  token,
                  method: "POST",
                  body: form,
                });
                setOpen(false);
                navigate(`/support/${ticket.id}`);
              } catch (error) {
                setError(error);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              {t("subject")}
              <input
                required
                minLength={3}
                maxLength={180}
                value={form.subject}
                onChange={(e) => setForm({ ...form, subject: e.target.value })}
              />
            </label>
            <label>
              {t("message")}
              <textarea
                required
                minLength={5}
                maxLength={5000}
                rows={5}
                value={form.body}
                onChange={(e) => setForm({ ...form, body: e.target.value })}
              />
            </label>
            <label>
              {t("priority")}
              <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                {["P1", "P2", "P3"].map((priority) => (
                  <option value={priority} key={priority}>{priority} · {t(`priority${priority}`)}</option>
                ))}
              </select>
            </label>
            <FormError error={error} />
            <button className="button primary" disabled={busy}>
              {t(busy ? "sending" : "sendMessage")}
              <Send size={17} />
            </button>
          </form>
        </Modal>
      )}
    </div>
  );
}
export function SupportDetail() {
  const { id } = useParams();
  const { t, lang, token, user } = useApp();
  const resource = useResource(`/support/tickets/${id}`, { auth: true });
  const [body, setBody] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [older, setOlder] = useState([]);
  const [acknowledge, setAcknowledge] = useState(true);
  const changeStatus = async (status) => {
    setBusy(true);
    setError(null);
    try {
      await api(`/support/tickets/${id}/status`, {
        token,
        method: "PATCH",
        body: { status },
      });
      resource.reload();
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="page-container support-detail">
      <Link className="back-link" to="/support">
        <ArrowLeft size={16} />
        {t("support")}
      </Link>
      <ResourceState resource={resource}>
        {(ticket) => (
          <>
            <PageHeading eyebrow={t("support")} title={ticket.subject}>
              <span className={`status-badge ${ticket.status}`}>
                {t(ticket.status)}
              </span>
            </PageHeading>
            <div className="surface info-note">
              <p>{ticket.priority} · {t(`priority${ticket.priority}`)}</p>
              {ticket.response_due_at && <p>{t("responseDue")}: {formatTime(ticket.response_due_at, lang)}</p>}
              {ticket.first_response_at && <p>{t("firstResponse")}: {formatTime(ticket.first_response_at, lang)}</p>}
              {ticket.response_overdue && <p role="status">{t("responseOverdue")}</p>}
              {["vendor", "admin"].includes(user.role) && ticket.user_id !== user.id && ticket.can_acknowledge && (
                <label>{t("priority")}
                  <select value={ticket.priority} disabled={busy} onChange={async (event) => {
                    setBusy(true);
                    setError(null);
                    try {
                      await api(`/support/tickets/${id}/priority`, { token, method: "PATCH", body: { priority: event.target.value } });
                      resource.reload();
                    } catch (error) { setError(error); } finally { setBusy(false); }
                  }}>
                    {["P1", "P2", "P3"].map((priority) => <option value={priority} key={priority}>{priority} · {t(`priority${priority}`)}</option>)}
                  </select>
                </label>
              )}
            </div>
            <div className="surface conversation">
              {ticket.messages_total >
                ticket.messages.length + older.length && (
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    setError(null);
                    try {
                      const remaining =
                        ticket.messages_total -
                        ticket.messages.length -
                        older.length;
                      const result = await api(
                        `/support/tickets/${id}/messages?limit=${Math.min(100, remaining)}&offset=${Math.max(0, remaining - 100)}`,
                        { token },
                      );
                      setOlder((current) => [...result.items, ...current]);
                    } catch (error) {
                      setError(error);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  {t("olderMessages")}
                </button>
              )}
              {[...older, ...ticket.messages].map((message) => (
                <article
                  key={message.id}
                  className={`conversation-message ${message.author_id === user.id ? "own" : ""}`}
                >
                  <div>
                    <strong>{message.author_name}</strong>
                    <span>{t(message.author_role)}</span>
                    <small>{formatTime(message.created_at, lang)}</small>
                  </div>
                  <p>{message.body}</p>
                </article>
              ))}
              <form
                className="stack-form"
                onSubmit={async (e) => {
                  e.preventDefault();
                  setBusy(true);
                  setError(null);
                  try {
                    await api(`/support/tickets/${id}/messages`, {
                      token,
                      method: "POST",
                      body: { body, acknowledge: Boolean(acknowledge && ticket.can_acknowledge && ["vendor", "admin"].includes(user.role) && ticket.user_id !== user.id) },
                    });
                    setBody("");
                    setOlder([]);
                    resource.reload();
                  } catch (error) {
                    setError(error);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                <label>
                  {t("message")}
                  <textarea
                    required
                    minLength={1}
                    maxLength={5000}
                    rows={4}
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                  />
                </label>
                {["vendor", "admin"].includes(user.role) && ticket.user_id !== user.id && ticket.can_acknowledge && (
                  <label className="checkbox-label">
                    <input type="checkbox" checked={acknowledge} onChange={(event) => setAcknowledge(event.target.checked)} />
                    {t("acknowledgeResponse")}
                  </label>
                )}
                <FormError error={error} />
                <div className="button-row">
                  <button
                    className="button primary"
                    disabled={
                      busy || ["resolved", "closed"].includes(ticket.status)
                    }
                  >
                    {t(busy ? "sending" : "sendMessage")}
                    <Send size={17} />
                  </button>
                  {ticket.status === "open" && (
                    <button
                      className="button secondary"
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        changeStatus(
                          ["vendor", "admin"].includes(user.role) &&
                            ticket.user_id !== user.id
                            ? "resolved"
                            : "closed",
                        )
                      }
                    >
                      {t(
                        ["vendor", "admin"].includes(user.role) &&
                          ticket.user_id !== user.id
                          ? "resolved"
                          : "closeTicket",
                      )}
                    </button>
                  )}
                  {["resolved", "closed"].includes(ticket.status) && (
                    <button
                      className="button secondary"
                      type="button"
                      disabled={busy}
                      onClick={() => changeStatus("open")}
                    >
                      {t("reopenTicket")}
                    </button>
                  )}
                  {["vendor", "admin"].includes(user.role) &&
                    ticket.user_id !== user.id &&
                    ticket.status === "open" && (
                      <button
                        className="button secondary"
                        type="button"
                        disabled={busy}
                        onClick={() => changeStatus("in_progress")}
                      >
                        {t("in_progress")}
                      </button>
                    )}
                  {["vendor", "admin"].includes(user.role) &&
                    ticket.user_id !== user.id &&
                    ticket.status === "in_progress" && (
                      <button
                        className="button secondary"
                        type="button"
                        disabled={busy}
                        onClick={() => changeStatus("resolved")}
                      >
                        {t("resolved")}
                      </button>
                    )}
                </div>
              </form>
            </div>
          </>
        )}
      </ResourceState>
    </div>
  );
}
