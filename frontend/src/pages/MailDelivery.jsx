import React, { useState } from "react";
import { RefreshCw } from "lucide-react";
import { api } from "../api";
import { useApp } from "../context";
import { formatTime } from "../i18n";
import { EmptyState, Modal, ResourceState, useResource } from "../components/common";

export default function MailDelivery() {
  const { token, t, lang, notify, errorText } = useApp();
  const resource = useResource("/admin/mail-delivery", { auth: true });
  const [busy, setBusy] = useState("");
  const [mailbox, setMailbox] = useState(null);
  const openMailbox = async () => {
    setBusy("mailbox");
    try { setMailbox(await api("/admin/demo-mailbox", { token })); }
    catch (error) { notify(errorText(error)); }
    finally { setBusy(""); }
  };
  const stateLabel = (state) => t({pending: "mailPending", sent: "mailSent", failed: "mailFailed", cancelled: "mailCancelled"}[state]);
  return (
    <section className="management-section">
      <div className="section-heading">
        <h2>{t("mailDeliveryTitle")}</h2>
        <button type="button" className="button secondary small" onClick={resource.reload}><RefreshCw size={16} />{t("refresh")}</button>
      </div>
      <ResourceState resource={resource}>{(data) => <>
        <div className="surface">
          <h3>{t(data.mode === "smtp" ? "mailModeEmail" : data.mode === "local" ? "mailModeLocal" : "mailModeDisabled")}</h3>
          {data.mode !== "smtp" && <p>{t("mailConfigurationHelp")}</p>}
          {data.from_address && <p>{data.from_address}</p>}
          {data.local_mailbox_enabled && <button type="button" className="button secondary" disabled={busy === "mailbox"} onClick={openMailbox}>{t("mailOpenLocal")}</button>}
        </div>
        <div className="metric-grid">
          {Object.entries(data.counts).map(([state, count]) => <div className="surface" key={state}><p>{stateLabel(state)}</p><strong>{count}</strong></div>)}
        </div>
        {data.items.length ? <div className="table-wrapper"><table>
          <thead><tr><th>{t("mailRecipient")}</th><th>{t("mailSubject")}</th><th>{t("status")}</th><th>{t("mailAttempts")}</th><th>{t("date")}</th><th>{t("actions")}</th></tr></thead>
          <tbody>{data.items.map((item) => <tr key={item.id}>
            <td>{item.recipient}</td><td>{item.subject}</td><td>{stateLabel(item.state)}{item.error_code && <small className="muted"> {item.error_code}</small>}</td><td>{item.attempts}</td><td>{formatTime(item.sent_at || item.created_at, lang)}</td>
            <td>{item.state === "failed" && <button type="button" className="button secondary small" disabled={busy === item.id} onClick={async () => {
              setBusy(item.id);
              try { await api(`/admin/mail-delivery/${item.id}/retry`, {token, method: "POST"}); resource.reload(); }
              catch (error) { notify(errorText(error)); }
              finally { setBusy(""); }
            }}>{t("mailRetry")}</button>}</td>
          </tr>)}</tbody>
        </table></div> : <EmptyState title={t("mailEmpty")} action={false} />}
      </>}</ResourceState>
      {mailbox && <Modal title={t("mailModeLocal")} onClose={() => setMailbox(null)}>
        <div className="stack-form">{mailbox.items.length ? mailbox.items.map((item) => {
          const match = item.body.match(/https?:\/\/[^\s]+/);
          let recoveryPath = null;
          if (match) {
            try { const url = new URL(match[0]); if (url.pathname === "/reset-password") recoveryPath = url.pathname + url.search; }
            catch { /* Render the plain text message without an unsafe link. */ }
          }
          return <article className="surface" key={item.id}>
            <h3>{item.subject}</h3><p>{item.recipient} · {formatTime(item.created_at, lang)}</p><pre className="mail-message-body">{item.body}</pre>
            {recoveryPath && <a className="button secondary" href={recoveryPath} target="_blank" rel="noreferrer">{t("mailOpenReset")}</a>}
          </article>;
        }) : <EmptyState title={t("mailEmpty")} action={false} />}</div>
      </Modal>}
    </section>
  );
}
