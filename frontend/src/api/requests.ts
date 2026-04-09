import { apiClient } from "./client";
import type { InventoryRequest } from "@/types";

export async function submitRequest(data: {
  itemId?: number;
  binId?: number;
  quantityRequested?: number;
  reason?: string;
  dueAt?: string;
}): Promise<InventoryRequest> {
  const { data: res } = await apiClient.post("/requests", {
    item_id: data.itemId,
    bin_id: data.binId,
    quantity_requested: data.quantityRequested ?? 1,
    reason: data.reason,
    due_at: data.dueAt,
  });
  return res;
}

export async function listRequests(status?: string): Promise<InventoryRequest[]> {
  const { data } = await apiClient.get("/requests", { params: status ? { status } : undefined });
  return data;
}

export async function approveRequest(
  requestId: number,
  dueAt?: string
): Promise<InventoryRequest> {
  const { data } = await apiClient.post(`/requests/${requestId}/approve`, { due_at: dueAt });
  return data;
}

export async function denyRequest(
  requestId: number,
  denialReason?: string
): Promise<InventoryRequest> {
  const { data } = await apiClient.post(`/requests/${requestId}/deny`, {
    denial_reason: denialReason,
  });
  return data;
}

export async function cancelRequest(requestId: number): Promise<InventoryRequest> {
  const { data } = await apiClient.post(`/requests/${requestId}/cancel`);
  return data;
}
