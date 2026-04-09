import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, TrendingDown, Package, DollarSign } from "lucide-react";
import { getInventoryStatus, getExpenseReport } from "@/api/reports";
import { useAuthStore } from "@/store/auth";
import { Navigate } from "react-router-dom";

export function ReportsPage() {
  const user = useAuthStore((s) => s.user);
  const canView = user?.role.canManageInventory || user?.role.canManageUsers;

  if (!canView) return <Navigate to="/dashboard" replace />;

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ["report-status"],
    queryFn: getInventoryStatus,
  });

  const { data: expenses, isLoading: expensesLoading } = useQuery({
    queryKey: ["report-expenses"],
    queryFn: () => getExpenseReport(),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Reports</h1>
        <p className="text-sm text-slate-500 mt-0.5">Inventory health and expense summary</p>
      </div>

      {/* Stats row */}
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

      {/* Expense report */}
      <div className="card p-4">
        <h2 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
          <DollarSign className="h-4 w-4" />
          Expense Report (This Month)
        </h2>
        {expensesLoading ? (
          <div className="text-sm text-slate-500">Loading…</div>
        ) : expenses ? (
          <>
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm text-slate-500">Total spend</span>
              <span className="text-lg font-bold text-slate-900">
                ${expenses.totalSpend.toFixed(2)}
              </span>
            </div>
            {expenses.byItem.length === 0 ? (
              <p className="text-sm text-slate-400">No purchases this month.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="text-left pb-2 font-medium text-slate-600">Item</th>
                    <th className="text-right pb-2 font-medium text-slate-600">Qty</th>
                    <th className="text-right pb-2 font-medium text-slate-600">Cost</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {expenses.byItem.map((row) => (
                    <tr key={row.itemId}>
                      <td className="py-2 text-slate-700">{row.itemName}</td>
                      <td className="py-2 text-right text-slate-600">{row.totalUsed}</td>
                      <td className="py-2 text-right font-medium text-slate-900">
                        {row.totalCost != null ? `$${row.totalCost.toFixed(2)}` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}
