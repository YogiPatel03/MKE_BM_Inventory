import { useQuery } from "@tanstack/react-query";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Box, FolderOpen, MapPin, Plus } from "lucide-react";
import { getCabinet, listBins, listItems } from "@/api/cabinets";
import { useAuthStore } from "@/store/auth";
import type { Item } from "@/types";
import { CheckoutModal } from "@/components/transactions/CheckoutModal";
import { BinModal } from "@/components/modals/BinModal";
import { ItemModal } from "@/components/modals/ItemModal";
import { useState } from "react";

function ItemRow({ item }: { item: Item }) {
  const [checkoutOpen, setCheckoutOpen] = useState(false);

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
      </div>
      <div className="flex items-center gap-3 flex-shrink-0 ml-4">
        <span className={availColor}>
          {item.quantityAvailable}/{item.quantityTotal}
        </span>
        {item.quantityAvailable > 0 && (
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
    </div>
  );
}

export function CabinetDetailPage() {
  const { id } = useParams<{ id: string }>();
  const cabinetId = Number(id);
  const user = useAuthStore((s) => s.user);
  const canManage = user?.role.canManageInventory ?? false;

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

  const { data: allItems = [], isLoading: itemsLoading } = useQuery({
    queryKey: ["items", "cabinet", cabinetId],
    queryFn: () => listItems({ cabinet_id: cabinetId }),
  });

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
              <ItemRow key={item.id} item={item} />
            ))}
          </div>
        </div>
      )}

      {/* Bins */}
      {bins.length === 0 && directItems.length === 0 && (
        <div className="py-20 text-center">
          <Box className="h-10 w-10 text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500">No bins or items in this cabinet yet.</p>
        </div>
      )}

      {binModalOpen && <BinModal cabinetId={cabinetId} onClose={() => setBinModalOpen(false)} />}
      {itemModalOpen && <ItemModal cabinetId={cabinetId} bins={bins} onClose={() => setItemModalOpen(false)} />}

      {bins.map((bin) => (
        <div key={bin.id}>
          <div className="flex items-center gap-2 mb-2">
            <FolderOpen className="h-4 w-4 text-slate-400" />
            <h2 className="text-sm font-semibold text-slate-700">{bin.label}</h2>
            {bin.locationNote && (
              <span className="text-xs text-slate-400">— {bin.locationNote}</span>
            )}
          </div>
          <div className="card overflow-hidden divide-y divide-slate-100">
            {itemsByBin(bin.id).length === 0 ? (
              <p className="py-4 px-4 text-sm text-slate-400">No items in this bin</p>
            ) : (
              itemsByBin(bin.id).map((item) => <ItemRow key={item.id} item={item} />)
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
