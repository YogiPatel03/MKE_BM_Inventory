import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, ChevronRight, ClipboardCheck, Plus, RefreshCw, Trash2, UserPlus, X } from "lucide-react";
import {
  listChecklists,
  getChecklist,
  addChecklistItem,
  completeChecklistItem,
  deleteChecklistItem,
  assignUser,
  unassignUser,
  backfillActiveTransactions,
} from "@/api/checklists";
import { listUsers } from "@/api/users";
import { useAuthStore } from "@/store/auth";
import type { Checklist, ChecklistItem, ChecklistSummary, GroupName } from "@/types";
import { GROUP_DISPLAY, GROUP_NAMES } from "@/types";

function useCanManage() {
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
  return (user?.role.canManageUsers || user?.role.canManageInventory || user?.role.canApproveRequests) ?? false;
}

// ── Add Item Modal ────────────────────────────────────────────────────────────

function AddItemModal({
  checklistId,
  onClose,
}: {
  checklistId: number;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await addChecklistItem(checklistId, { title: title.trim(), description: description.trim() || undefined });
      qc.invalidateQueries({ queryKey: ["checklist", checklistId] });
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
        <h2 className="text-lg font-semibold text-slate-900 mb-5">Add Checklist Item</h2>
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
          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary flex-1 justify-center">Cancel</button>
            <button type="submit" disabled={loading} className="btn-primary flex-1 justify-center">
              {loading ? "Adding…" : "Add item"}
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await completeChecklistItem(checklistId, item.id, notes.trim() || undefined);
      qc.invalidateQueries({ queryKey: ["checklist", checklistId] });
      qc.invalidateQueries({ queryKey: ["checklists"] });
      onClose();
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? "Failed to complete item");
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
            📸 A photo proof request will be sent to the Telegram group chat.
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

// ── Assign User Modal ─────────────────────────────────────────────────────────

function AssignModal({
  checklist,
  onClose,
}: {
  checklist: Checklist;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [userId, setUserId] = useState<number | "">("");
  const [loading, setLoading] = useState(false);

  const { data: allUsers = [] } = useQuery({
    queryKey: ["users"],
    queryFn: listUsers,
  });

  const assignedIds = new Set(checklist.assignments.map((a) => a.userId));
  const available = allUsers.filter((u) => u.isActive && !assignedIds.has(u.id));

  const handleAssign = async () => {
    if (!userId) return;
    setLoading(true);
    try {
      await assignUser(checklist.id, userId as number);
      qc.invalidateQueries({ queryKey: ["checklist", checklist.id] });
      onClose();
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? "Failed to assign user");
    } finally {
      setLoading(false);
    }
  };

  const handleUnassign = async (uid: number) => {
    try {
      await unassignUser(checklist.id, uid);
      qc.invalidateQueries({ queryKey: ["checklist", checklist.id] });
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? "Failed to unassign user");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50">
      <div className="card w-full max-w-md p-6 relative">
        <button onClick={onClose} className="absolute top-4 right-4 text-slate-400 hover:text-slate-700">
          <X className="h-5 w-5" />
        </button>
        <h2 className="text-lg font-semibold text-slate-900 mb-4">Manage Assignments</h2>

        {/* Current assignees */}
        {checklist.assignments.length > 0 && (
          <div className="mb-4">
            <p className="text-xs text-slate-500 uppercase font-medium mb-2">Currently assigned</p>
            <div className="space-y-1">
              {checklist.assignments.map((a) => (
                <div key={a.id} className="flex items-center justify-between py-1.5 px-2 rounded-lg bg-slate-50">
                  <span className="text-sm text-slate-800">{a.user.fullName}</span>
                  <button
                    onClick={() => handleUnassign(a.userId)}
                    className="text-slate-400 hover:text-red-600 p-0.5"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Add new assignee */}
        {available.length > 0 && (
          <div className="space-y-3">
            <p className="text-xs text-slate-500 uppercase font-medium">Add assignee</p>
            <select
              className="input"
              value={userId}
              onChange={(e) => setUserId(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">Select user…</option>
              {available.map((u) => (
                <option key={u.id} value={u.id}>{u.fullName} ({u.username})</option>
              ))}
            </select>
            <button
              onClick={handleAssign}
              disabled={!userId || loading}
              className="btn-primary w-full justify-center"
            >
              {loading ? "Assigning…" : "Assign"}
            </button>
          </div>
        )}

        <button onClick={onClose} className="btn-secondary w-full justify-center mt-3">Done</button>
      </div>
    </div>
  );
}

// ── Checklist Detail View ─────────────────────────────────────────────────────

function ChecklistDetailView({ checklistId }: { checklistId: number }) {
  const qc = useQueryClient();
  const canManage = useCanManage();
  const canAddItems = useCanAddItems();
  const canAssign = useCanAssign();
  const user = useAuthStore((s) => s.user);

  const [addItemOpen, setAddItemOpen] = useState(false);
  const [completingItem, setCompletingItem] = useState<ChecklistItem | null>(null);
  const [assignOpen, setAssignOpen] = useState(false);

  const { data: checklist, isLoading } = useQuery({
    queryKey: ["checklist", checklistId],
    queryFn: () => getChecklist(checklistId),
  });

  const deleteMut = useMutation({
    mutationFn: ({ itemId }: { itemId: number }) => deleteChecklistItem(checklistId, itemId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["checklist", checklistId] }),
  });

  if (isLoading) return <div className="py-8 text-center"><div className="h-6 w-6 animate-spin rounded-full border-2 border-brand-600 border-t-transparent mx-auto" /></div>;
  if (!checklist) return <p className="text-slate-500 p-4">Checklist not found.</p>;

  const isAssigned = checklist.assignments.some((a) => a.userId === user?.id);
  const canComplete = isAssigned || canManage;

  const completedCount = checklist.items.filter((i) => i.isCompleted).length;

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="text-sm text-slate-500">
          {completedCount}/{checklist.items.length} tasks complete
          {checklist.assignments.length > 0 && (
            <span className="ml-3">
              · {checklist.assignments.map((a) => a.user.fullName).join(", ")}
            </span>
          )}
        </div>
        <div className="flex gap-2">
          {canAssign && (
            <button onClick={() => setAssignOpen(true)} className="btn-secondary text-sm py-1.5 px-3">
              <UserPlus className="h-3.5 w-3.5" />
              Assign
            </button>
          )}
          {canAddItems && (
            <button onClick={() => setAddItemOpen(true)} className="btn-primary text-sm py-1.5 px-3">
              <Plus className="h-3.5 w-3.5" />
              Add task
            </button>
          )}
        </div>
      </div>

      {/* Items list */}
      {checklist.items.length === 0 ? (
        <div className="card p-8 text-center text-slate-400">
          <ClipboardCheck className="h-8 w-8 mx-auto mb-2 opacity-40" />
          <p className="text-sm">No tasks yet</p>
        </div>
      ) : (
        <div className="card divide-y divide-slate-100 overflow-hidden">
          {checklist.items.map((item) => (
            <div
              key={item.id}
              className={`px-4 py-3 flex items-start gap-3 ${item.isCompleted ? "bg-green-50/50" : ""}`}
            >
              {/* Completion status */}
              <div className="flex-shrink-0 mt-0.5">
                {item.isCompleted ? (
                  <div className="h-5 w-5 rounded-full bg-green-500 flex items-center justify-center">
                    <Check className="h-3 w-3 text-white" />
                  </div>
                ) : (
                  <div className="h-5 w-5 rounded-full border-2 border-slate-300" />
                )}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-start gap-2 flex-wrap">
                  <p className={`text-sm font-medium ${item.isCompleted ? "text-slate-400 line-through" : "text-slate-900"}`}>
                    {item.title}
                  </p>
                  {item.isAutoGenerated && (
                    <span className="text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">
                      Auto
                    </span>
                  )}
                </div>
                {item.description && !item.isCompleted && (
                  <p className="text-xs text-slate-500 mt-0.5">{item.description}</p>
                )}
                {item.isCompleted && item.completionNotes && (
                  <p className="text-xs text-slate-500 mt-0.5 italic">Note: {item.completionNotes}</p>
                )}
              </div>

              {/* Actions */}
              <div className="flex items-center gap-1 flex-shrink-0">
                {!item.isCompleted && canComplete && (
                  <button
                    onClick={() => setCompletingItem(item)}
                    className="text-xs text-green-600 hover:text-green-700 px-2 py-1 rounded hover:bg-green-50 transition-colors"
                  >
                    Complete
                  </button>
                )}
                {!item.isAutoGenerated && canManage && (
                  <button
                    onClick={() => {
                      if (confirm("Delete this task?")) deleteMut.mutate({ itemId: item.id });
                    }}
                    className="p-1 text-slate-300 hover:text-red-500 rounded transition-colors"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {addItemOpen && <AddItemModal checklistId={checklistId} onClose={() => setAddItemOpen(false)} />}
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
    </div>
  );
}

// ── Main Checklist Page ───────────────────────────────────────────────────────

export function ChecklistPage() {
  const [selectedGroup, setSelectedGroup] = useState<GroupName | "">("");
  const [selectedChecklistId, setSelectedChecklistId] = useState<number | null>(null);
  const [syncing, setSyncing] = useState(false);
  const canManage = useCanManage();
  const qc = useQueryClient();

  const { data: checklists = [], isLoading } = useQuery({
    queryKey: ["checklists", selectedGroup],
    queryFn: () => listChecklists(selectedGroup ? { groupName: selectedGroup } : {}),
  });

  const handleSync = async () => {
    setSyncing(true);
    try {
      const result = await backfillActiveTransactions();
      qc.invalidateQueries({ queryKey: ["checklists"] });
      alert(`Sync complete: ${result.created} task(s) created, ${result.skipped} already up to date.`);
    } catch {
      alert("Sync failed. Check that users have a group assigned.");
    } finally {
      setSyncing(false);
    }
  };

  const filtered = selectedGroup
    ? checklists.filter((c) => c.groupName === selectedGroup)
    : checklists;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Weekly Checklist</h1>
          <p className="text-sm text-slate-500 mt-0.5">Auto-generated every Monday for each group</p>
        </div>
        {canManage && (
          <button
            onClick={handleSync}
            disabled={syncing}
            className="btn-secondary text-sm"
            title="Create missing return tasks for all active checkouts"
          >
            <RefreshCw className={`h-4 w-4 ${syncing ? "animate-spin" : ""}`} />
            {syncing ? "Syncing…" : "Sync active checkouts"}
          </button>
        )}
      </div>

      {/* Group filter */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => { setSelectedGroup(""); setSelectedChecklistId(null); }}
          className={`px-3 py-1 text-sm rounded-full border transition-colors ${
            selectedGroup === ""
              ? "bg-brand-600 text-white border-brand-600"
              : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
          }`}
        >
          All Groups
        </button>
        {GROUP_NAMES.map((g) => (
          <button
            key={g}
            onClick={() => { setSelectedGroup(g); setSelectedChecklistId(null); }}
            className={`px-3 py-1 text-sm rounded-full border transition-colors ${
              selectedGroup === g
                ? "bg-brand-600 text-white border-brand-600"
                : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
            }`}
          >
            {GROUP_DISPLAY[g]}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="card p-8 text-center text-slate-500">
          <ClipboardCheck className="h-10 w-10 mx-auto mb-3 text-slate-300" />
          <p>No checklists found. They are auto-generated every Monday morning.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((cl) => (
            <div key={cl.id} className="card overflow-hidden">
              {/* Summary row */}
              <button
                className="w-full flex items-center gap-3 px-5 py-4 text-left hover:bg-slate-50 transition-colors"
                onClick={() =>
                  setSelectedChecklistId((prev) => (prev === cl.id ? null : cl.id))
                }
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-slate-900">
                      {GROUP_DISPLAY[cl.groupName]}
                    </span>
                    <span className="text-xs text-slate-500">
                      Week of {new Date(cl.weekStart).toLocaleDateString()}
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

                {/* Progress bar */}
                <div className="w-24 hidden sm:block">
                  <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-green-500 rounded-full transition-all"
                      style={{
                        width: cl.itemCount > 0
                          ? `${Math.round((cl.completedCount / cl.itemCount) * 100)}%`
                          : "0%",
                      }}
                    />
                  </div>
                </div>

                {selectedChecklistId === cl.id ? (
                  <ChevronDown className="h-4 w-4 text-slate-400 flex-shrink-0" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-slate-400 flex-shrink-0" />
                )}
              </button>

              {/* Expanded checklist detail */}
              {selectedChecklistId === cl.id && (
                <div className="border-t border-slate-100 px-5 py-4">
                  <ChecklistDetailView checklistId={cl.id} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
