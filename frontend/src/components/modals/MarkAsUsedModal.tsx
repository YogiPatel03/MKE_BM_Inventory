import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Flame, X } from "lucide-react";
import { markAsUsed } from "@/api/usage";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import type { Item } from "@/types";

interface Props {
  item: Item;
  onClose: () => void;
}

export function MarkAsUsedModal({ item, onClose }: Props) {
  const qc = useQueryClient();
  const [qty, setQty] = useState(1.0);
  const [notes, setNotes] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  useEscapeKey(onClose);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (qty <= 0 || qty > item.quantityAvailable) return;
    setIsLoading(true);
    setError("");
    try {
      await markAsUsed({ itemId: item.id, quantityUsed: qty, notes: notes || undefined });
      qc.invalidateQueries({ queryKey: ["item", item.id] });
      qc.invalidateQueries({ queryKey: ["all-items"] });
      qc.invalidateQueries({ queryKey: ["usage-events", item.id] });
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to mark as used");
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
        aria-labelledby="mark-used-title"
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
          <Flame className="h-5 w-5 text-amber-500" aria-hidden="true" />
          <h2 id="mark-used-title" className="text-lg font-semibold text-slate-900">Mark as Used</h2>
        </div>
        <p className="text-sm text-slate-500 mb-4">
          <strong className="text-slate-700">{item.name}</strong> — {item.quantityAvailable} available.
          Marking as used permanently reduces stock.
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="mark-used-qty" className="label">Quantity used *</label>
            <input
              id="mark-used-qty"
              type="number"
              min={0.01}
              max={item.quantityAvailable}
              step={0.01}
              className="input"
              value={qty}
              onChange={(e) => setQty(parseFloat(e.target.value) || 0)}
              required
              autoFocus
            />
            <p className="text-xs text-slate-400 mt-1">Max: {item.quantityAvailable}</p>
          </div>
          <div>
            <label htmlFor="mark-used-notes" className="label">Notes (optional)</label>
            <input
              id="mark-used-notes"
              className="input"
              placeholder="e.g. Used for event setup"
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
              disabled={isLoading || qty < 1 || qty > item.quantityAvailable}
              className="btn-primary flex-1 justify-center bg-amber-600 hover:bg-amber-700"
            >
              {isLoading ? "Saving…" : `Use ${qty}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
