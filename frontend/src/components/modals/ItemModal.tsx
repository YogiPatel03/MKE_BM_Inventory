import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { createItem } from "@/api/items";
import type { Bin } from "@/types";

interface Props {
  cabinetId: number;
  bins: Bin[];
  onClose: () => void;
}

const CONDITIONS = ["GOOD", "FAIR", "POOR", "DAMAGED"] as const;

export function ItemModal({ cabinetId, bins, onClose }: Props) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [quantityTotal, setQuantityTotal] = useState(1);
  const [sku, setSku] = useState("");
  const [condition, setCondition] = useState("GOOD");
  const [binId, setBinId] = useState<number | "">("");
  const [isConsumable, setIsConsumable] = useState(false);
  const [unitPrice, setUnitPrice] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError("");
    try {
      await createItem({
        name,
        description: description || undefined,
        quantityTotal,
        cabinetId,
        binId: binId !== "" ? binId : undefined,
        sku: sku || undefined,
        condition,
        isConsumable,
        unitPrice: unitPrice !== "" ? parseFloat(unitPrice) : undefined,
      });
      qc.invalidateQueries({ queryKey: ["items"] });
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to create item");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50">
      <div className="card w-full max-w-md p-6 relative overflow-y-auto max-h-[90vh]">
        <button onClick={onClose} className="absolute top-4 right-4 text-slate-400 hover:text-slate-700">
          <X className="h-5 w-5" />
        </button>
        <h2 className="text-lg font-semibold text-slate-900 mb-5">Add Item</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Name *</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div>
            <label className="label">Description</label>
            <textarea className="input resize-none" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Quantity *</label>
              <input
                type="number"
                min={1}
                className="input"
                value={quantityTotal}
                onChange={(e) => setQuantityTotal(Number(e.target.value))}
                required
              />
            </div>
            <div>
              <label className="label">Condition</label>
              <select className="input" value={condition} onChange={(e) => setCondition(e.target.value)}>
                {CONDITIONS.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Consumable toggle — required decision at creation */}
          <div className="rounded-lg border border-slate-200 p-3 space-y-1">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={isConsumable}
                onChange={(e) => setIsConsumable(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 accent-brand-600"
              />
              <span className="text-sm font-medium text-slate-800">Consumable item</span>
            </label>
            <p className="text-xs text-slate-400 ml-7">
              {isConsumable
                ? "Stock reduces permanently when used. No checkout/return flow."
                : "Uses checkout / return flow. Stock is not permanently consumed."}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">SKU / Code</label>
              <input className="input" placeholder="Optional" value={sku} onChange={(e) => setSku(e.target.value)} />
            </div>
            <div>
              <label className="label">Unit price ($)</label>
              <input
                type="number"
                min={0}
                step="0.01"
                className="input"
                placeholder="0.00"
                value={unitPrice}
                onChange={(e) => setUnitPrice(e.target.value)}
              />
            </div>
          </div>

          {bins.length > 0 && (
            <div>
              <label className="label">Bin (optional)</label>
              <select className="input" value={binId} onChange={(e) => setBinId(e.target.value === "" ? "" : Number(e.target.value))}>
                <option value="">No bin (direct in cabinet)</option>
                {bins.map((b) => (
                  <option key={b.id} value={b.id}>{b.label}{b.locationNote ? ` — ${b.locationNote}` : ""}</option>
                ))}
              </select>
            </div>
          )}

          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary flex-1 justify-center">Cancel</button>
            <button type="submit" disabled={isLoading} className="btn-primary flex-1 justify-center">
              {isLoading ? "Creating…" : "Add item"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
