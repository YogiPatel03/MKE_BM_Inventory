import { apiClient } from "./client";
import type { ActivityLog, ActivityType } from "@/types";

export interface ListActivityParams {
  activityType?: ActivityType | "";
  itemId?: number;
  actorId?: number;
  since?: string;
  skip?: number;
  limit?: number;
}

export async function listActivity(params: ListActivityParams = {}): Promise<ActivityLog[]> {
  const { data } = await apiClient.get<ActivityLog[]>("/activity", {
    params: {
      activity_type: params.activityType || undefined,
      item_id: params.itemId,
      actor_id: params.actorId,
      since: params.since,
      skip: params.skip,
      limit: params.limit ?? 100,
    },
  });
  return data;
}

export async function listActivityTypes(): Promise<string[]> {
  const { data } = await apiClient.get<string[]>("/activity/types");
  return data;
}
