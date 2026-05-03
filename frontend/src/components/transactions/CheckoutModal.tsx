import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { checkout } from "@/api/transactions";
import { useAuthStore } from "@/store/auth";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import type { Item } from "@/types";

interface Props {
  item: Item;
  onClose: () => void;
}

export function CheckoutModal({ item, onClose }: Props) {
  const user = useAuthStore((s) => s.user);
  const qc = useQueryClient();

  const [quantity, setQuantity] = useState(1.0);
  const [dueAt, setDueAt] = useState("");
  const [notes, setNotes] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  useEscapeKey(onClose);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) return;
    setIsLoading(true);
    setError("");
    try {
      await checkout({
        itemId: item.id,
        userId: user.id,
        quantity,
        dueAt: dueAt || undefined,
        notes: notes || undefined,
      });
      qc.invalidateQueries({ queryKey: ["items"] });
      qc.invalidateQueries({ queryKey: ["transactions"] });
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Checkout failed");
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
        aria-labelledby="checkout-modal-title"
        className="card w-full max-w-md p-6 relative"
      >
        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute top-4 right-4 p-1.5 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
        >
          <X className="h-4 w-4" />
        </button>

        <h2 id="checkout-modal-title" className="text-lg font-semibold text-slate-900 mb-1">Check Out Item</h2>
        <p className="text-sm text-slate-500 mb-5">
          {item.name} — {Number.isInteger(item.quantityAvailable) ? item.quantityAvailable : item.quantityAvailable.toFixed(2)} available
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="checkout-qty" className="label">Quantity</label>
            <input
              id="checkout-qty"
              type="number"
              min={0.01}
              max={item.quantityAvailable}
              step={0.01}
              value={quantity}
              onChange={(e) => setQuantity(parseFloat(e.target.value) || 0)}
              className="input"
              required
              autoFocus
            />
          </div>

          <div>
            <label htmlFor="checkout-due" className="label">Due Date (optional)</label>
            <input
              id="checkout-due"
              type="date"
              value={dueAt}
              onChange={(e) => setDueAt(e.target.value)}
              className="input"
              min={new Date().toISOString().split("T")[0]}
            />
          </div>

          <div>
            <label htmlFor="checkout-notes" className="label">Notes (optional)</label>
            <textarea
              id="checkout-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="input resize-none"
              placeholder="Purpose, project, etc."
            />
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
          )}

          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary flex-1 justify-center">
              Cancel
            </button>
            <button type="submit" disabled={isLoading} className="btn-primary flex-1 justify-center">
              {isLoading ? "Processing…" : "Check out"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
