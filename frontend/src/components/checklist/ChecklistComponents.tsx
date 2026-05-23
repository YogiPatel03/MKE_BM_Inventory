import { useState } from "react";
import { useQuery, useMutation, useQueryClient, QueryClient } from "@tanstack/react-query";
import {
  Check,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Folder,
  Plus,
  Trash2,
  UserPlus,
  X,
} from "lucide-react";
import { toast } from "@/store/toast";
import { ConfirmModal } from "@/components/modals/ConfirmModal";
import {
  getChecklist,
  addChecklistItem,
  completeChecklistItem,
  incompleteChecklistItem,
  deleteChecklistItem,
  assignUser,
  unassignUser,
  createSubchecklist,
  listChecklistDefaults,
  addChecklistDefault,
  removeChecklistDefault,
} from "@/api/checklists";
import { listUsers } from "@/api/users";
import { useAuthStore } from "@/store/auth";
import { formatSabhaDate } from "@/utils/checklistDateHelpers";
import type {
  Checklist,
  ChecklistAssignmentDefault,
  ChecklistItem,
  ChecklistSummary,
  GroupName,
  Subchecklist,
} from "@/types";
import { GROUP_DISPLAY } from "@/types";

// ── Query invalidation helper ─────────────────────────────────────────────────
// Invalidates both the detail cache and the list summary cache so Dashboard
// cards (which read from the list query) stay fresh after any mutation.

function invalidateChecklist(qc: QueryClient, checklistId: number) {
  qc.invalidateQueries({ queryKey: ["checklist", checklistId] });
  qc.invalidateQueries({ queryKey: ["checklists"] });
}

// ── Permission hooks ──────────────────────────────────────────────────────────

export function useCanManage() {
  const user = useAuthStore((s) => s.user);
  return (user?.role.canManageUsers || user?.role.canManageInventory) ?? false;
}

function useCanAddItems() {
  const user = useAuthStore((s) => s.user);
  return (
    (user?.role.canManageUsers ||
      user?.role.canManageInventory ||
      user?.role.canApproveRequests) ?? false
  );
}

function useCanAssign() {
  const user = useAuthStore((s) => s.user);
  return (
    (user?.role.canManageUsers ||
      user?.role.canManageInventory ||
      user?.role.canApproveRequests) ?? false
  );
}

export function useCanManageDefaults(groupName: GroupName): boolean {
  const user = useAuthStore((s) => s.user);
  if (!user) return false;
  if (user.role.canManageUsers || user.role.canManageInventory) return true;
  return user.role.canApproveRequests && user.groupName === groupName;
}

export function useIsAdminOrCoordinator(): boolean {
  const user = useAuthStore((s) => s.user);
  if (!user) return false;
  return user.role.canManageUsers || user.role.canManageInventory;
}

// ── Add Item Modal ────────────────────────────────────────────────────────────

function AddItemModal({
  checklistId,
  subchecklists,
  assignees,
  onClose,
}: {
  checklistId: number;
  subchecklists: Subchecklist[];
  assignees: { id: number; fullName: string }[];
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [assigneeId, setAssigneeId] = useState<number | "">("");
  const [subchecklistId, setSubchecklistId] = useState<number | "">("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await addChecklistItem(checklistId, {
        title: title.trim(),
        description: description.trim() || undefined,
        assigneeId: assigneeId ? Number(assigneeId) : undefined,
        subchecklistId: subchecklistId ? Number(subchecklistId) : undefined,
      });
      invalidateChecklist(qc, checklistId);
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to add item");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50">
      <div className="card w-full max-w-md p-6 relative">
        <button onClick={onClose} className="absolute top-4 right-4 text-slate-400 hover:text-slate-700">
          <X className="h-5 w-5" />
        </button>
        <h2 className="text-lg font-semibold text-slate-900 mb-5">Add Checklist Task</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Task Title *</label>
            <input
              className="input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Check lighting equipment"
              required
            />
          </div>
          <div>
            <label className="label">Description</label>
            <textarea
              className="input resize-none"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional details"
            />
          </div>
          {subchecklists.length > 0 && (
            <div>
              <label className="label">Section</label>
              <select
                className="input"
                value={subchecklistId}
                onChange={(e) => setSubchecklistId(e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">No section (top level)</option>
                {subchecklists.map((s) => (
                  <option key={s.id} value={s.id}>{s.title}</option>
                ))}
              </select>
            </div>
          )}
          <div>
            <label className="label">Assign to</label>
            <select
              className="input"
              value={assigneeId}
              onChange={(e) => setAssigneeId(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">Everyone</option>
              {assignees.map((u) => (
                <option key={u.id} value={u.id}>{u.fullName}</option>
              ))}
            </select>
            <p className="text-xs text-slate-500 mt-1">
              Leave blank to assign to everyone — one completion counts.
            </p>
          </div>
          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary flex-1 justify-center">Cancel</button>
            <button type="submit" disabled={loading} className="btn-primary flex-1 justify-center">
              {loading ? "Adding…" : "Add task"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Add Subchecklist Modal ────────────────────────────────────────────────────

function AddSubchecklistModal({ checklistId, onClose }: { checklistId: number; onClose: () => void }) {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await createSubchecklist(checklistId, { title: title.trim() });
      invalidateChecklist(qc, checklistId);
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to create section");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50">
      <div className="card w-full max-w-sm p-6 relative">
        <button onClick={onClose} className="absolute top-4 right-4 text-slate-400 hover:text-slate-700">
          <X className="h-5 w-5" />
        </button>
        <h2 className="text-lg font-semibold text-slate-900 mb-4">Add Custom Section</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Section Name *</label>
            <input
              className="input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Setup, Cleanup, Special Tasks"
              required
              autoFocus
            />
          </div>
          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary flex-1 justify-center">Cancel</button>
            <button type="submit" disabled={loading} className="btn-primary flex-1 justify-center">
              {loading ? "Creating…" : "Create section"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Complete Item Modal ───────────────────────────────────────────────────────

function CompleteModal({
  item,
  checklistId,
  onClose,
}: {
  item: ChecklistItem;
  checklistId: number;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await completeChecklistItem(checklistId, item.id, notes.trim() || undefined);
      invalidateChecklist(qc, checklistId);
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to complete item");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50">
      <div className="card w-full max-w-md p-6 relative">
        <button onClick={onClose} className="absolute top-4 right-4 text-slate-400 hover:text-slate-700">
          <X className="h-5 w-5" />
        </button>
        <h2 className="text-lg font-semibold text-slate-900 mb-2">Complete Task</h2>
        <p className="text-sm text-slate-600 mb-5">{item.title}</p>
        {item.isAutoGenerated && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-sm text-amber-800 mb-4">
            A photo proof request will be sent to the Telegram group chat.
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Notes (optional)</label>
            <textarea
              className="input resize-none"
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Any notes about completion…"
            />
          </div>
          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary flex-1 justify-center">Cancel</button>
            <button type="submit" disabled={loading} className="btn-primary flex-1 justify-center bg-green-600 hover:bg-green-700">
              {loading ? "Saving…" : "Mark complete"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Assign User Modal (This week + Every week tabs) ───────────────────────────

function AssignModal({
  checklist,
  onClose,
}: {
  checklist: Checklist;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const canManageDefaults = useCanManageDefaults(checklist.groupName);
  const isAdminOrCoordinator = useIsAdminOrCoordinator();

  const [activeTab, setActiveTab] = useState<"thisWeek" | "everyWeek">("thisWeek");

  const [weeklyUserId, setWeeklyUserId] = useState<number | "">("");
  const [weeklyLoading, setWeeklyLoading] = useState(false);
  const [weeklyError, setWeeklyError] = useState("");

  const [defaultUserId, setDefaultUserId] = useState<number | "">("");
  const [defaultLoading, setDefaultLoading] = useState(false);
  const [defaultError, setDefaultError] = useState("");

  const { data: allUsers = [] } = useQuery({
    queryKey: ["users"],
    queryFn: listUsers,
  });

  const { data: defaults = [], isLoading: defaultsLoading } = useQuery({
    queryKey: ["checklist-defaults", checklist.groupName],
    queryFn: () => listChecklistDefaults(checklist.groupName),
    enabled: canManageDefaults,
  });

  const assignedIds = new Set(checklist.assignments.map((a) => a.userId));
  const availableForWeek = allUsers.filter((u) => u.isActive && !assignedIds.has(u.id));

  const defaultUserIds = new Set(defaults.map((d: ChecklistAssignmentDefault) => d.userId));
  const availableForDefault = allUsers.filter((u) => {
    if (!u.isActive || defaultUserIds.has(u.id)) return false;
    if (!isAdminOrCoordinator) return u.groupName === checklist.groupName;
    return true;
  });

  const handleWeeklyAssign = async () => {
    if (!weeklyUserId) return;
    setWeeklyLoading(true);
    setWeeklyError("");
    try {
      await assignUser(checklist.id, weeklyUserId as number);
      invalidateChecklist(qc, checklist.id);
      setWeeklyUserId("");
    } catch (e: any) {
      setWeeklyError(e?.response?.data?.detail ?? "Failed to assign user");
    } finally {
      setWeeklyLoading(false);
    }
  };

  const handleWeeklyUnassign = async (uid: number) => {
    setWeeklyError("");
    try {
      await unassignUser(checklist.id, uid);
      invalidateChecklist(qc, checklist.id);
    } catch (e: any) {
      setWeeklyError(e?.response?.data?.detail ?? "Failed to unassign user");
    }
  };

  const handleAddDefault = async () => {
    if (!defaultUserId) return;
    setDefaultLoading(true);
    setDefaultError("");
    try {
      await addChecklistDefault(checklist.groupName, defaultUserId as number);
      qc.invalidateQueries({ queryKey: ["checklist-defaults", checklist.groupName] });
      setDefaultUserId("");
    } catch (e: any) {
      setDefaultError(e?.response?.data?.detail ?? "Failed to add recurring assignee");
    } finally {
      setDefaultLoading(false);
    }
  };

  const handleRemoveDefault = async (d: ChecklistAssignmentDefault) => {
    setDefaultError("");
    try {
      await removeChecklistDefault(d.id);
      qc.invalidateQueries({ queryKey: ["checklist-defaults", checklist.groupName] });
    } catch (e: any) {
      setDefaultError(e?.response?.data?.detail ?? "Failed to remove recurring assignee");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50">
      <div className="card w-full max-w-md p-6 relative">
        <button onClick={onClose} className="absolute top-4 right-4 text-slate-400 hover:text-slate-700">
          <X className="h-5 w-5" />
        </button>
        <h2 className="text-lg font-semibold text-slate-900 mb-4">Manage Assignments</h2>

        {canManageDefaults && (
          <div className="flex gap-1 bg-slate-100 rounded-lg p-1 mb-4">
            <button
              onClick={() => setActiveTab("thisWeek")}
              className={`flex-1 py-1.5 text-sm rounded-md transition-colors ${
                activeTab === "thisWeek"
                  ? "bg-white shadow-sm font-medium text-slate-900"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              This week only
            </button>
            <button
              onClick={() => setActiveTab("everyWeek")}
              className={`flex-1 py-1.5 text-sm rounded-md transition-colors ${
                activeTab === "everyWeek"
                  ? "bg-white shadow-sm font-medium text-slate-900"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Every week
            </button>
          </div>
        )}

        {(!canManageDefaults || activeTab === "thisWeek") && (
          <div className="space-y-3">
            {canManageDefaults && (
              <p className="text-xs text-slate-500 bg-slate-50 rounded-lg px-3 py-2">
                Changes here affect only this Sabha checklist.
              </p>
            )}

            {checklist.assignments.length > 0 && (
              <div>
                <p className="text-xs text-slate-500 uppercase font-medium mb-2">Currently assigned</p>
                <div className="space-y-1">
                  {checklist.assignments.map((a) => (
                    <div key={a.id} className="flex items-center justify-between py-1.5 px-2 rounded-lg bg-slate-50">
                      <span className="text-sm text-slate-800">{a.user.fullName}</span>
                      <button
                        onClick={() => handleWeeklyUnassign(a.userId)}
                        className="text-slate-400 hover:text-red-600 p-0.5"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {availableForWeek.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs text-slate-500 uppercase font-medium">Add assignee</p>
                <select
                  className="input"
                  value={weeklyUserId}
                  onChange={(e) => setWeeklyUserId(e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">Select user…</option>
                  {availableForWeek.map((u) => (
                    <option key={u.id} value={u.id}>{u.fullName} ({u.username})</option>
                  ))}
                </select>
                <button
                  onClick={handleWeeklyAssign}
                  disabled={!weeklyUserId || weeklyLoading}
                  className="btn-primary w-full justify-center"
                >
                  {weeklyLoading ? "Assigning…" : "Assign this week"}
                </button>
              </div>
            )}

            {weeklyError && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{weeklyError}</p>}
          </div>
        )}

        {canManageDefaults && activeTab === "everyWeek" && (
          <div className="space-y-3">
            <p className="text-xs text-slate-500 bg-slate-50 rounded-lg px-3 py-2">
              Every week assignees are automatically added to new weekly checklists. Changes here don't affect this week.
            </p>

            {defaultsLoading ? (
              <div className="py-4 flex justify-center">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
              </div>
            ) : defaults.length > 0 ? (
              <div>
                <p className="text-xs text-slate-500 uppercase font-medium mb-2">Recurring assignees</p>
                <div className="space-y-1">
                  {defaults.map((d: ChecklistAssignmentDefault) => (
                    <div key={d.id} className="flex items-center justify-between py-1.5 px-2 rounded-lg bg-slate-50">
                      <span className="text-sm text-slate-800">{d.user.fullName}</span>
                      <button
                        onClick={() => handleRemoveDefault(d)}
                        className="text-slate-400 hover:text-red-600 p-0.5"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm text-slate-400 italic text-center py-2">No recurring assignees set.</p>
            )}

            {availableForDefault.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs text-slate-500 uppercase font-medium">Add recurring assignee</p>
                <select
                  className="input"
                  value={defaultUserId}
                  onChange={(e) => setDefaultUserId(e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">Select user…</option>
                  {availableForDefault.map((u) => (
                    <option key={u.id} value={u.id}>{u.fullName} ({u.username})</option>
                  ))}
                </select>
                <button
                  onClick={handleAddDefault}
                  disabled={!defaultUserId || defaultLoading}
                  className="btn-primary w-full justify-center"
                >
                  {defaultLoading ? "Adding…" : "Add every week"}
                </button>
              </div>
            )}

            {defaultError && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{defaultError}</p>}
          </div>
        )}

        <button onClick={onClose} className="btn-secondary w-full justify-center mt-4">Done</button>
      </div>
    </div>
  );
}

// ── Task Row ──────────────────────────────────────────────────────────────────

function TaskRow({
  item,
  checklistId,
  canComplete,
  canDelete,
  onComplete,
  onDelete,
}: {
  item: ChecklistItem;
  checklistId: number;
  canComplete: boolean;
  canDelete: boolean;
  onComplete: (item: ChecklistItem) => void;
  onDelete: (itemId: number) => void;
}) {
  const qc = useQueryClient();
  const [incompleteLoading, setIncompleteLoading] = useState(false);

  const canUndo =
    item.isCompleted &&
    canComplete &&
    !(item.isAutoGenerated && (item.autoType === "ITEM_RETURN" || item.autoType === "BIN_RETURN"));

  const handleIncomplete = async () => {
    if (incompleteLoading) return;
    setIncompleteLoading(true);
    try {
      await incompleteChecklistItem(checklistId, item.id);
      invalidateChecklist(qc, checklistId);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? "Failed to mark incomplete");
    } finally {
      setIncompleteLoading(false);
    }
  };

  return (
    <div className={`px-4 py-3 flex items-start gap-3 ${item.isCompleted ? "bg-green-50/50" : ""}`}>
      <div className="flex-shrink-0 mt-0.5">
        {item.isCompleted ? (
          <div className="h-5 w-5 rounded-full bg-green-500 flex items-center justify-center">
            <Check className="h-3 w-3 text-white" />
          </div>
        ) : (
          <div className="h-5 w-5 rounded-full border-2 border-slate-300" />
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-start gap-2 flex-wrap">
          <p className={`text-sm font-medium ${item.isCompleted ? "text-slate-400 line-through" : "text-slate-900"}`}>
            {item.title}
          </p>
          {item.isAutoGenerated && (
            <span className="text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">Auto</span>
          )}
          {item.assignee ? (
            <span className="text-xs bg-brand-100 text-brand-700 px-1.5 py-0.5 rounded">
              {item.assignee.fullName}
            </span>
          ) : (
            <span className="text-xs bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">Everyone</span>
          )}
        </div>
        {item.description && !item.isCompleted && (
          <p className="text-xs text-slate-500 mt-0.5">{item.description}</p>
        )}
        {item.isCompleted && item.completionNotes && (
          <p className="text-xs text-slate-500 mt-0.5 italic">Note: {item.completionNotes}</p>
        )}
      </div>

      <div className="flex items-center gap-1 flex-shrink-0">
        {!item.isCompleted && canComplete && (
          <button
            onClick={() => onComplete(item)}
            className="text-xs text-green-600 hover:text-green-700 px-2 py-1 rounded hover:bg-green-50 transition-colors"
          >
            Complete
          </button>
        )}
        {canUndo && (
          <button
            onClick={handleIncomplete}
            disabled={incompleteLoading}
            className="text-xs text-slate-500 hover:text-slate-700 px-2 py-1 rounded hover:bg-slate-100 transition-colors disabled:opacity-50"
          >
            {incompleteLoading ? "…" : "Undo"}
          </button>
        )}
        {!item.isAutoGenerated && canDelete && (
          <button
            onClick={() => onDelete(item.id)}
            aria-label={`Delete task: ${item.title}`}
            className="p-2 text-slate-300 hover:text-red-500 rounded transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

// ── Subchecklist Section ──────────────────────────────────────────────────────

function SubchecklistSection({
  sub,
  checklistId,
  canComplete,
  canDelete,
  onComplete,
  onDelete,
}: {
  sub: Subchecklist;
  checklistId: number;
  canComplete: boolean;
  canDelete: boolean;
  onComplete: (item: ChecklistItem) => void;
  onDelete: (itemId: number) => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const completed = sub.items.filter((i) => i.isCompleted).length;
  const total = sub.items.length;

  const sectionTypeLabel =
    sub.sectionType === "PRE_SABHA"
      ? "Pre Sabha"
      : sub.sectionType === "POST_SABHA"
      ? "Post Sabha"
      : null;

  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <button
        className="w-full flex items-center gap-2 px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors text-left"
        onClick={() => setCollapsed((v) => !v)}
      >
        <Folder className="h-4 w-4 text-slate-400 flex-shrink-0" />
        <span className="font-medium text-slate-800 flex-1">{sub.title}</span>
        {sectionTypeLabel && (
          <span className="text-xs bg-brand-100 text-brand-700 px-1.5 py-0.5 rounded">
            {sectionTypeLabel}
          </span>
        )}
        {sub.isMandatory && (
          <span className="text-xs bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded">Required</span>
        )}
        <span className="text-xs text-slate-500 ml-1">{completed}/{total}</span>
        {collapsed ? (
          <ChevronRight className="h-4 w-4 text-slate-400" />
        ) : (
          <ChevronDown className="h-4 w-4 text-slate-400" />
        )}
      </button>

      {!collapsed && (
        <div className="divide-y divide-slate-100">
          {sub.items.length === 0 ? (
            <p className="px-4 py-3 text-sm text-slate-400 italic">No tasks in this section</p>
          ) : (
            sub.items.map((item) => (
              <TaskRow
                key={item.id}
                item={item}
                checklistId={checklistId}
                canComplete={canComplete}
                canDelete={canDelete}
                onComplete={onComplete}
                onDelete={onDelete}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ── Checklist Detail View ─────────────────────────────────────────────────────

export function ChecklistDetailView({ checklistId }: { checklistId: number }) {
  const qc = useQueryClient();
  const canManage = useCanManage();
  const canAddItems = useCanAddItems();
  const canAssign = useCanAssign();
  const user = useAuthStore((s) => s.user);

  const [addItemOpen, setAddItemOpen] = useState(false);
  const [addSubOpen, setAddSubOpen] = useState(false);
  const [completingItem, setCompletingItem] = useState<ChecklistItem | null>(null);
  const [assignOpen, setAssignOpen] = useState(false);
  const [deletingItemId, setDeletingItemId] = useState<number | null>(null);

  const { data: checklist, isLoading } = useQuery({
    queryKey: ["checklist", checklistId],
    queryFn: () => getChecklist(checklistId),
  });

  const deleteMut = useMutation({
    mutationFn: ({ itemId }: { itemId: number }) => deleteChecklistItem(checklistId, itemId),
    onSuccess: () => invalidateChecklist(qc, checklistId),
  });

  if (isLoading)
    return (
      <div className="py-8 text-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-brand-600 border-t-transparent mx-auto" />
      </div>
    );
  if (!checklist) return <p className="text-slate-500 p-4">Checklist not found.</p>;

  const isAssigned = checklist.assignments.some((a) => a.userId === user?.id);
  const canComplete = isAssigned || canManage;
  const canDelete = canManage || (!!user?.role.canApproveRequests && isAssigned);

  const completedCount = checklist.items.filter((i) => i.isCompleted).length;
  const topLevelItems = checklist.items.filter((i) => i.subchecklistId === null);
  const assignees = checklist.assignments.map((a) => a.user);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-sm text-slate-500">
          {completedCount}/{checklist.items.length} tasks complete
          {checklist.assignments.length > 0 && (
            <span className="ml-3">
              · {checklist.assignments.map((a) => a.user.fullName).join(", ")}
            </span>
          )}
        </div>
        <div className="flex gap-2 flex-wrap">
          {canAssign && (
            <button onClick={() => setAssignOpen(true)} className="btn-secondary text-sm py-1.5 px-3">
              <UserPlus className="h-3.5 w-3.5" />
              Assign
            </button>
          )}
          {canAddItems && (
            <>
              <button onClick={() => setAddSubOpen(true)} className="btn-secondary text-sm py-1.5 px-3">
                <Folder className="h-3.5 w-3.5" />
                Add section
              </button>
              <button onClick={() => setAddItemOpen(true)} className="btn-primary text-sm py-1.5 px-3">
                <Plus className="h-3.5 w-3.5" />
                Add task
              </button>
            </>
          )}
        </div>
      </div>

      {checklist.subchecklists.length > 0 && (
        <div className="space-y-3">
          {checklist.subchecklists.map((sub) => (
            <SubchecklistSection
              key={sub.id}
              sub={sub}
              checklistId={checklistId}
              canComplete={canComplete}
              canDelete={canDelete}
              onComplete={setCompletingItem}
              onDelete={setDeletingItemId}
            />
          ))}
        </div>
      )}

      {topLevelItems.length > 0 && (
        <div className="card divide-y divide-slate-100 overflow-hidden">
          <div className="px-4 py-2 bg-slate-50">
            <p className="text-xs font-medium text-slate-500 uppercase">General tasks</p>
          </div>
          {topLevelItems.map((item) => (
            <TaskRow
              key={item.id}
              item={item}
              checklistId={checklistId}
              canComplete={canComplete}
              canDelete={canDelete}
              onComplete={setCompletingItem}
              onDelete={setDeletingItemId}
            />
          ))}
        </div>
      )}

      {checklist.items.length === 0 && checklist.subchecklists.length === 0 && (
        <div className="card p-8 text-center text-slate-400">
          <ClipboardCheck className="h-8 w-8 mx-auto mb-2 opacity-40" />
          <p className="text-sm">No tasks yet</p>
        </div>
      )}

      {addItemOpen && (
        <AddItemModal
          checklistId={checklistId}
          subchecklists={checklist.subchecklists}
          assignees={assignees}
          onClose={() => setAddItemOpen(false)}
        />
      )}
      {addSubOpen && (
        <AddSubchecklistModal checklistId={checklistId} onClose={() => setAddSubOpen(false)} />
      )}
      {completingItem && (
        <CompleteModal
          item={completingItem}
          checklistId={checklistId}
          onClose={() => setCompletingItem(null)}
        />
      )}
      {assignOpen && checklist && (
        <AssignModal checklist={checklist} onClose={() => setAssignOpen(false)} />
      )}
      {deletingItemId !== null && (
        <ConfirmModal
          title="Delete Task"
          message="Delete this task? This cannot be undone."
          confirmLabel="Delete"
          isDangerous
          onConfirm={() => {
            deleteMut.mutate({ itemId: deletingItemId });
            setDeletingItemId(null);
          }}
          onCancel={() => setDeletingItemId(null)}
        />
      )}
    </div>
  );
}

// ── Checklist Accordion ───────────────────────────────────────────────────────
// Renders a list of checklist summary cards; each expands to ChecklistDetailView.

export function ChecklistAccordion({ checklists }: { checklists: ChecklistSummary[] }) {
  const [selectedId, setSelectedId] = useState<number | null>(null);

  return (
    <div className="space-y-3">
      {checklists.map((cl) => (
        <div key={cl.id} className="card overflow-hidden">
          <button
            className="w-full flex items-center gap-3 px-5 py-4 text-left hover:bg-slate-50 transition-colors"
            onClick={() => setSelectedId((prev) => (prev === cl.id ? null : cl.id))}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-slate-900">{GROUP_DISPLAY[cl.groupName]}</span>
                <span className="text-xs text-slate-500">
                  Sabha: {formatSabhaDate(cl.sabhaDate, cl.weekStart)}
                </span>
                {cl.completedCount === cl.itemCount && cl.itemCount > 0 && (
                  <span className="badge-green text-xs">All done</span>
                )}
              </div>
              <div className="flex items-center gap-4 mt-1 text-xs text-slate-500">
                <span>{cl.completedCount}/{cl.itemCount} tasks</span>
                <span>{cl.assigneeCount} assignee{cl.assigneeCount !== 1 ? "s" : ""}</span>
              </div>
            </div>

            <div className="w-24 hidden sm:block">
              <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-green-500 rounded-full transition-all"
                  style={{
                    width:
                      cl.itemCount > 0
                        ? `${Math.round((cl.completedCount / cl.itemCount) * 100)}%`
                        : "0%",
                  }}
                />
              </div>
            </div>

            {selectedId === cl.id ? (
              <ChevronDown className="h-4 w-4 text-slate-400 flex-shrink-0" />
            ) : (
              <ChevronRight className="h-4 w-4 text-slate-400 flex-shrink-0" />
            )}
          </button>

          {selectedId === cl.id && (
            <div className="border-t border-slate-100 px-5 py-4">
              <ChecklistDetailView checklistId={cl.id} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
