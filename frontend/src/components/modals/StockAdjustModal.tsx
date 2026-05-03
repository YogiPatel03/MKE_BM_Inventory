import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Scale, X } from "lucide-react";
import { adjustStock } from "@/api/stockAdjustments";
import { useEscapeKey } from "@/hooks/useEscapeKey";
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
  useEscapeKey(onClose);

  const deltaNum = delta === "" ? 0 : parseFloat(delta);
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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="stock-adjust-title"
        className="card w-full max-w-sm p-6 relative"
      >
        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute top-4 right-4 p-1.5 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
        <div className="flex items-center gap-2 mb-4">
          <Scale className="h-5 w-5 text-brand-600" aria-hidden="true" />
          <h2 id="stock-adjust-title" className="text-lg font-semibold text-slate-900">Adjust Stock</h2>
        </div>
        <p className="text-sm text-slate-500 mb-4">
          <strong className="text-slate-700">{item.name}</strong> — current total:{" "}
          <strong>{item.quantityTotal}</strong>, available: <strong>{item.quantityAvailable}</strong>.
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="stock-adjust-delta" className="label">Adjustment (+/-) *</label>
            <input
              id="stock-adjust-delta"
              type="number"
              step={0.01}
              className="input"
              placeholder="e.g. +5 or -2.5"
              value={delta}
              onChange={(e) => setDelta(e.target.value)}
              required
              autoFocus
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
            <label htmlFor="stock-adjust-reason" className="label">Reason *</label>
            <select id="stock-adjust-reason" className="input" value={reason} onChange={(e) => setReason(e.target.value)}>
              {REASONS.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="stock-adjust-notes" className="label">Notes (optional)</label>
            <input
              id="stock-adjust-notes"
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
