import { apiClient } from "./client";
import type { Bin, Cabinet, Item } from "@/types";

export async function listCabinets(roomId?: number): Promise<Cabinet[]> {
  const params = roomId ? { room_id: roomId } : {};
  const { data } = await apiClient.get<Cabinet[]>("/cabinets", { params });
  return data;
}

export async function getCabinet(id: number): Promise<Cabinet> {
  const { data } = await apiClient.get<Cabinet>(`/cabinets/${id}`);
  return data;
}

export async function createCabinet(payload: {
  name: string;
  roomId: number;
  location?: string | null;
  description?: string | null;
}): Promise<Cabinet> {
  const { data } = await apiClient.post<Cabinet>("/cabinets", {
    name: payload.name,
    room_id: payload.roomId,
    location: payload.location,
    description: payload.description,
  });
  return data;
}

export async function updateCabinet(
  id: number,
  payload: { name?: string; location?: string | null; description?: string | null; roomId?: number }
): Promise<Cabinet> {
  const { data } = await apiClient.patch<Cabinet>(`/cabinets/${id}`, {
    name: payload.name,
    location: payload.location,
    description: payload.description,
    room_id: payload.roomId,
  });
  return data;
}

export async function deleteCabinet(id: number): Promise<void> {
  await apiClient.delete(`/cabinets/${id}`);
}

export async function createBin(payload: {
  label: string;
  cabinetId: number;
  groupNumber?: number;
  locationNote?: string;
  description?: string;
}): Promise<Bin> {
  const { data } = await apiClient.post<Bin>("/bins", {
    label: payload.label,
    cabinet_id: payload.cabinetId,
    group_number: payload.groupNumber,
    location_note: payload.locationNote,
    description: payload.description,
  });
  return data;
}

export async function listBins(cabinetId?: number): Promise<Bin[]> {
  const params = cabinetId ? { cabinet_id: cabinetId } : {};
  const { data } = await apiClient.get<Bin[]>("/bins", { params });
  return data;
}

export async function listItems(params: {
  cabinet_id?: number;
  bin_id?: number;
  search?: string;
  skip?: number;
  limit?: number;
}): Promise<Item[]> {
  const { data } = await apiClient.get<Item[]>("/items", { params });
  return data;
}
