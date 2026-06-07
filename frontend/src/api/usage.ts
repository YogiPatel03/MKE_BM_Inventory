import { apiClient } from "./client";
import { toUsageEventPayload } from "@/utils/markAsUsedValidation";
import type { UsageEvent } from "@/types";

export async function markAsUsed(data: {
  itemId: number;
  quantityUsed: number;
  notes?: string;
}): Promise<UsageEvent> {
  const { data: res } = await apiClient.post("/usage-events", toUsageEventPayload(data));
  return res;
}
