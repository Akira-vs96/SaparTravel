const API_URL = (import.meta.env.VITE_API_URL || "/api/v1").replace(/\/$/, "");

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
