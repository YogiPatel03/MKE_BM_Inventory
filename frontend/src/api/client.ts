import axios from "axios";
import camelcaseKeys from "camelcase-keys";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export const apiClient = axios.create({
  baseURL: `${BASE_URL}/api`,
  headers: { "Content-Type": "application/json" },
});

// Attach JWT from localStorage to every request
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Convert snake_case API responses to camelCase, redirect to login on 401
apiClient.interceptors.response.use(
  (r) => {
    if (r.data && typeof r.data === "object") {
      r.data = camelcaseKeys(r.data, { deep: true });
    }
    return r;
  },
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);
