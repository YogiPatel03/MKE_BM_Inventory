import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import { findBinByNumber } from "@/api/cabinets";
import { submitRequest } from "@/api/requests";
import { toast } from "@/store/toast";
import type { CheckoutPurpose } from "@/types";

interface Props {
  onClose: () => void;
}

export function BinRequestModal({ onClose }: Props) {
  const qc = useQueryClient();
  const [binNumber, setBinNumber] = useState("");
  const [reason, setReason] = useState("");
  const [purpose, setPurpose] = useState<CheckoutPurpose>("GENERAL");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEscapeKey(() => { if (!loading) onClose(); });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;
    const trimmed = binNumber.trim();
    if (!trimmed) {
      setError("Please enter a bin number.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const bin = await findBinByNumber(trimmed);
      if (!bin) {
        setError(`Bin number "${trimmed}" not found.`);
        return;
      }
      await submitRequest({ binId: bin.id, reason: reason.trim() || undefined, purpose });
      qc.invalidateQueries({ queryKey: ["requests"] });
      qc.invalidateQueries({ queryKey: ["activity"] });
      toast.success("Request submitted successfully.");
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to submit request.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50"
      onClick={(e) => { if (e.target === e.currentTarget && !loading) onClose(); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="bin-request-modal-title"
        className="card w-full max-w-md p-6"
      >
        <h2 id="bin-request-modal-title" className="text-lg font-semibold text-slate-900 mb-4">
          Request bin
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="bin-request-number" className="label">
              Bin number <span className="text-red-500">*</span>
            </label>
            <input
              id="bin-request-number"
              className="input"
              placeholder="e.g. B-01"
              value={binNumber}
              onChange={(e) => { setBinNumber(e.target.value); setError(""); }}
              autoFocus
            />
          </div>

          <div>
            <label htmlFor="bin-request-reason" className="label">
              Reason <span className="text-slate-400 font-normal">(optional)</span>
            </label>
            <input
              id="bin-request-reason"
              className="input"
              placeholder="e.g. needed for event setup"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>

          <div>
            <p className="label mb-1.5">Checkout purpose</p>
            <div className="flex gap-2">
              {(["GENERAL", "SABHA"] as const).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPurpose(p)}
                  className={`flex-1 rounded-lg border px-3 py-2.5 text-sm font-medium text-left transition-colors ${
                    purpose === p
                      ? "border-brand-600 bg-brand-50 text-brand-700"
                      : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  <span className="block">{p === "GENERAL" ? "General use" : "Sabha"}</span>
                  <span className="block text-xs font-normal mt-0.5 text-slate-400">
                    {p === "GENERAL"
                      ? "Does not appear on the Sabha checklist."
                      : "Adds this item to the Sabha return checklist."}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
          )}

          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="btn-secondary flex-1 justify-center"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="btn-primary flex-1 justify-center"
            >
              {loading ? "Submitting…" : "Submit request"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
