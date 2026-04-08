import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ClipboardList, Filter } from "lucide-react";
import { listTransactions } from "@/api/transactions";
import { useAuthStore } from "@/store/auth";
import { TransactionRow } from "@/components/transactions/TransactionRow";
import type { TransactionStatus } from "@/types";

const STATUS_OPTIONS: { value: TransactionStatus | ""; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "CHECKED_OUT", label: "Checked out" },
  { value: "OVERDUE", label: "Overdue" },
  { value: "RETURNED", label: "Returned" },
  { value: "CANCELLED", label: "Cancelled" },
];

export function TransactionsPage() {
  const user = useAuthStore((s) => s.user);
  const canViewAll = user?.role.canViewAllTransactions ?? false;
  const [statusFilter, setStatusFilter] = useState<TransactionStatus | "">("");

  const { data: transactions = [], isLoading } = useQuery({
    queryKey: ["transactions", statusFilter],
    queryFn: () =>
      listTransactions({
        status_filter: statusFilter || undefined,
        limit: 100,
      }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Transactions</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {canViewAll ? "All transactions" : "Your transactions"}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-slate-400" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as TransactionStatus | "")}
            className="input py-1.5 text-sm w-auto"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="card overflow-hidden divide-y divide-slate-100">
        {isLoading ? (
          <div className="py-10 text-center">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-brand-600 border-t-transparent mx-auto" />
          </div>
        ) : transactions.length === 0 ? (
          <div className="py-16 text-center">
            <ClipboardList className="h-10 w-10 text-slate-300 mx-auto mb-3" />
            <p className="text-slate-500">No transactions found</p>
          </div>
        ) : (
          transactions.map((t) => <TransactionRow key={t.id} transaction={t} />)
        )}
      </div>
    </div>
  );
}
