import { apiClient } from "./client";

export async function resolveQRToken(token: string): Promise<{ type: "item" | "bin"; id: number }> {
  const { data } = await apiClient.get("/qr/resolve", { params: { token } });
  return data;
}

export async function generateItemQR(itemId: number): Promise<{ token: string }> {
  const { data } = await apiClient.post(`/qr/item/${itemId}/generate`);
  return data;
}

export async function generateBinQR(binId: number): Promise<{ token: string }> {
  const { data } = await apiClient.post(`/qr/bin/${binId}/generate`);
  return data;
}
