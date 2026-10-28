import axios from "axios";
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "",
  timeout: 15000,
});
api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("atlas_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const body = error.response?.data;
    return (
      body?.error?.details
        ?.map((detail: { message: string }) => detail.message)
        .join("; ") ||
      body?.error?.message ||
      (typeof body?.detail === "string"
        ? body.detail
        : body?.detail
          ? "Please check the form values."
          : error.message)
    );
  }
  return String(error);
}
export async function download(jobId: string, format: "csv" | "json") {
  const response = await api.get(`/api/scraping/jobs/${jobId}/export`, {
    params: { format },
    responseType: "blob",
  });
  const url = URL.createObjectURL(response.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = `atlas-${jobId}.${format}`;
  a.click();
  URL.revokeObjectURL(url);
}
