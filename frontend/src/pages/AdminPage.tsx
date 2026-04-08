import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Shield, UserPlus, Users } from "lucide-react";
import { apiClient } from "@/api/client";
import { useAuthStore } from "@/store/auth";
import { Navigate } from "react-router-dom";
import type { User } from "@/types";
import { UserModal } from "@/components/modals/UserModal";

async function listUsers(): Promise<User[]> {
  const { data } = await apiClient.get<User[]>("/users");
  return data;
}

function RoleBadge({ roleName }: { roleName: string }) {
  const colors: Record<string, string> = {
    ADMIN: "badge-red",
    COORDINATOR: "badge-blue",
    GROUP_LEAD: "badge-yellow",
    USER: "badge-slate",
  };
  return <span className={colors[roleName] ?? "badge-slate"}>{roleName}</span>;
}

export function AdminPage() {
  const user = useAuthStore((s) => s.user);
  const [createOpen, setCreateOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);

  if (!user?.role.canManageUsers) {
    return <Navigate to="/dashboard" replace />;
  }

  const { data: users = [], isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: listUsers,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Shield className="h-6 w-6 text-brand-600" />
            Admin
          </h1>
        </div>
        <button className="btn-primary" onClick={() => setCreateOpen(true)}>
          <UserPlus className="h-4 w-4" />
          Create user
        </button>
      </div>

      <div>
        <h2 className="text-base font-semibold text-slate-900 mb-3 flex items-center gap-2">
          <Users className="h-4 w-4 text-slate-500" />
          Users ({users.length})
        </h2>

        <div className="card overflow-hidden">
          <table className="min-w-full divide-y divide-slate-100">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wide">Name</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wide">Username</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wide">Role</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wide">Telegram</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase tracking-wide">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {isLoading ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-sm text-slate-400">
                    Loading…
                  </td>
                </tr>
              ) : (
                users.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3 text-sm font-medium text-slate-900">{u.fullName}</td>
                    <td className="px-4 py-3 text-sm text-slate-500">{u.username}</td>
                    <td className="px-4 py-3">
                      <RoleBadge roleName={u.role.name} />
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-500">
                      {u.telegramHandle ? (
                        <span className="text-brand-600">@{u.telegramHandle}</span>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={u.isActive ? "badge-green" : "badge-red"}>
                        {u.isActive ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        className="text-xs text-slate-500 hover:text-slate-900"
                        onClick={() => setEditingUser(u)}
                      >
                        Edit
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      {createOpen && <UserModal onClose={() => setCreateOpen(false)} />}
      {editingUser && <UserModal user={editingUser} onClose={() => setEditingUser(null)} />}
    </div>
  );
}
