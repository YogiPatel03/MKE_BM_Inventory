import { apiClient } from "./client";
import type { Bin, Cabinet, Item } from "@/types";

export async function listCabinets(): Promise<Cabinet[]> {
  const { data } = await apiClient.get<Cabinet[]>("/cabinets");
  return data;
}

export async function getCabinet(id: number): Promise<Cabinet> {
  const { data } = await apiClient.get<Cabinet>(`/cabinets/${id}`);
  return data;
}

export async function createCabinet(
  payload: Pick<Cabinet, "name" | "location" | "description">
): Promise<Cabinet> {
  const { data } = await apiClient.post<Cabinet>("/cabinets", payload);
  return data;
}

export async function updateCabinet(
  id: number,
  payload: { name?: string; location?: string | null; description?: string | null }
): Promise<Cabinet> {
  const { data } = await apiClient.patch<Cabinet>(`/cabinets/${id}`, payload);
  return data;
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
