import { apiClient } from "./client";
import type { Checklist, ChecklistItem, ChecklistSummary, ChecklistAssignment } from "@/types";

export async function listChecklists(params?: {
  groupName?: string;
  weekStart?: string;
}): Promise<ChecklistSummary[]> {
  const { data } = await apiClient.get<ChecklistSummary[]>("/checklists", { params });
  return data;
}

export async function getChecklist(id: number): Promise<Checklist> {
  const { data } = await apiClient.get<Checklist>(`/checklists/${id}`);
  return data;
}

export async function addChecklistItem(
  checklistId: number,
  payload: { title: string; description?: string; itemOrder?: number }
): Promise<ChecklistItem> {
  const { data } = await apiClient.post<ChecklistItem>(
    `/checklists/${checklistId}/items`,
    payload
  );
  return data;
}

export async function completeChecklistItem(
  checklistId: number,
  itemId: number,
  notes?: string
): Promise<ChecklistItem> {
  const { data } = await apiClient.patch<ChecklistItem>(
    `/checklists/${checklistId}/items/${itemId}/complete`,
    { notes }
  );
  return data;
}

export async function deleteChecklistItem(
  checklistId: number,
  itemId: number
): Promise<void> {
  await apiClient.delete(`/checklists/${checklistId}/items/${itemId}`);
}

export async function assignUser(
  checklistId: number,
  userId: number
): Promise<ChecklistAssignment> {
  const { data } = await apiClient.post<ChecklistAssignment>(
    `/checklists/${checklistId}/assign`,
    { user_id: userId }
  );
  return data;
}

export async function unassignUser(
  checklistId: number,
  userId: number
): Promise<void> {
  await apiClient.delete(`/checklists/${checklistId}/assign/${userId}`);
}

export async function backfillActiveTransactions(): Promise<{ created: number; skipped: number }> {
  const { data } = await apiClient.post<{ created: number; skipped: number }>(
    "/checklists/backfill-active-transactions"
  );
  return data;
}
