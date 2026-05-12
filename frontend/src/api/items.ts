import { apiClient } from "./client";
import type { Item } from "@/types";
import {
  toItemCreateApiPayload,
  toItemUpdateApiPayload,
  type ItemCreatePayload,
  type ItemUpdatePayload,
} from "./itemPayloads";

export async function listItems(params?: {
  cabinetId?: number;
  binId?: number;
  search?: string;
  isActive?: boolean;
  skip?: number;
  limit?: number;
}): Promise<Item[]> {
  const { data } = await apiClient.get<Item[]>("/items", {
    params: {
      cabinet_id: params?.cabinetId,
      bin_id: params?.binId,
      search: params?.search,
      is_active: params?.isActive ?? true,
      skip: params?.skip,
      limit: params?.limit,
    },
  });
  return data;
}

export async function getItem(id: number): Promise<Item> {
  const { data } = await apiClient.get<Item>(`/items/${id}`);
  return data;
}

export async function createItem(payload: ItemCreatePayload): Promise<Item> {
  const { data } = await apiClient.post<Item>("/items", toItemCreateApiPayload(payload));
  return data;
}

export async function updateItem(
  id: number,
  payload: ItemUpdatePayload
): Promise<Item> {
  const { data } = await apiClient.patch<Item>(`/items/${id}`, toItemUpdateApiPayload(payload));
  return data;
}
