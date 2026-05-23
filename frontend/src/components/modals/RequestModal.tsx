import { useState } from "react";
import { useEscapeKey } from "@/hooks/useEscapeKey";
import type { CheckoutPurpose } from "@/types";

interface Props {
  title: string;
  confirmLabel?: string;
  onConfirm: (reason: string, purpose: CheckoutPurpose) => void;
  onCancel: () => void;
}

export function RequestModal({
  title,
  confirmLabel = "Submit request",
  onConfirm,
  onCancel,
}: Props) {
  const [reason, setReason] = useState("");
  const [purpose, setPurpose] = useState<CheckoutPurpose>("GENERAL");
  useEscapeKey(onCancel);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onConfirm(reason, purpose);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50"
      onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="request-modal-title"
        className="card w-full max-w-md p-6"
      >
        <h2 id="request-modal-title" className="text-lg font-semibold text-slate-900 mb-4">
          {title}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="request-modal-reason" className="label">
              Reason <span className="text-slate-400 font-normal">(optional)</span>
            </label>
            <input
              id="request-modal-reason"
              className="input"
              placeholder="e.g. needed for event setup"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              autoFocus
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

          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onCancel} className="btn-secondary flex-1 justify-center">
              Cancel
            </button>
            <button type="submit" className="btn-primary flex-1 justify-center">
              {confirmLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
