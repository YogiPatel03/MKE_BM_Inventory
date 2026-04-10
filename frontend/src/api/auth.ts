import { apiClient } from "./client";
import type { User } from "@/types";

export interface LoginPayload {
  username: string;
  password: string;
}

export async function login(payload: LoginPayload): Promise<string> {
  const { data } = await apiClient.post<{ accessToken: string }>("/auth/login", payload);
  return data.accessToken;
}

export async function getMe(): Promise<User> {
  const { data } = await apiClient.get<User>("/auth/me");
  return data;
}

export async function createUser(payload: {
  fullName: string;
  username: string;
  password: string;
  roleId: number;
  telegramHandle?: string;
  groupName?: string | null;
}): Promise<User> {
  const { data } = await apiClient.post<User>("/users", {
    full_name: payload.fullName,
    username: payload.username,
    password: payload.password,
    role_id: payload.roleId,
    telegram_handle: payload.telegramHandle || null,
    group_name: payload.groupName ?? null,
  });
  return data;
}

export async function updateUser(
  userId: number,
  payload: { fullName?: string; username?: string; roleId?: number; telegramHandle?: string; isActive?: boolean; groupName?: string | null }
): Promise<User> {
  const { data } = await apiClient.patch<User>(`/users/${userId}`, {
    full_name: payload.fullName,
    username: payload.username,
    role_id: payload.roleId,
    telegram_handle: payload.telegramHandle,
    is_active: payload.isActive,
    group_name: payload.groupName,
  });
  return data;
}

export async function resetUserPassword(userId: number, newPassword: string): Promise<void> {
  await apiClient.post(`/users/${userId}/reset-password`, { new_password: newPassword });
}

export async function listRoles(): Promise<{ id: number; name: string }[]> {
  const { data } = await apiClient.get<{ id: number; name: string }[]>("/roles");
  return data;
}
