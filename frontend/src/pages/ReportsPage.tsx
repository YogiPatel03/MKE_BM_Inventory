import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, TrendingDown, Package, BarChart2 } from "lucide-react";
import { getInventoryStatus, getExpenseReport } from "@/api/reports";
import { listItems } from "@/api/items";
import { useAuthStore } from "@/store/auth";
import { Navigate } from "react-router-dom";

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function thisMonthStart(): string {
  const d = new Date();
  return toISODate(new Date(d.getFullYear(), d.getMonth(), 1));
}

function ytdStart(): string {
  return toISODate(new Date(new Date().getFullYear(), 0, 1));
}

export function ReportsPage() {
  const user = useAuthStore((s) => s.user);
  const canView = user?.role.canManageInventory || user?.role.canManageUsers;

  const today = toISODate(new Date());
  const [preset, setPreset] = useState<"month" | "ytd" | "custom">("month");
  const [startDate, setStartDate] = useState(thisMonthStart());
  const [endDate, setEndDate] = useState(today);
  const [activeTab, setActiveTab] = useState<"purchases" | "usage">("purchases");
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);

  if (!canView) return <Navigate to="/dashboard" replace />;

  const effectiveStart = preset === "month" ? thisMonthStart() : preset === "ytd" ? ytdStart() : startDate;
  const effectiveEnd = preset === "custom" ? endDate : today;

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ["report-status"],
    queryFn: getInventoryStatus,
  });

  const { data: allItems = [] } = useQuery({
    queryKey: ["items-for-filter"],
    queryFn: () => listItems({ isActive: true }),
  });

  const { data: expenses, isLoading: expensesLoading } = useQuery({
    queryKey: ["report-expenses", effectiveStart, effectiveEnd, selectedItemId],
    queryFn: () => getExpenseReport(
      new Date(effectiveStart).toISOString(),
      new Date(effectiveEnd + "T23:59:59").toISOString(),
      selectedItemId,
    ),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Reports</h1>
        <p className="text-sm text-slate-500 mt-0.5">Inventory health and expense tracking</p>
      </div>

      {/* Status row */}
      {statusLoading ? (
        <div className="flex justify-center py-8">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
        </div>
      ) : status ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="card p-4">
              <div className="flex items-center gap-2 text-slate-500 text-xs mb-1">
                <Package className="h-4 w-4" />
                Total Items
              </div>
              <p className="text-2xl font-bold text-slate-900">{status.totalItems}</p>
            </div>
            <div className="card p-4">
              <div className="flex items-center gap-2 text-slate-500 text-xs mb-1">
                <Package className="h-4 w-4" />
                Checked Out
              </div>
              <p className="text-2xl font-bold text-slate-900">{status.checkedOutCount}</p>
            </div>
            <div className="card p-4">
              <div className="flex items-center gap-2 text-amber-500 text-xs mb-1">
                <AlertTriangle className="h-4 w-4" />
                Overdue
              </div>
              <p className={`text-2xl font-bold ${status.overdueCount > 0 ? "text-amber-600" : "text-slate-900"}`}>
                {status.overdueCount}
              </p>
            </div>
            <div className="card p-4">
              <div className="flex items-center gap-2 text-red-500 text-xs mb-1">
                <TrendingDown className="h-4 w-4" />
                Low Stock
              </div>
              <p className={`text-2xl font-bold ${status.lowStockItems.length > 0 ? "text-red-600" : "text-slate-900"}`}>
                {status.lowStockItems.length}
              </p>
            </div>
          </div>

          {status.lowStockItems.length > 0 && (
            <div className="card p-4">
              <h2 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-500" />
                Low Stock Items
              </h2>
              <div className="space-y-2">
                {status.lowStockItems.map((item) => (
                  <div key={item.itemId} className="flex items-center justify-between text-sm">
                    <span className="text-slate-700">{item.itemName}</span>
                    <span className="text-amber-600 font-medium">
                      {item.quantityAvailable}/{item.quantityTotal}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      ) : null}

      {/* Period picker */}
      <div className="card p-4 space-y-3">
        <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
          <BarChart2 className="h-4 w-4" />
          Expense Period
        </h2>
        <div className="flex gap-2 flex-wrap">
          {(["month", "ytd", "custom"] as const).map((p) => (
            <button
              key={p}
              onClick={() => setPreset(p)}
              className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                preset === p
                  ? "bg-brand-600 text-white border-brand-600"
                  : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
              }`}
            >
              {p === "month" ? "This month" : p === "ytd" ? "Year to date" : "Custom range"}
            </button>
          ))}
        </div>
        {preset === "custom" && (
          <div className="flex gap-3 flex-wrap">
            <div>
              <label className="label">From</label>
              <input type="date" className="input" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </div>
            <div>
              <label className="label">To</label>
              <input type="date" className="input" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </div>
          </div>
        )}
        {!expensesLoading && expenses && (
          <p className="text-xs text-slate-400">
            {new Date(expenses.periodStart).toLocaleDateString()} –{" "}
            {new Date(expenses.periodEnd).toLocaleDateString()}
          </p>
        )}

        {/* Item filter */}
        <div>
          <label className="label">Filter by item</label>
          <select
            className="input max-w-xs"
            value={selectedItemId ?? ""}
            onChange={(e) => setSelectedItemId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">All items</option>
            {allItems.map((item) => (
              <option key={item.id} value={item.id}>{item.name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Expense tabs */}
      <div className="card p-4 space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex gap-2">
            <button
              onClick={() => setActiveTab("purchases")}
              className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                activeTab === "purchases"
                  ? "bg-brand-600 text-white border-brand-600"
                  : "bg-white text-slate-600 border-slate-200"
              }`}
            >
              Purchases (restocking)
            </button>
            <button
              onClick={() => setActiveTab("usage")}
              className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
                activeTab === "usage"
                  ? "bg-amber-600 text-white border-amber-600"
                  : "bg-white text-slate-600 border-slate-200"
              }`}
            >
              Usage (consumption)
            </button>
          </div>
          {!expensesLoading && expenses && (
            <div className="text-sm">
              {activeTab === "purchases" ? (
                <span className="font-bold text-slate-900">
                  ${expenses.totalPurchaseSpend.toFixed(2)}{" "}
                  <span className="font-normal text-slate-400">spent</span>
                </span>
              ) : (
                <span className="font-bold text-amber-700">
                  ${expenses.totalUsageCost.toFixed(2)}{" "}
                  <span className="font-normal text-slate-400">consumed</span>
                </span>
              )}
            </div>
          )}
        </div>

        {expensesLoading ? (
          <div className="text-sm text-slate-500">Loading…</div>
        ) : expenses ? (
          activeTab === "purchases" ? (
            expenses.byPurchase.length === 0 ? (
              <p className="text-sm text-slate-400">No purchases in this period.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="text-left pb-2 font-medium text-slate-600">Item</th>
                    <th className="text-right pb-2 font-medium text-slate-600">Qty bought</th>
                    <th className="text-right pb-2 font-medium text-slate-600">Cost</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {expenses.byPurchase.map((row) => (
                    <tr key={row.itemId}>
                      <td className="py-2 text-slate-700">{row.itemName}</td>
                      <td className="py-2 text-right text-slate-600">{row.totalPurchased}</td>
                      <td className="py-2 text-right font-medium text-slate-900">
                        {row.totalPurchaseCost != null ? `$${row.totalPurchaseCost.toFixed(2)}` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          ) : (
            expenses.byUsage.length === 0 ? (
              <p className="text-sm text-slate-400">No usage events in this period.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="text-left pb-2 font-medium text-slate-600">Item</th>
                    <th className="text-right pb-2 font-medium text-slate-600">Qty used</th>
                    <th className="text-right pb-2 font-medium text-slate-600">Est. cost</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {expenses.byUsage.map((row) => (
                    <tr key={row.itemId}>
                      <td className="py-2 text-slate-700">{row.itemName}</td>
                      <td className="py-2 text-right text-slate-600">{row.totalUsed}</td>
                      <td className="py-2 text-right font-medium text-amber-700">
                        {row.totalCost != null && row.totalCost > 0 ? `$${row.totalCost.toFixed(2)}` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )
        ) : null}
      </div>
    </div>
  );
}
