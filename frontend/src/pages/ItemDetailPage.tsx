import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { getItem } from "@/api/items";
import { listTransactions } from "@/api/transactions";
import { useAuthStore } from "@/store/auth";
import { CheckoutModal } from "@/components/transactions/CheckoutModal";
import { TransactionRow } from "@/components/transactions/TransactionRow";

export function ItemDetailPage() {
  const { id } = useParams<{ id: string }>();
  const itemId = Number(id);
  const user = useAuthStore((s) => s.user);
  const [checkoutOpen, setCheckoutOpen] = useState(false);

  const { data: item, isLoading } = useQuery({
    queryKey: ["item", itemId],
    queryFn: () => getItem(itemId),
  });

  const { data: transactions = [] } = useQuery({
    queryKey: ["transactions", "item", itemId],
    queryFn: () => listTransactions({ item_id_filter: itemId, limit: 50 }),
  });

  if (isLoading) {
    return <div className="animate-pulse h-8 bg-slate-100 rounded w-48" />;
  }
  if (!item) return <p className="text-slate-500">Item not found.</p>;

  const conditionColor: Record<string, string> = {
    GOOD: "badge-green",
    FAIR: "badge-yellow",
    POOR: "badge-red",
    DAMAGED: "badge-red",
  };

  return (
    <div className="space-y-6">
      <div>
        <Link
          to={`/inventory/cabinets/${item.cabinetId}`}
          className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-3"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to cabinet
        </Link>

        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{item.name}</h1>
            {item.sku && <p className="text-xs text-slate-400 mt-0.5">SKU: {item.sku}</p>}
            {item.description && (
              <p className="text-sm text-slate-600 mt-2">{item.description}</p>
            )}
          </div>
          {item.quantityAvailable > 0 && (
            <button onClick={() => setCheckoutOpen(true)} className="btn-primary">
              Check out
            </button>
          )}
        </div>
      </div>

      {/* Attributes */}
      <div className="card p-5 grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div>
          <p className="text-xs text-slate-500">Available</p>
          <p className="text-xl font-bold text-slate-900">
            {item.quantityAvailable}
            <span className="text-sm font-normal text-slate-400">/{item.quantityTotal}</span>
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Condition</p>
          <span className={conditionColor[item.condition] ?? "badge-slate"}>
            {item.condition}
          </span>
        </div>
        <div>
          <p className="text-xs text-slate-500">Location</p>
          <p className="text-sm font-medium text-slate-700">
            Cabinet {item.cabinetId}
            {item.binId ? ` / Bin ${item.binId}` : " (direct)"}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Status</p>
          <span className={item.isActive ? "badge-green" : "badge-slate"}>
            {item.isActive ? "Active" : "Inactive"}
          </span>
        </div>
      </div>

      {/* Transaction history */}
      <div>
        <h2 className="text-base font-semibold text-slate-900 mb-3">Transaction History</h2>
        <div className="card divide-y divide-slate-100 overflow-hidden">
          {transactions.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-400">No transactions yet</p>
          ) : (
            transactions.map((t) => <TransactionRow key={t.id} transaction={t} />)
          )}
        </div>
      </div>

      {checkoutOpen && item && (
        <CheckoutModal item={item} onClose={() => setCheckoutOpen(false)} />
      )}
    </div>
  );
}
