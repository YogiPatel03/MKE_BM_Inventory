import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Flame, MapPin, Scale } from "lucide-react";
import { getItem } from "@/api/items";
import { listTransactions } from "@/api/transactions";
import { apiClient } from "@/api/client";
import { CheckoutModal } from "@/components/transactions/CheckoutModal";
import { TransactionRow } from "@/components/transactions/TransactionRow";
import { MarkAsUsedModal } from "@/components/modals/MarkAsUsedModal";
import { StockAdjustModal } from "@/components/modals/StockAdjustModal";
import { MoveModal } from "@/components/modals/MoveModal";
import { useAuthStore } from "@/store/auth";
import type { Bin, Cabinet, UsageEvent } from "@/types";

async function fetchCabinets(): Promise<Cabinet[]> {
  const { data } = await apiClient.get("/cabinets");
  return data;
}

async function fetchBins(cabinetId: number): Promise<Bin[]> {
  const { data } = await apiClient.get("/bins", { params: { cabinet_id: cabinetId } });
  return data;
}

async function fetchUsageEvents(itemId: number): Promise<UsageEvent[]> {
  const { data } = await apiClient.get(`/usage-events/item/${itemId}`);
  return data;
}

export function ItemDetailPage() {
  const { id } = useParams<{ id: string }>();
  const itemId = Number(id);
  const user = useAuthStore((s) => s.user);
  const canManage = user?.role.canManageInventory || user?.role.canManageUsers;

  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [markUsedOpen, setMarkUsedOpen] = useState(false);
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);

  const { data: item, isLoading } = useQuery({
    queryKey: ["item", itemId],
    queryFn: () => getItem(itemId),
  });

  const { data: transactions = [] } = useQuery({
    queryKey: ["transactions", "item", itemId],
    queryFn: () => listTransactions({ item_id_filter: itemId, limit: 50 }),
    enabled: !!item && !item.isConsumable,
  });

  const { data: usageEvents = [] } = useQuery<UsageEvent[]>({
    queryKey: ["usage-events", itemId],
    queryFn: () => fetchUsageEvents(itemId),
    enabled: !!item && item.isConsumable,
  });

  const { data: cabinets = [] } = useQuery<Cabinet[]>({
    queryKey: ["cabinets"],
    queryFn: fetchCabinets,
  });

  const { data: bins = [] } = useQuery<Bin[]>({
    queryKey: ["bins", item?.cabinetId],
    queryFn: () => fetchBins(item!.cabinetId),
    enabled: !!item,
  });

  if (isLoading) {
    return <div className="animate-pulse h-8 bg-slate-100 rounded w-48" />;
  }
  if (!item) return <p className="text-slate-500">Item not found.</p>;

  const cabinetName = cabinets.find((c) => c.id === item.cabinetId)?.name ?? `Cabinet ${item.cabinetId}`;
  const binLabel = item.binId ? (bins.find((b) => b.id === item.binId)?.label ?? `Bin ${item.binId}`) : null;

  const conditionColor: Record<string, string> = {
    GOOD: "badge-green",
    FAIR: "badge-yellow",
    POOR: "badge-red",
    DAMAGED: "badge-red",
  };

  const isInBin = item.binId !== null;

  return (
    <div className="space-y-6">
      <div>
        <Link
          to={`/inventory/cabinets/${item.cabinetId}`}
          className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-3"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to {cabinetName}
        </Link>

        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{item.name}</h1>
            {item.sku && <p className="text-xs text-slate-400 mt-0.5">SKU: {item.sku}</p>}
            {item.description && (
              <p className="text-sm text-slate-600 mt-2">{item.description}</p>
            )}
          </div>
          <div className="flex gap-2 flex-wrap">
            {/* Consumable: mark as used */}
            {item.isConsumable && item.quantityAvailable > 0 && (
              <button onClick={() => setMarkUsedOpen(true)} className="btn-primary bg-amber-600 hover:bg-amber-700">
                <Flame className="h-4 w-4" />
                Mark as used
              </button>
            )}
            {/* Non-consumable, not in a bin: checkout */}
            {!item.isConsumable && !isInBin && item.quantityAvailable > 0 && (
              <button onClick={() => setCheckoutOpen(true)} className="btn-primary">
                Check out
              </button>
            )}
            {/* In bin: show info only */}
            {isInBin && (
              <span className="inline-flex items-center gap-1.5 text-xs bg-slate-100 text-slate-600 px-3 py-1.5 rounded-lg">
                <MapPin className="h-3.5 w-3.5" />
                Check out via bin
              </span>
            )}
            {canManage && (
              <>
                <button onClick={() => setAdjustOpen(true)} className="btn-secondary">
                  <Scale className="h-4 w-4" />
                  Adjust stock
                </button>
                <button onClick={() => setMoveOpen(true)} className="btn-secondary">
                  <MapPin className="h-4 w-4" />
                  Move
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Bin restriction notice */}
      {isInBin && !item.isConsumable && (
        <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3 text-sm text-slate-600">
          This item is inside <strong>{binLabel}</strong>. To check it out, check out the entire bin.
        </div>
      )}

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
            {cabinetName}
            {binLabel ? ` / ${binLabel}` : " (direct)"}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Type</p>
          <span className={item.isConsumable ? "badge-yellow" : "badge-slate"}>
            {item.isConsumable ? "Consumable" : "Standard"}
          </span>
        </div>
        {item.unitPrice != null && (
          <div>
            <p className="text-xs text-slate-500">Unit price</p>
            <p className="text-sm font-medium text-slate-700">${item.unitPrice.toFixed(2)}</p>
          </div>
        )}
        <div>
          <p className="text-xs text-slate-500">Status</p>
          <span className={item.isActive ? "badge-green" : "badge-slate"}>
            {item.isActive ? "Active" : "Inactive"}
          </span>
        </div>
      </div>

      {/* Consumable usage history */}
      {item.isConsumable && (
        <div>
          <h2 className="text-base font-semibold text-slate-900 mb-3">Usage History</h2>
          <div className="card divide-y divide-slate-100 overflow-hidden">
            {usageEvents.length === 0 ? (
              <p className="py-8 text-center text-sm text-slate-400">No usage events yet</p>
            ) : (
              usageEvents.map((evt) => (
                <div key={evt.id} className="px-4 py-3 flex items-center justify-between text-sm">
                  <div>
                    <span className="font-medium text-slate-900">Used {evt.quantityUsed}</span>
                    {evt.notes && (
                      <span className="text-slate-400 ml-2">— {evt.notes}</span>
                    )}
                  </div>
                  <span className="text-xs text-slate-400">
                    {new Date(evt.usedAt).toLocaleDateString()}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Non-consumable transaction history */}
      {!item.isConsumable && (
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
      )}

      {checkoutOpen && item && (
        <CheckoutModal item={item} onClose={() => setCheckoutOpen(false)} />
      )}
      {markUsedOpen && item && (
        <MarkAsUsedModal item={item} onClose={() => setMarkUsedOpen(false)} />
      )}
      {adjustOpen && item && (
        <StockAdjustModal item={item} onClose={() => setAdjustOpen(false)} />
      )}
      {moveOpen && item && (
        <MoveModal
          entityType="item"
          entityId={item.id}
          entityName={item.name}
          currentCabinetId={item.cabinetId}
          currentBinId={item.binId}
          onClose={() => setMoveOpen(false)}
        />
      )}
    </div>
  );
}
