import { apiClient } from "./client";
import type { Room } from "@/types";

export async function listRooms(): Promise<Room[]> {
  const { data } = await apiClient.get<Room[]>("/rooms");
  return data;
}

export async function getRoom(id: number): Promise<Room> {
  const { data } = await apiClient.get<Room>(`/rooms/${id}`);
  return data;
}

export async function createRoom(payload: {
  name: string;
  description?: string | null;
}): Promise<Room> {
  const { data } = await apiClient.post<Room>("/rooms", payload);
  return data;
}

export async function updateRoom(
  id: number,
  payload: { name?: string; description?: string | null }
): Promise<Room> {
  const { data } = await apiClient.patch<Room>(`/rooms/${id}`, payload);
  return data;
}

export async function deleteRoom(id: number): Promise<void> {
  await apiClient.delete(`/rooms/${id}`);
}
