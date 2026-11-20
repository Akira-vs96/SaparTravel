import React, { useEffect, useRef, useState } from "react";
import { LoaderCircle, RotateCcw, Send, Sparkles } from "lucide-react";
import { api } from "../api";
import { useApp } from "../context";
import { PageHeading } from "../components/common";
import TourCard from "../components/TourCard";

const suggestions = [
  "assistantPromptBudget",
  "assistantPromptNature",
  "assistantPromptBeach",
];

export default function Assistant() {
  const { lang, t, errorText } = useApp();
  const [messages, setMessages] = useState([
    { id: "welcome", role: "assistant", welcome: true },
  ]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  const reset = () => {
    setMessages([{ id: "welcome", role: "assistant", welcome: true }]);
    setDraft("");
    inputRef.current?.focus();
  };

  const send = async (value = draft) => {
    const content = value.trim();
    if (!content || busy) return;
    const userMessage = {
      id: `${Date.now()}-user`,
      role: "user",
      content,
    };
    const history = [
      ...messages
        .filter((message) => !message.welcome)
        .map(({ role, content: text }) => ({ role, content: text })),
      { role: "user", content },
    ].slice(-10);
    while (history[0]?.role === "assistant") history.shift();
    setMessages((current) => [...current, userMessage]);
    setDraft("");
    setBusy(true);
    try {
      const data = await api("/travel-assistant/chat", {
        method: "POST",
        body: { lang, messages: history },
      });
      setMessages((current) => [
        ...current,
        {
          id: `${Date.now()}-assistant`,
          role: "assistant",
          content: data.reply,
          items: data.items || [],
          search: Boolean(data.search),
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: `${Date.now()}-assistant-error`,
          role: "assistant",
          content: error.status ? error.message : errorText(error),
          error: true,
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-container assistant-page">
      <PageHeading
        eyebrow="SAPAR / GEMINI"
        title={t("assistantTitle")}
        text={t("assistantIntro")}
      />
      <p className="assistant-disclosure">{t("assistantPrivacy")}</p>

      <section className="surface assistant-panel" aria-label={t("assistantTitle")}>
        <div className="assistant-panel-heading">
          <div className="assistant-identity">
            <span className="assistant-mark"><Sparkles size={19} /></span>
            <div>
              <strong>{t("assistantNav")}</strong>
              <small>Gemini · SaparTravel</small>
            </div>
          </div>
          <button className="button secondary small" type="button" onClick={reset} disabled={busy}>
            <RotateCcw size={15} /> {t("assistantNewChat")}
          </button>
        </div>

        <div className="assistant-messages" aria-live="polite" aria-relevant="additions text">
          {messages.map((message) => (
            <div className={`assistant-turn ${message.role}`} key={message.id}>
              {message.welcome ? (
                <div className="assistant-bubble">{t("assistantWelcome")}</div>
              ) : (
                <>
                  <div className={`assistant-bubble${message.error ? " is-error" : ""}`}>
                    {message.content}
                  </div>
                  {message.items?.length > 0 && (
                    <div className="assistant-results">
                      <h2>{t("assistantToursFound")}</h2>
                      <div className="tour-grid">
                        {message.items.map((tour) => <TourCard key={tour.id} tour={tour} />)}
                      </div>
                    </div>
                  )}
                  {message.search && message.items?.length === 0 && (
                    <p className="assistant-no-matches">{t("assistantNoMatches")}</p>
                  )}
                </>
              )}
            </div>
          ))}
          {busy && (
            <div className="assistant-turn assistant" role="status">
              <div className="assistant-bubble assistant-loading">
                <LoaderCircle className="spin" size={17} /> {t("assistantThinking")}
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {messages.length === 1 && (
          <div className="assistant-suggestions" aria-label={t("assistantTitle")}>
            {suggestions.map((key) => (
              <button key={key} type="button" onClick={() => send(t(key))} disabled={busy}>
                {t(key)}
              </button>
            ))}
          </div>
        )}

        <form
          className="assistant-composer"
          onSubmit={(event) => {
            event.preventDefault();
            send();
          }}
        >
          <textarea
            ref={inputRef}
            value={draft}
            onChange={(event) => setDraft(event.target.value.slice(0, 1200))}
            placeholder={t("assistantPlaceholder")}
            maxLength={1200}
            rows={2}
            disabled={busy}
            aria-label={t("assistantPlaceholder")}
          />
          <button className="button primary" type="submit" disabled={busy || !draft.trim()}>
            <Send size={17} /> {t("assistantSend")}
          </button>
        </form>
      </section>
    </div>
  );
}
