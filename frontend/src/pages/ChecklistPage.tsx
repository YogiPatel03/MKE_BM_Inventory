import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardCheck, RefreshCw } from "lucide-react";
import { toast } from "@/store/toast";
import { listChecklists, backfillActiveTransactions } from "@/api/checklists";
import { useCanManage, ChecklistAccordion } from "@/components/checklist/ChecklistComponents";
import type { GroupName } from "@/types";
import { GROUP_DISPLAY, GROUP_NAMES } from "@/types";

export function ChecklistPage() {
  const [selectedGroup, setSelectedGroup] = useState<GroupName | "">("");
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
      toast.success(`Sync complete: ${result.created} task(s) created, ${result.skipped} already up to date.`);
    } catch {
      toast.error("Sync failed. Check that users have a group assigned.");
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
          <p className="text-sm text-slate-500 mt-0.5">
            Auto-generated every Monday · Pre Sabha &amp; Post Sabha sections included
          </p>
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

      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setSelectedGroup("")}
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
            onClick={() => setSelectedGroup(g)}
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
        <ChecklistAccordion checklists={filtered} />
      )}
    </div>
  );
}
