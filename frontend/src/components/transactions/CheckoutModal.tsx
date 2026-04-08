import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { checkout } from "@/api/transactions";
import { useAuthStore } from "@/store/auth";
import type { Item } from "@/types";

interface Props {
  item: Item;
  onClose: () => void;
}

export function CheckoutModal({ item, onClose }: Props) {
  const user = useAuthStore((s) => s.user);
  const qc = useQueryClient();

  const [quantity, setQuantity] = useState(1);
  const [dueAt, setDueAt] = useState("");
  const [notes, setNotes] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50">
      <div className="card w-full max-w-md p-6 relative">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-slate-700"
        >
          <X className="h-5 w-5" />
        </button>

        <h2 className="text-lg font-semibold text-slate-900 mb-1">Check Out Item</h2>
        <p className="text-sm text-slate-500 mb-5">
          {item.name} — {item.quantityAvailable} available
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Quantity</label>
            <input
              type="number"
              min={1}
              max={item.quantityAvailable}
              value={quantity}
              onChange={(e) => setQuantity(Number(e.target.value))}
              className="input"
              required
            />
          </div>

          <div>
            <label className="label">Due Date (optional)</label>
            <input
              type="date"
              value={dueAt}
              onChange={(e) => setDueAt(e.target.value)}
              className="input"
              min={new Date().toISOString().split("T")[0]}
            />
          </div>

          <div>
            <label className="label">Notes (optional)</label>
            <textarea
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
