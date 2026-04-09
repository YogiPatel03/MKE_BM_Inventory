import { apiClient } from "./client";
import type { StockAdjustment } from "@/types";

export async function adjustStock(data: {
  itemId: number;
  delta: number;
  reason?: string;
  notes?: string;
}): Promise<StockAdjustment> {
  const { data: res } = await apiClient.post("/stock-adjustments", {
    item_id: data.itemId,
    delta: data.delta,
    reason: data.reason ?? "CORRECTION",
    notes: data.notes,
  });
  return res;
}

export async function getAdjustmentsForItem(itemId: number): Promise<StockAdjustment[]> {
  const { data } = await apiClient.get(`/stock-adjustments/item/${itemId}`);
  return data;
}
