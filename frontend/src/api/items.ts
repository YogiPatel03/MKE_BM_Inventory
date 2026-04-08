import { apiClient } from "./client";
import type { Item } from "@/types";

export async function getItem(id: number): Promise<Item> {
  const { data } = await apiClient.get<Item>(`/items/${id}`);
  return data;
}

export async function createItem(payload: {
  name: string;
  description?: string;
  quantityTotal: number;
  cabinetId: number;
  binId?: number;
  sku?: string;
  condition?: string;
}): Promise<Item> {
  const { data } = await apiClient.post<Item>("/items", {
    name: payload.name,
    description: payload.description,
    quantity_total: payload.quantityTotal,
    cabinet_id: payload.cabinetId,
    bin_id: payload.binId,
    sku: payload.sku,
    condition: payload.condition,
  });
  return data;
}

export async function updateItem(id: number, payload: Partial<Item>): Promise<Item> {
  const { data } = await apiClient.patch<Item>(`/items/${id}`, payload);
  return data;
}
