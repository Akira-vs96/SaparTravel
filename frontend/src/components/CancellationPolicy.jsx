import React from "react";
import { useApp } from "../context";
export default function CancellationPolicy({ policy }) {
  const { t } = useApp();
  const rules = [...(policy?.rules || [])].sort(
    (a, b) => b.days_before - a.days_before,
  );
  return (
    <div className="cancellation-rules">
      {rules.length ? (
        <>
          <p className="muted">{t("policyDemo")}</p>
          <ul>
            {rules.map((rule, index) => (
              <li key={rule.days_before}>
                <span>
                  {index === 0
                    ? `${rule.days_before}+`
                    : `${rule.days_before}–${rules[index - 1].days_before - 1}`}{" "}
                  {t("daysBefore").toLowerCase()}
                </span>
                <strong>
                  {rule.refund_percent}% {t("refund").toLowerCase()}
                </strong>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p>{t("policyText")}</p>
      )}
    </div>
  );
}
export function refundPercent(booking) {
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Almaty",
  }).format(new Date());
  const days = Math.floor(
    (Date.parse(booking.start_date) - Date.parse(today)) / 86400000,
  );
  return (
    [...(booking.cancellation_policy?.rules || [])]
      .sort((a, b) => b.days_before - a.days_before)
      .find((rule) => days >= rule.days_before)?.refund_percent || 0
  );
}
