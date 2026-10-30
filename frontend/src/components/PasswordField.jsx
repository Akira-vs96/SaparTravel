import React, { useId, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { useApp } from "../context";

export default function PasswordField({ label, hint, ...props }) {
  const { t } = useApp();
  const id = useId();
  const [visible, setVisible] = useState(false);
  return (
    <div className="password-field">
      <label htmlFor={id}>{label}</label>
      <div className="password-input-wrap">
        <input {...props} id={id} type={visible ? "text" : "password"} aria-describedby={hint ? `${id}-hint` : undefined} />
        <button type="button" className="icon-button password-visibility" aria-label={t(visible ? "hidePassword" : "showPassword")} aria-pressed={visible} onClick={() => setVisible(!visible)}>
          {visible ? <EyeOff size={19} /> : <Eye size={19} />}
        </button>
      </div>
      {hint && <small id={`${id}-hint`}>{hint}</small>}
    </div>
  );
}
