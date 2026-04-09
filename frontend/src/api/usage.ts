import { apiClient } from "./client";
import type { UsageEvent } from "@/types";

export async function markAsUsed(data: {
  itemId: number;
  quantityUsed: number;
  notes?: string;
}): Promise<UsageEvent> {
  const { data: res } = await apiClient.post("/usage-events", {
    item_id: data.itemId,
    quantity_used: data.quantityUsed,
    notes: data.notes,
  });
  return res;
}
