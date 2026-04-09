import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Box, Edit2, Flame, FolderOpen, MapPin, Package, Plus, QrCode } from "lucide-react";
import { getCabinet, listBins, listItems, updateCabinet } from "@/api/cabinets";
import { checkoutBin, returnBin, listBinTransactions } from "@/api/binTransactions";
import { useAuthStore } from "@/store/auth";
import type { Bin, BinTransaction, Cabinet, Item } from "@/types";
import { CheckoutModal } from "@/components/transactions/CheckoutModal";
import { BinModal } from "@/components/modals/BinModal";
import { BinQRModal } from "@/components/modals/BinQRModal";
import { ItemModal } from "@/components/modals/ItemModal";
import { MarkAsUsedModal } from "@/components/modals/MarkAsUsedModal";
import { MoveModal } from "@/components/modals/MoveModal";

function EditCabinetModal({ cabinet, onClose }: { cabinet: Cabinet; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(cabinet.name);
  const [location, setLocation] = useState(cabinet.location ?? "");
  const [description, setDescription] = useState(cabinet.description ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await updateCabinet(cabinet.id, {
        name: name.trim(),
        location: location.trim() || null,
        description: description.trim() || null,
      });
      qc.invalidateQueries({ queryKey: ["cabinet", cabinet.id] });
      qc.invalidateQueries({ queryKey: ["cabinets"] });
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
        <h2 className="text-lg font-semibold text-slate-900 mb-4">Edit Cabinet</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Name *</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div>
            <label className="label">Location</label>
            <input className="input" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="e.g. Room 204, Shelf B" />
          </div>
          <div>
            <label className="label">Description</label>
            <textarea className="input resize-none" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
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

function ItemRow({ item, inBin }: { item: Item; inBin: boolean }) {
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [markUsedOpen, setMarkUsedOpen] = useState(false);

  const availColor =
    item.quantityAvailable === 0
      ? "badge-red"
      : item.quantityAvailable < item.quantityTotal
      ? "badge-yellow"
      : "badge-green";

  return (
    <div className="flex items-center justify-between py-3 px-4 hover:bg-slate-50 transition-colors">
      <div className="min-w-0">
        <Link
          to={`/inventory/items/${item.id}`}
          className="text-sm font-medium text-slate-900 hover:text-brand-700 truncate block"
        >
          {item.name}
        </Link>
        {item.sku && <p className="text-xs text-slate-400">SKU: {item.sku}</p>}
        <div className="flex items-center gap-2 mt-0.5">
          {item.isConsumable && (
            <span className="text-xs text-amber-600 font-medium">consumable</span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3 flex-shrink-0 ml-4">
        <span className={availColor}>
          {item.quantityAvailable}/{item.quantityTotal}
        </span>
        {/* Consumable: mark as used */}
        {item.isConsumable && item.quantityAvailable > 0 && (
          <button
            onClick={() => setMarkUsedOpen(true)}
            className="btn-primary text-xs py-1 px-3 bg-amber-600 hover:bg-amber-700"
          >
            <Flame className="h-3.5 w-3.5" />
            Use
          </button>
        )}
        {/* Non-consumable, not in bin: individual checkout */}
        {!item.isConsumable && !inBin && item.quantityAvailable > 0 && (
          <button
            onClick={() => setCheckoutOpen(true)}
            className="btn-primary text-xs py-1 px-3"
          >
            Check out
          </button>
        )}
      </div>
      {checkoutOpen && (
        <CheckoutModal item={item} onClose={() => setCheckoutOpen(false)} />
      )}
      {markUsedOpen && (
        <MarkAsUsedModal item={item} onClose={() => setMarkUsedOpen(false)} />
      )}
    </div>
  );
}

interface BinSectionProps {
  bin: Bin;
  items: Item[];
  cabinetId: number;
  canManage: boolean;
  canProcess: boolean;
  activeBinTxn: BinTransaction | undefined;
  onBinTxnChange: () => void;
}

function BinSection({ bin, items, cabinetId, canManage, canProcess, activeBinTxn, onBinTxnChange }: BinSectionProps) {
  const qc = useQueryClient();
  const [moveOpen, setMoveOpen] = useState(false);
  const [qrOpen, setQrOpen] = useState(false);
  const [checkoutNotes, setCheckoutNotes] = useState("");
  const [returnNotes, setReturnNotes] = useState("");
  const [showCheckoutForm, setShowCheckoutForm] = useState(false);
  const [showReturnForm, setShowReturnForm] = useState(false);

  const checkoutMut = useMutation({
    mutationFn: () => checkoutBin({ binId: bin.id, notes: checkoutNotes || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["items", "cabinet", cabinetId] });
      qc.invalidateQueries({ queryKey: ["bin-transactions"] });
      onBinTxnChange();
      setShowCheckoutForm(false);
      setCheckoutNotes("");
    },
  });

  const returnMut = useMutation({
    mutationFn: () => returnBin(activeBinTxn!.id, returnNotes || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["items", "cabinet", cabinetId] });
      qc.invalidateQueries({ queryKey: ["bin-transactions"] });
      onBinTxnChange();
      setShowReturnForm(false);
      setReturnNotes("");
    },
  });

  const hasItems = items.length > 0;
  const isCheckedOut = activeBinTxn !== undefined;

  return (
    <div className="space-y-2">
      {/* Bin header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <FolderOpen className="h-4 w-4 text-slate-400" />
          <h2 className="text-sm font-semibold text-slate-700">{bin.label}</h2>
          {bin.locationNote && (
            <span className="text-xs text-slate-400">— {bin.locationNote}</span>
          )}
          {isCheckedOut && (
            <span className="badge-yellow text-xs">Checked out</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {canManage && (
            <button
              onClick={() => setMoveOpen(true)}
              className="text-xs text-slate-400 hover:text-slate-600 flex items-center gap-1"
            >
              <MapPin className="h-3.5 w-3.5" /> Move bin
            </button>
          )}
          <button
            onClick={() => setQrOpen(true)}
            className="text-xs text-slate-400 hover:text-slate-600 flex items-center gap-1"
          >
            <QrCode className="h-3.5 w-3.5" /> QR
          </button>
          {canProcess && !isCheckedOut && hasItems && !showCheckoutForm && (
            <button
              onClick={() => setShowCheckoutForm(true)}
              className="btn-primary text-xs py-1 px-3"
            >
              <Package className="h-3.5 w-3.5" />
              Check out bin
            </button>
          )}
          {canProcess && isCheckedOut && !showReturnForm && (
            <button
              onClick={() => setShowReturnForm(true)}
              className="btn-secondary text-xs py-1 px-3"
            >
              Return bin
            </button>
          )}
        </div>
      </div>

      {/* Checkout form */}
      {showCheckoutForm && (
        <div className="rounded-lg border border-brand-200 bg-brand-50 p-3 space-y-2">
          <p className="text-xs font-medium text-brand-800">
            Check out all {items.length} item(s) in this bin as one unit
          </p>
          <input
            className="input text-sm"
            placeholder="Notes (optional)"
            value={checkoutNotes}
            onChange={(e) => setCheckoutNotes(e.target.value)}
          />
          {checkoutMut.isError && (
            <p className="text-xs text-red-600">{(checkoutMut.error as any)?.response?.data?.detail ?? "Failed"}</p>
          )}
          <div className="flex gap-2">
            <button onClick={() => { checkoutMut.mutate(); }} disabled={checkoutMut.isPending} className="btn-primary text-xs py-1 px-3">
              {checkoutMut.isPending ? "Checking out…" : "Confirm checkout"}
            </button>
            <button onClick={() => setShowCheckoutForm(false)} className="btn-secondary text-xs py-1 px-3">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Return form */}
      {showReturnForm && (
        <div className="rounded-lg border border-green-200 bg-green-50 p-3 space-y-2">
          <p className="text-xs font-medium text-green-800">Return all items in this bin</p>
          <input
            className="input text-sm"
            placeholder="Return notes (optional)"
            value={returnNotes}
            onChange={(e) => setReturnNotes(e.target.value)}
          />
          {returnMut.isError && (
            <p className="text-xs text-red-600">{(returnMut.error as any)?.response?.data?.detail ?? "Failed"}</p>
          )}
          <div className="flex gap-2">
            <button onClick={() => { returnMut.mutate(); }} disabled={returnMut.isPending} className="btn-primary text-xs py-1 px-3 bg-green-600 hover:bg-green-700">
              {returnMut.isPending ? "Returning…" : "Confirm return"}
            </button>
            <button onClick={() => setShowReturnForm(false)} className="btn-secondary text-xs py-1 px-3">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Items */}
      <div className="card overflow-hidden divide-y divide-slate-100">
        {items.length === 0 ? (
          <p className="py-4 px-4 text-sm text-slate-400">No items in this bin</p>
        ) : (
          items.map((item) => (
            <ItemRow key={item.id} item={item} inBin={!item.isConsumable} />
          ))
        )}
      </div>

      {moveOpen && (
        <MoveModal
          entityType="bin"
          entityId={bin.id}
          entityName={bin.label}
          currentCabinetId={cabinetId}
          onClose={() => setMoveOpen(false)}
        />
      )}
      {qrOpen && <BinQRModal bin={bin} onClose={() => setQrOpen(false)} />}
    </div>
  );
}

export function CabinetDetailPage() {
  const { id } = useParams<{ id: string }>();
  const cabinetId = Number(id);
  const user = useAuthStore((s) => s.user);
  const canManage = user?.role.canManageInventory ?? false;
  const canProcess = user?.role.canProcessAnyTransaction || user?.role.canManageUsers || false;
  useQueryClient(); // ensure query client available for child component mutations

  const { data: cabinet, isLoading: cabLoading } = useQuery({
    queryKey: ["cabinet", cabinetId],
    queryFn: () => getCabinet(cabinetId),
  });

  const { data: bins = [] } = useQuery({
    queryKey: ["bins", cabinetId],
    queryFn: () => listBins(cabinetId),
  });

  const [binModalOpen, setBinModalOpen] = useState(false);
  const [itemModalOpen, setItemModalOpen] = useState(false);
  const [editCabinetOpen, setEditCabinetOpen] = useState(false);

  const { data: allItems = [] } = useQuery({
    queryKey: ["items", "cabinet", cabinetId],
    queryFn: () => listItems({ cabinet_id: cabinetId }),
  });

  const { data: binTransactions = [], refetch: refetchBinTxns } = useQuery<BinTransaction[]>({
    queryKey: ["bin-transactions"],
    queryFn: listBinTransactions,
    enabled: canProcess,
  });

  // Map bin_id -> active BinTransaction
  const activeBinTxnMap = Object.fromEntries(
    binTransactions
      .filter((bt) => bt.status === "CHECKED_OUT")
      .map((bt) => [bt.binId, bt])
  );

  const directItems = allItems.filter((i) => !i.binId);
  const itemsByBin = (binId: number) => allItems.filter((i) => i.binId === binId);

  if (cabLoading) {
    return <div className="animate-pulse h-8 bg-slate-100 rounded w-48" />;
  }

  if (!cabinet) {
    return <p className="text-slate-500">Cabinet not found.</p>;
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link
          to="/inventory"
          className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-3"
        >
          <ArrowLeft className="h-4 w-4" />
          Inventory
        </Link>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{cabinet.name}</h1>
            {cabinet.location && (
              <p className="text-sm text-slate-500 flex items-center gap-1 mt-1">
                <MapPin className="h-3.5 w-3.5" />
                {cabinet.location}
              </p>
            )}
            {cabinet.description && (
              <p className="text-sm text-slate-600 mt-1">{cabinet.description}</p>
            )}
          </div>
          {canManage && (
            <div className="flex gap-2">
              <button className="btn-secondary text-xs" onClick={() => setEditCabinetOpen(true)}>
                <Edit2 className="h-4 w-4" />
                Edit
              </button>
              <button className="btn-secondary text-xs" onClick={() => setBinModalOpen(true)}>
                <Plus className="h-4 w-4" />
                Add Bin
              </button>
              <button className="btn-primary text-xs" onClick={() => setItemModalOpen(true)}>
                <Plus className="h-4 w-4" />
                Add Item
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Direct items (no bin) */}
      {directItems.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-2">
            Direct items
          </h2>
          <div className="card overflow-hidden divide-y divide-slate-100">
            {directItems.map((item) => (
              <ItemRow key={item.id} item={item} inBin={false} />
            ))}
          </div>
        </div>
      )}

      {/* Bins */}
      {bins.map((bin) => (
        <BinSection
          key={bin.id}
          bin={bin}
          items={itemsByBin(bin.id)}
          cabinetId={cabinetId}
          canManage={canManage}
          canProcess={canProcess}
          activeBinTxn={activeBinTxnMap[bin.id]}
          onBinTxnChange={() => refetchBinTxns()}
        />
      ))}

      {bins.length === 0 && directItems.length === 0 && (
        <div className="py-20 text-center">
          <Box className="h-10 w-10 text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500">No bins or items in this cabinet yet.</p>
        </div>
      )}

      {binModalOpen && <BinModal cabinetId={cabinetId} onClose={() => setBinModalOpen(false)} />}
      {itemModalOpen && <ItemModal cabinetId={cabinetId} bins={bins} onClose={() => setItemModalOpen(false)} />}
      {editCabinetOpen && cabinet && <EditCabinetModal cabinet={cabinet} onClose={() => setEditCabinetOpen(false)} />}
    </div>
  );
}
