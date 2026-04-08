import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { createBin } from "@/api/cabinets";

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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50">
      <div className="card w-full max-w-md p-6 relative">
        <button onClick={onClose} className="absolute top-4 right-4 text-slate-400 hover:text-slate-700">
          <X className="h-5 w-5" />
        </button>
        <h2 className="text-lg font-semibold text-slate-900 mb-5">Add Bin</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Label *</label>
            <input className="input" placeholder="e.g. A1, Top shelf" value={label} onChange={(e) => setLabel(e.target.value)} required />
          </div>
          <div>
            <label className="label">Location note</label>
            <input className="input" placeholder="e.g. Left side, second row" value={locationNote} onChange={(e) => setLocationNote(e.target.value)} />
          </div>
          <div>
            <label className="label">Description</label>
            <textarea className="input resize-none" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
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
