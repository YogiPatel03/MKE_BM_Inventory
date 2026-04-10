import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, BarChart2, DollarSign, Package, TrendingDown } from "lucide-react";
import { getInventoryStatus, getExpenseReport, getHeldValueReport } from "@/api/reports";
import { listItems } from "@/api/items";
import { useAuthStore } from "@/store/auth";
import { Navigate } from "react-router-dom";
import type { HeldValueReport } from "@/types";

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

// ── Held Value Report Tab ─────────────────────────────────────────────────────

function HeldValueTab() {
  const { data: report, isLoading } = useQuery({
    queryKey: ["report-held-value"],
    queryFn: getHeldValueReport,
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
      </div>
    );
  }

  if (!report) return null;

  return (
    <div className="space-y-6">
      {/* Total */}
      <div className="card p-5 bg-brand-50 border border-brand-100">
        <div className="flex items-center gap-2 text-brand-600 text-sm mb-1">
          <DollarSign className="h-4 w-4" />
          Total Held Inventory Value
        </div>
        <p className="text-3xl font-bold text-brand-900">
          ${report.totalHeldValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </p>
        <p className="text-xs text-brand-600 mt-1">{report.totalItems} active items</p>
      </div>

      {/* By Room */}
      {report.byRoom.length > 0 && (
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">By Room</h3>
          <div className="space-y-2">
            {report.byRoom.map((r) => (
              <div key={r.roomId} className="flex items-center justify-between text-sm">
                <div>
                  <span className="text-slate-800 font-medium">{r.roomName}</span>
                  <span className="text-slate-400 ml-2 text-xs">
                    {r.cabinetCount} cabinet{r.cabinetCount !== 1 ? "s" : ""} · {r.itemCount} items
                  </span>
                </div>
                <span className="font-semibold text-slate-900">
                  ${r.totalValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* By Cabinet */}
      {report.byCabinet.length > 0 && (
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">By Cabinet</h3>
          <div className="space-y-2">
            {report.byCabinet.map((c) => (
              <div key={c.cabinetId} className="flex items-center justify-between text-sm">
                <div>
                  <span className="text-slate-800 font-medium">{c.cabinetName}</span>
                  <span className="text-slate-400 ml-2 text-xs">
                    {c.roomName} · {c.itemCount} items
                  </span>
                </div>
                <span className="font-semibold text-slate-900">
                  ${c.totalValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Item detail table */}
      <div className="card p-4">
        <h3 className="text-sm font-semibold text-slate-700 mb-3">Item Detail</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100">
                <th className="text-left pb-2 font-medium text-slate-600">Item</th>
                <th className="text-left pb-2 font-medium text-slate-600 hidden sm:table-cell">Cabinet</th>
                <th className="text-right pb-2 font-medium text-slate-600">Qty</th>
                <th className="text-right pb-2 font-medium text-slate-600">Unit Price</th>
                <th className="text-right pb-2 font-medium text-slate-600">Value</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {report.items.map((item) => (
                <tr key={item.itemId}>
                  <td className="py-2 text-slate-700">{item.itemName}</td>
                  <td className="py-2 text-slate-500 hidden sm:table-cell">{item.cabinetName}</td>
                  <td className="py-2 text-right text-slate-600">{item.quantityTotal}</td>
                  <td className="py-2 text-right text-slate-600">
                    {item.unitPrice != null ? `$${item.unitPrice.toFixed(2)}` : "—"}
                  </td>
                  <td className="py-2 text-right font-medium text-slate-900">
                    {item.heldValue > 0
                      ? `$${item.heldValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-slate-400 mt-3">
          * Value = unit price × total quantity. Checked-out items are still counted because
          the organisation still owns them. Value decreases only on loss/damage adjustments.
        </p>
      </div>
    </div>
  );
}

// ── Main Reports Page ─────────────────────────────────────────────────────────

export function ReportsPage() {
  const user = useAuthStore((s) => s.user);
  const canView = user?.role.canManageInventory || user?.role.canManageUsers;

  const today = toISODate(new Date());
  const [preset, setPreset] = useState<"month" | "ytd" | "custom">("month");
  const [startDate, setStartDate] = useState(thisMonthStart());
  const [endDate, setEndDate] = useState(today);
  const [activeTab, setActiveTab] = useState<"status" | "purchases" | "usage" | "held-value">("status");
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
    enabled: activeTab === "purchases" || activeTab === "usage",
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Reports</h1>
        <p className="text-sm text-slate-500 mt-0.5">Inventory health, expenses, and held value</p>
      </div>

      {/* Top-level tabs */}
      <div className="flex gap-2 flex-wrap">
        {(["status", "purchases", "usage", "held-value"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-1.5 text-sm rounded-lg border transition-colors ${
              activeTab === tab
                ? "bg-brand-600 text-white border-brand-600"
                : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
            }`}
          >
            {tab === "status" && "Inventory Status"}
            {tab === "purchases" && "Purchases"}
            {tab === "usage" && "Usage"}
            {tab === "held-value" && "Held Value"}
          </button>
        ))}
      </div>

      {/* ── Status Tab ── */}
      {activeTab === "status" && (
        <>
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

              {status.outOfStockItems.length > 0 && (
                <div className="card p-4">
                  <h2 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-red-500" />
                    Out of Stock
                  </h2>
                  <div className="space-y-2">
                    {status.outOfStockItems.map((item) => (
                      <div key={item.itemId} className="flex items-center justify-between text-sm">
                        <span className="text-slate-700">{item.itemName}</span>
                        <span className="badge-red text-xs">Out of stock</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : null}
        </>
      )}

      {/* ── Purchases / Usage tabs (shared period selector) ── */}
      {(activeTab === "purchases" || activeTab === "usage") && (
        <>
          {/* Period picker */}
          <div className="card p-4 space-y-3">
            <h2 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <BarChart2 className="h-4 w-4" />
              Period
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

          {/* Results */}
          <div className="card p-4 space-y-4">
            {expensesLoading ? (
              <div className="text-sm text-slate-500">Loading…</div>
            ) : expenses ? (
              <>
                <div className="text-sm font-semibold text-slate-900">
                  {activeTab === "purchases" ? (
                    <>Total: <span className="text-brand-700">${expenses.totalPurchaseSpend.toFixed(2)}</span> spent</>
                  ) : (
                    <>Total: <span className="text-amber-700">${expenses.totalUsageCost.toFixed(2)}</span> consumed</>
                  )}
                </div>

                {activeTab === "purchases" ? (
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
                )}
              </>
            ) : null}
          </div>
        </>
      )}

      {/* ── Held Value Tab ── */}
      {activeTab === "held-value" && <HeldValueTab />}
    </div>
  );
}
