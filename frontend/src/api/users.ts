import { apiClient } from "./client";
import type { User } from "@/types";

export async function listUsers(): Promise<User[]> {
  const { data } = await apiClient.get<User[]>("/users");
  return data;
}

export async function getUser(id: number): Promise<User> {
  const { data } = await apiClient.get<User>(`/users/${id}`);
  return data;
}

export async function createUser(payload: {
  fullName: string;
  username: string;
  password: string;
  roleId: number;
  telegramHandle?: string;
  groupName?: string;
}): Promise<User> {
  const { data } = await apiClient.post<User>("/users", {
    full_name: payload.fullName,
    username: payload.username,
    password: payload.password,
    role_id: payload.roleId,
    telegram_handle: payload.telegramHandle,
    group_name: payload.groupName,
  });
  return data;
}

export async function updateUser(
  id: number,
  payload: {
    fullName?: string;
    username?: string;
    telegramHandle?: string;
    roleId?: number;
    isActive?: boolean;
    groupName?: string;
  }
): Promise<User> {
  const { data } = await apiClient.patch<User>(`/users/${id}`, {
    full_name: payload.fullName,
    username: payload.username,
    telegram_handle: payload.telegramHandle,
    role_id: payload.roleId,
    is_active: payload.isActive,
    group_name: payload.groupName,
  });
  return data;
}

export async function resetPassword(
  id: number,
  newPassword: string
): Promise<void> {
  await apiClient.post(`/users/${id}/reset-password`, { new_password: newPassword });
}

export async function generateLinkToken(): Promise<{ token: string; instructions: string }> {
  const { data } = await apiClient.get("/users/me/link-token");
  return data;
}
