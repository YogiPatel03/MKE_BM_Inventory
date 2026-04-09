import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Edit2, Flame, MapPin, RotateCcw, Scale } from "lucide-react";
import { getItem, updateItem } from "@/api/items";
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

async function reverseUsageEvent(eventId: number, notes?: string): Promise<void> {
  await apiClient.post(`/usage-events/${eventId}/reverse`, { notes });
}

// Inline edit form for name/description/price
function InlineEditModal({
  item,
  onClose,
}: {
  item: { id: number; name: string; description: string | null; unitPrice: number | null; lowStockThreshold: number | null };
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState(item.name);
  const [description, setDescription] = useState(item.description ?? "");
  const [unitPrice, setUnitPrice] = useState(item.unitPrice?.toString() ?? "");
  const [threshold, setThreshold] = useState(item.lowStockThreshold?.toString() ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await updateItem(item.id, {
        name: name.trim(),
        description: description.trim() || null,
        unitPrice: unitPrice ? parseFloat(unitPrice) : undefined,
        lowStockThreshold: threshold ? parseInt(threshold, 10) : undefined,
      });
      qc.invalidateQueries({ queryKey: ["item", item.id] });
      qc.invalidateQueries({ queryKey: ["activity"] });
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to save changes");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50">
      <div className="card w-full max-w-md p-6 relative">
        <h2 className="text-lg font-semibold text-slate-900 mb-4">Edit Item</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Name *</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div>
            <label className="label">Description</label>
            <textarea className="input" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div>
            <label className="label">Unit price ($)</label>
            <input
              type="number"
              step="0.01"
              min="0"
              className="input"
              value={unitPrice}
              onChange={(e) => setUnitPrice(e.target.value)}
              placeholder="e.g. 4.99"
            />
          </div>
          <div>
            <label className="label">Low stock threshold</label>
            <input
              type="number"
              min="0"
              className="input"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              placeholder="Leave blank to use 10% of total"
            />
            <p className="text-xs text-slate-400 mt-1">Alert fires when available ≤ this value. Blank = 10% of total.</p>
          </div>
          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary flex-1 justify-center">Cancel</button>
            <button type="submit" disabled={loading} className="btn-primary flex-1 justify-center">
              {loading ? "Saving…" : "Save changes"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function ItemDetailPage() {
  const { id } = useParams<{ id: string }>();
  const itemId = Number(id);
  const user = useAuthStore((s) => s.user);
  const canManage = user?.role.canManageInventory;
  const qc = useQueryClient();

  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [markUsedOpen, setMarkUsedOpen] = useState(false);
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [reversingId, setReversingId] = useState<number | null>(null);

  const { data: item, isLoading } = useQuery({
    queryKey: ["item", itemId],
    queryFn: () => getItem(itemId),
  });

  const { data: transactions = [] } = useQuery({
    queryKey: ["transactions", "item", itemId],
    queryFn: () => listTransactions({ item_id_filter: itemId, limit: 50 }),
    enabled: !!item && !item.isConsumable,
  });

  const { data: usageEvents = [], refetch: refetchUsage } = useQuery<UsageEvent[]>({
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

  const handleReverse = async (eventId: number) => {
    if (!confirm("Reverse this usage event? This will restore the consumed stock.")) return;
    setReversingId(eventId);
    try {
      await reverseUsageEvent(eventId, "Reversed from UI");
      await refetchUsage();
      qc.invalidateQueries({ queryKey: ["item", itemId] });
      qc.invalidateQueries({ queryKey: ["activity"] });
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? "Failed to reverse usage event");
    } finally {
      setReversingId(null);
    }
  };

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
            {/* Edit button for coordinators+ */}
            {canManage && (
              <button onClick={() => setEditOpen(true)} className="btn-secondary">
                <Edit2 className="h-4 w-4" />
                Edit
              </button>
            )}
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
        {item.lowStockThreshold != null && (
          <div>
            <p className="text-xs text-slate-500">Low stock threshold</p>
            <p className="text-sm font-medium text-slate-700">{item.lowStockThreshold}</p>
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
                    <div className="flex items-center gap-2">
                      {evt.isReversal ? (
                        <span className="badge-blue text-xs">Reversed</span>
                      ) : (
                        <span className="font-medium text-slate-900">Used {evt.quantityUsed}</span>
                      )}
                      {evt.reversesEventId && (
                        <span className="text-xs text-slate-400">↩ reversal of #{evt.reversesEventId}</span>
                      )}
                    </div>
                    {evt.notes && (
                      <span className="text-slate-400 text-xs ml-0">{evt.notes}</span>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-slate-400">
                      {new Date(evt.usedAt).toLocaleDateString()}
                    </span>
                    {canManage && !evt.isReversal && !usageEvents.some((e) => e.reversesEventId === evt.id) && (
                      <button
                        className="text-xs text-slate-400 hover:text-red-600 flex items-center gap-1"
                        onClick={() => handleReverse(evt.id)}
                        disabled={reversingId === evt.id}
                      >
                        <RotateCcw className="h-3 w-3" />
                        {reversingId === evt.id ? "…" : "Reverse"}
                      </button>
                    )}
                  </div>
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
      {editOpen && item && (
        <InlineEditModal item={item} onClose={() => setEditOpen(false)} />
      )}
    </div>
  );
}
