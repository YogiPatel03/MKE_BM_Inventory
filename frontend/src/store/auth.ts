import { create } from "zustand";
import { getMe, login as apiLogin } from "@/api/auth";
import type { User } from "@/types";

interface AuthState {
  user: User | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  hydrate: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isLoading: true,

  login: async (username, password) => {
    const token = await apiLogin({ username, password });
    localStorage.setItem("access_token", token);
    const user = await getMe();
    set({ user });
  },

  logout: () => {
    localStorage.removeItem("access_token");
    set({ user: null });
  },

  hydrate: async () => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      set({ isLoading: false });
      return;
    }
    try {
      const user = await getMe();
      set({ user, isLoading: false });
    } catch {
      localStorage.removeItem("access_token");
      set({ user: null, isLoading: false });
    }
  },
}));
