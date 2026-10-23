const API_URL = (import.meta.env.VITE_API_URL || "/api/v1").replace(/\/$/, "");
export async function download(path, token, filename) {
  let response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    const error = new Error("network");
    error.code = "network";
    throw error;
  }
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    error.status = response.status;
    if (response.status === 401 && token)
      window.dispatchEvent(
        new CustomEvent("sapar:unauthorized", { detail: { token } }),
      );
    throw error;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function api(path, { token, body, headers, ...options } = {}) {
  let response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    const networkError = new Error("network");
    networkError.code = "network";
    throw networkError;
  }
  const data =
    response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail
          .map((item) => `${item.loc?.slice(1).join(".") || ""}: ${item.msg}`)
          .join("; ")
      : typeof detail === "string"
        ? detail
        : `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.fields = data?.errors || (Array.isArray(detail) ? detail : []);
    error.errors = error.fields;
    if (response.status === 401 && token) {
      window.dispatchEvent(
        new CustomEvent("sapar:unauthorized", { detail: { token } }),
      );
    }
    throw error;
  }
  return data;
}

export function queryString(values) {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== "" && value !== undefined && value !== null)
      query.set(key, value);
  });
  return query.toString();
}
