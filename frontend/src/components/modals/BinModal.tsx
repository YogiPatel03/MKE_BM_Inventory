import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { createBin } from "@/api/cabinets";
import { useEscapeKey } from "@/hooks/useEscapeKey";

interface Props {
  cabinetId: number;
  onClose: () => void;
}

export function BinModal({ cabinetId, onClose }: Props) {
  const qc = useQueryClient();
  const [label, setLabel] = useState("");
  const [locationNote, setLocationNote] = useState("");
  const [description, setDescription] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  useEscapeKey(onClose);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError("");
    try {
      await createBin({
        label,
        cabinetId,
        locationNote: locationNote || undefined,
        description: description || undefined,
      });
      qc.invalidateQueries({ queryKey: ["bins", cabinetId] });
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to create bin");
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
        aria-labelledby="bin-modal-title"
        className="card w-full max-w-md p-6 relative"
      >
        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute top-4 right-4 p-1.5 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
        <h2 id="bin-modal-title" className="text-lg font-semibold text-slate-900 mb-5">Add Bin</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="bin-label" className="label">Label *</label>
            <input id="bin-label" className="input" placeholder="e.g. A1, Top shelf" value={label} onChange={(e) => setLabel(e.target.value)} required autoFocus />
          </div>
          <div>
            <label htmlFor="bin-location-note" className="label">Location note</label>
            <input id="bin-location-note" className="input" placeholder="e.g. Left side, second row" value={locationNote} onChange={(e) => setLocationNote(e.target.value)} />
          </div>
          <div>
            <label htmlFor="bin-description" className="label">Description</label>
            <textarea id="bin-description" className="input resize-none" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary flex-1 justify-center">Cancel</button>
            <button type="submit" disabled={isLoading} className="btn-primary flex-1 justify-center">
              {isLoading ? "Creating…" : "Create bin"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
