import React from "react";
import { priceBreakdown } from "../i18n";

export default function PriceDisplay({ amount, lang, className = "", note }) {
  const price = priceBreakdown(amount, lang);
  return (
    <span className={`price-display ${className}`} title={note}>
      <strong>{price.primary}</strong>
      <small>
        ≈ {price.usd} · {price.rub}
      </small>
    </span>
  );
}
