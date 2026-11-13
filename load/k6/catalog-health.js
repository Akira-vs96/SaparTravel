import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    catalog: {
      executor: "constant-arrival-rate",
      rate: Number(__ENV.K6_RATE || 20),
      timeUnit: "1s",
      duration: __ENV.K6_DURATION || "30s",
      preAllocatedVUs: 10,
      maxVUs: 50,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500"],
  },
};

export default function () {
  const baseUrl = __ENV.BASE_URL || "http://localhost:8000";
  const path = __ENV.K6_PATH || "/api/v1/catalog";
  const response = http.get(`${baseUrl}${path}`);
  check(response, {
    "health returns 200": (r) => r.status === 200,
    "health returns JSON": (r) =>
      String(r.headers["Content-Type"] || "").includes("application/json"),
  });
  sleep(0.01);
}
