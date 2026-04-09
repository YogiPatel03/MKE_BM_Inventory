import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Scale, X } from "lucide-react";
import { adjustStock } from "@/api/stockAdjustments";
import type { Item } from "@/types";

const REASONS = ["CORRECTION", "DAMAGED", "LOST", "RESTOCK", "AUDIT", "OTHER"] as const;

interface Props {
  item: Item;
  onClose: () => void;
}

export function StockAdjustModal({ item, onClose }: Props) {
  const qc = useQueryClient();
  const [delta, setDelta] = useState<string>("");
  const [reason, setReason] = useState<string>("CORRECTION");
  const [notes, setNotes] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const deltaNum = delta === "" ? 0 : parseInt(delta, 10);
  const newTotal = item.quantityTotal + (isNaN(deltaNum) ? 0 : deltaNum);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!delta || isNaN(deltaNum) || deltaNum === 0) return;
    setIsLoading(true);
    setError("");
    try {
      await adjustStock({
        itemId: item.id,
        delta: deltaNum,
        reason,
        notes: notes || undefined,
      });
      qc.invalidateQueries({ queryKey: ["item", item.id] });
      qc.invalidateQueries({ queryKey: ["all-items"] });
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Adjustment failed");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50">
      <div className="card w-full max-w-sm p-6 relative">
        <button onClick={onClose} className="absolute top-4 right-4 text-slate-400 hover:text-slate-700">
          <X className="h-5 w-5" />
        </button>
        <div className="flex items-center gap-2 mb-4">
          <Scale className="h-5 w-5 text-brand-600" />
          <h2 className="text-lg font-semibold text-slate-900">Adjust Stock</h2>
        </div>
        <p className="text-sm text-slate-500 mb-4">
          <strong className="text-slate-700">{item.name}</strong> — current total:{" "}
          <strong>{item.quantityTotal}</strong>, available: <strong>{item.quantityAvailable}</strong>.
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Adjustment (+/-) *</label>
            <input
              type="number"
              className="input"
              placeholder="e.g. +5 or -2"
              value={delta}
              onChange={(e) => setDelta(e.target.value)}
              required
            />
            {delta !== "" && !isNaN(deltaNum) && deltaNum !== 0 && (
              <p className="text-xs mt-1 text-slate-500">
                New total will be{" "}
                <strong className={newTotal < 0 ? "text-red-600" : "text-slate-800"}>
                  {newTotal}
                </strong>
              </p>
            )}
          </div>
          <div>
            <label className="label">Reason *</label>
            <select className="input" value={reason} onChange={(e) => setReason(e.target.value)}>
              {REASONS.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Notes (optional)</label>
            <input
              className="input"
              placeholder="Additional context"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary flex-1 justify-center">
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading || !delta || isNaN(deltaNum) || deltaNum === 0 || newTotal < 0}
              className="btn-primary flex-1 justify-center"
            >
              {isLoading ? "Saving…" : "Apply"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
