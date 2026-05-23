import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Box,
  CheckCircle,
  ClipboardCheck,
  ClipboardList,
  Clock,
  Inbox,
  RefreshCw,
  ShoppingCart,
} from "lucide-react";
import { listTransactions } from "@/api/transactions";
import { getInventoryStatus } from "@/api/reports";
import { listChecklists, backfillActiveTransactions } from "@/api/checklists";
import { useAuthStore } from "@/store/auth";
import { TransactionRow } from "@/components/transactions/TransactionRow";
import {
  ChecklistAccordion,
  useCanManage,
} from "@/components/checklist/ChecklistComponents";
import { BinRequestModal } from "@/components/modals/BinRequestModal";
import { toast } from "@/store/toast";
import { format } from "date-fns";
import { Link } from "react-router-dom";
import type { GroupName } from "@/types";
import { GROUP_DISPLAY, GROUP_NAMES } from "@/types";

function StatCard({
  label,
  value,
  icon: Icon,
  color,
  to,
}: {
  label: string;
  value: number | string;
  icon: React.ElementType;
  color: string;
  to?: string;
}) {
  const inner = (
    <div className="card p-5 flex items-start gap-4">
      <div className={`rounded-xl p-3 ${color}`}>
        <Icon className="h-5 w-5" />
      </div>
      <div>
        <p className="text-2xl font-bold text-slate-900">{value}</p>
        <p className="text-sm text-slate-500">{label}</p>
      </div>
    </div>
  );
  return to ? <Link to={to}>{inner}</Link> : inner;
}

function WeeklyChecklistSection() {
  const qc = useQueryClient();
  const canManage = useCanManage();
  const [syncing, setSyncing] = useState(false);
  const [binRequestOpen, setBinRequestOpen] = useState(false);
  const [selectedGroup, setSelectedGroup] = useState<GroupName | "">("");

  const { data: checklists = [], isLoading } = useQuery({
    queryKey: ["checklists", selectedGroup],
    queryFn: () => listChecklists(selectedGroup ? { groupName: selectedGroup } : {}),
  });

  const filtered = selectedGroup
    ? checklists.filter((c) => c.groupName === selectedGroup)
    : checklists;

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

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
        <h2 className="text-base font-semibold text-slate-900">Weekly Checklist</h2>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setBinRequestOpen(true)}
            className="btn-secondary text-sm py-1.5 px-3"
          >
            <Inbox className="h-3.5 w-3.5" />
            Request bin
          </button>
          {canManage && (
            <button
              onClick={handleSync}
              disabled={syncing}
              className="btn-secondary text-sm py-1.5 px-3"
              title="Create missing return tasks for all active checkouts"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin" : ""}`} />
              {syncing ? "Syncing…" : "Sync checkouts"}
            </button>
          )}
        </div>
      </div>

      <div className="flex gap-2 flex-wrap mb-3">
        <button
          onClick={() => setSelectedGroup("")}
          className={`px-3 py-1 text-xs rounded-full border transition-colors ${
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
            className={`px-3 py-1 text-xs rounded-full border transition-colors ${
              selectedGroup === g
                ? "bg-brand-600 text-white border-brand-600"
                : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
            }`}
          >
            {GROUP_DISPLAY[g]}
          </button>
        ))}
      </div>

      {binRequestOpen && <BinRequestModal onClose={() => setBinRequestOpen(false)} />}

      {isLoading ? (
        <div className="card p-8 flex justify-center">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="card p-8 text-center text-slate-500">
          <ClipboardCheck className="h-10 w-10 mx-auto mb-3 text-slate-300" />
          <p className="text-sm">No active checklists this week.</p>
          <p className="text-xs text-slate-400 mt-1">They are auto-generated every Monday morning.</p>
        </div>
      ) : (
        <ChecklistAccordion checklists={filtered} />
      )}
    </div>
  );
}

export function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const canViewAll = user?.role.canViewAllTransactions ?? false;
  const canManageInventory = user?.role.canManageInventory ?? false;

  const { data: activeTransactions = [] } = useQuery({
    queryKey: ["transactions", "CHECKED_OUT"],
    queryFn: () => listTransactions({ status_filter: "CHECKED_OUT", limit: 100 }),
  });

  const { data: overdueTransactions = [] } = useQuery({
    queryKey: ["transactions", "OVERDUE"],
    queryFn: () => listTransactions({ status_filter: "OVERDUE", limit: 100 }),
  });

  const { data: recentTransactions = [] } = useQuery({
    queryKey: ["transactions", "recent"],
    queryFn: () => listTransactions({ limit: 10 }),
  });

  const { data: inventoryStatus } = useQuery({
    queryKey: ["inventory-status"],
    queryFn: getInventoryStatus,
    enabled: canManageInventory,
  });

  const lowStockCount = inventoryStatus?.lowStockItems.length ?? 0;
  const outOfStockCount = inventoryStatus?.outOfStockItems.length ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          {format(new Date(), "EEEE, MMMM d, yyyy")}
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Checked out"
          value={activeTransactions.length}
          icon={ClipboardList}
          color="bg-blue-50 text-blue-600"
          to="/transactions"
        />
        <StatCard
          label="Overdue"
          value={overdueTransactions.length}
          icon={AlertTriangle}
          color={overdueTransactions.length > 0 ? "bg-red-50 text-red-600" : "bg-slate-50 text-slate-400"}
          to="/transactions"
        />
        {canManageInventory && (
          <>
            <StatCard
              label="Low stock"
              value={lowStockCount}
              icon={ShoppingCart}
              color={lowStockCount > 0 ? "bg-amber-50 text-amber-600" : "bg-slate-50 text-slate-400"}
              to="/reports"
            />
            <StatCard
              label="Out of stock"
              value={outOfStockCount}
              icon={Box}
              color={outOfStockCount > 0 ? "bg-red-50 text-red-600" : "bg-slate-50 text-slate-400"}
              to="/reports"
            />
          </>
        )}
        {!canManageInventory && (
          <StatCard
            label="My active"
            value={activeTransactions.length}
            icon={CheckCircle}
            color="bg-green-50 text-green-600"
          />
        )}
      </div>

      {/* Overdue alert */}
      {overdueTransactions.length > 0 && (
        <div className="rounded-xl bg-red-50 border border-red-200 p-4 flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-red-600 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-sm font-semibold text-red-800">
              {overdueTransactions.length} overdue checkout{overdueTransactions.length > 1 ? "s" : ""}
            </p>
            <p className="text-sm text-red-700">
              Check the Transactions page or Telegram for details.
            </p>
          </div>
        </div>
      )}

      {/* Weekly Checklist */}
      <WeeklyChecklistSection />

      {/* Low stock items — visible to coordinators */}
      {canManageInventory && lowStockCount > 0 && (
        <div>
          <h2 className="text-base font-semibold text-slate-900 mb-3">Low Stock Items</h2>
          <div className="card divide-y divide-slate-100 overflow-hidden">
            {inventoryStatus?.lowStockItems.slice(0, 5).map((item) => (
              <Link
                key={item.itemId}
                to={`/inventory/items/${item.itemId}`}
                className="px-4 py-3 flex items-center justify-between hover:bg-slate-50 transition-colors"
              >
                <div>
                  <p className="text-sm font-medium text-slate-900">{item.itemName}</p>
                  <p className="text-xs text-slate-400">
                    Cabinet {item.cabinetId}{item.binId ? ` / Bin ${item.binId}` : ""}
                  </p>
                </div>
                <div className="text-right">
                  <span className="badge-yellow">{item.quantityAvailable} left</span>
                  {item.lowStockThreshold && (
                    <p className="text-xs text-slate-400 mt-0.5">threshold: {item.lowStockThreshold}</p>
                  )}
                </div>
              </Link>
            ))}
            {lowStockCount > 5 && (
              <Link to="/reports" className="block px-4 py-2 text-xs text-brand-600 hover:underline text-center">
                +{lowStockCount - 5} more → See full report
              </Link>
            )}
          </div>
        </div>
      )}

      {/* Out of stock items */}
      {canManageInventory && outOfStockCount > 0 && (
        <div>
          <h2 className="text-base font-semibold text-slate-900 mb-3">Out of Stock</h2>
          <div className="card divide-y divide-slate-100 overflow-hidden">
            {inventoryStatus?.outOfStockItems.slice(0, 5).map((item) => (
              <Link
                key={item.itemId}
                to={`/inventory/items/${item.itemId}`}
                className="px-4 py-3 flex items-center justify-between hover:bg-slate-50 transition-colors"
              >
                <div>
                  <p className="text-sm font-medium text-slate-900">{item.itemName}</p>
                  <p className="text-xs text-slate-400">
                    Cabinet {item.cabinetId}{item.binId ? ` / Bin ${item.binId}` : ""}
                  </p>
                </div>
                <span className="badge-red">Out of stock</span>
              </Link>
            ))}
            {outOfStockCount > 5 && (
              <Link to="/reports" className="block px-4 py-2 text-xs text-brand-600 hover:underline text-center">
                +{outOfStockCount - 5} more → See full report
              </Link>
            )}
          </div>
        </div>
      )}

      {/* Recent transactions */}
      <div>
        <h2 className="text-base font-semibold text-slate-900 mb-3">
          {canViewAll ? "Recent Transactions" : "My Recent Transactions"}
        </h2>
        <div className="card divide-y divide-slate-100 overflow-hidden">
          {recentTransactions.length === 0 ? (
            <div className="py-10 text-center text-sm text-slate-400">
              <Clock className="h-8 w-8 mx-auto mb-2 text-slate-300" />
              No transactions yet
            </div>
          ) : (
            recentTransactions.map((t) => <TransactionRow key={t.id} transaction={t} />)
          )}
        </div>
      </div>
    </div>
  );
}
