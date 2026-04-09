import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Box, CheckCircle, ClipboardList, Clock, ShoppingCart } from "lucide-react";
import { listTransactions } from "@/api/transactions";
import { getInventoryStatus } from "@/api/reports";
import { useAuthStore } from "@/store/auth";
import { TransactionRow } from "@/components/transactions/TransactionRow";
import { format } from "date-fns";
import { Link } from "react-router-dom";

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
