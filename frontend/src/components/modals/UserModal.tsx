import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { createUser, updateUser } from "@/api/auth";
import type { User } from "@/types";

const ROLES = [
  { id: 1, name: "ADMIN" },
  { id: 2, name: "COORDINATOR" },
  { id: 3, name: "GROUP_LEAD" },
  { id: 4, name: "USER" },
];

interface Props {
  user?: User; // if provided, edit mode
  onClose: () => void;
}

export function UserModal({ user: editUser, onClose }: Props) {
  const qc = useQueryClient();
  const isEdit = !!editUser;

  const [fullName, setFullName] = useState(editUser?.fullName ?? "");
  const [username, setUsername] = useState(editUser?.username ?? "");
  const [password, setPassword] = useState("");
  const [roleId, setRoleId] = useState(editUser?.roleId ?? 4);
  const [telegramHandle, setTelegramHandle] = useState(editUser?.telegramHandle ?? "");
  const [isActive, setIsActive] = useState(editUser?.isActive ?? true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError("");
    try {
      if (isEdit) {
        await updateUser(editUser.id, {
          fullName,
          roleId,
          telegramHandle: telegramHandle || undefined,
          isActive,
        });
      } else {
        await createUser({
          fullName,
          username,
          password,
          roleId,
          telegramHandle: telegramHandle || undefined,
        });
      }
      qc.invalidateQueries({ queryKey: ["users"] });
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to save user");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50">
      <div className="card w-full max-w-md p-6 relative">
        <button onClick={onClose} className="absolute top-4 right-4 text-slate-400 hover:text-slate-700">
          <X className="h-5 w-5" />
        </button>
        <h2 className="text-lg font-semibold text-slate-900 mb-5">
          {isEdit ? "Edit User" : "Create User"}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Full name *</label>
            <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
          </div>
          {!isEdit && (
            <div>
              <label className="label">Username *</label>
              <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} required autoComplete="off" />
            </div>
          )}
          {!isEdit && (
            <div>
              <label className="label">Password *</label>
              <input
                type="password"
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
              />
            </div>
          )}
          <div>
            <label className="label">Role *</label>
            <select className="input" value={roleId} onChange={(e) => setRoleId(Number(e.target.value))}>
              {ROLES.map((r) => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Telegram handle</label>
            <input
              className="input"
              placeholder="@username (without @)"
              value={telegramHandle}
              onChange={(e) => setTelegramHandle(e.target.value.replace(/^@/, ""))}
            />
          </div>
          {isEdit && (
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="is_active"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-brand-600"
              />
              <label htmlFor="is_active" className="text-sm text-slate-700">Active account</label>
            </div>
          )}
          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary flex-1 justify-center">Cancel</button>
            <button type="submit" disabled={isLoading} className="btn-primary flex-1 justify-center">
              {isLoading ? "Saving…" : isEdit ? "Save changes" : "Create user"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
