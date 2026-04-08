import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { MessageSquare, X } from "lucide-react";
import { returnItem } from "@/api/transactions";
import type { Transaction } from "@/types";

interface Props {
  transaction: Transaction;
  onClose: () => void;
}

export function ReturnModal({ transaction, onClose }: Props) {
  const qc = useQueryClient();
  const [notes, setNotes] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError("");
    try {
      await returnItem(transaction.id, { notes: notes || undefined });
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["items"] });
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Return failed");
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

        <h2 className="text-lg font-semibold text-slate-900 mb-1">Return Item</h2>
        <p className="text-sm text-slate-500 mb-1">Transaction #{transaction.id}</p>

        {/* Photo notice */}
        <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg p-3 mb-5">
          <MessageSquare className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-amber-800">
            After submitting, the Telegram bot will ask you to provide a condition photo in the
            coordinator channel.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Return notes (optional)</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              className="input resize-none"
              placeholder="Condition on return, any damage, etc."
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
              {isLoading ? "Processing…" : "Confirm return"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
