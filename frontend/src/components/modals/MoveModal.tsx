import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MapPin, X } from "lucide-react";
import { apiClient } from "@/api/client";
import { listBins } from "@/api/cabinets";
import type { Bin, Cabinet } from "@/types";

type EntityType = "item" | "bin";

interface Props {
  entityType: EntityType;
  entityId: number;
  entityName: string;
  currentCabinetId: number;
  currentBinId?: number | null;
  onClose: () => void;
}

async function moveItem(itemId: number, toCabinetId: number, toBinId?: number, notes?: string) {
  const { data } = await apiClient.post("/moves/item", {
    item_id: itemId,
    to_cabinet_id: toCabinetId,
    to_bin_id: toBinId ?? null,
    notes,
  });
  return data;
}

async function moveBin(binId: number, toCabinetId: number, notes?: string) {
  const { data } = await apiClient.post("/moves/bin", {
    bin_id: binId,
    to_cabinet_id: toCabinetId,
    notes,
  });
  return data;
}

export function MoveModal({
  entityType,
  entityId,
  entityName,
  currentCabinetId,
  currentBinId,
  onClose,
}: Props) {
  const qc = useQueryClient();
  const [toCabinetId, setToCabinetId] = useState<number | "">(currentCabinetId);
  const [toBinId, setToBinId] = useState<number | "">(currentBinId ?? "");
  const [notes, setNotes] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const { data: cabinets = [] } = useQuery<Cabinet[]>({
    queryKey: ["cabinets"],
    queryFn: async () => {
      const { data } = await apiClient.get("/cabinets");
      return data;
    },
  });

  const { data: bins = [] } = useQuery<Bin[]>({
    queryKey: ["bins", toCabinetId],
    queryFn: () => listBins(toCabinetId as number),
    enabled: toCabinetId !== "",
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (toCabinetId === "") return;
    setIsLoading(true);
    setError("");
    try {
      if (entityType === "item") {
        await moveItem(entityId, toCabinetId as number, toBinId !== "" ? (toBinId as number) : undefined, notes || undefined);
      } else {
        await moveBin(entityId, toCabinetId as number, notes || undefined);
      }
      qc.invalidateQueries({ queryKey: ["items"] });
      qc.invalidateQueries({ queryKey: ["all-items"] });
      qc.invalidateQueries({ queryKey: ["bins"] });
      qc.invalidateQueries({ queryKey: ["item", entityId] });
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Move failed");
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
          <MapPin className="h-5 w-5 text-brand-600" />
          <h2 className="text-lg font-semibold text-slate-900">
            Move {entityType === "item" ? "Item" : "Bin"}
          </h2>
        </div>
        <p className="text-sm text-slate-500 mb-4">
          Moving <strong className="text-slate-700">{entityName}</strong>
          {entityType === "bin" && (
            <span className="text-xs block mt-1 text-amber-600">
              All items inside this bin will move with it.
            </span>
          )}
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Destination cabinet *</label>
            <select
              className="input"
              value={toCabinetId}
              onChange={(e) => {
                setToCabinetId(e.target.value === "" ? "" : Number(e.target.value));
                setToBinId("");
              }}
              required
            >
              <option value="">Select cabinet…</option>
              {cabinets.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}{c.location ? ` — ${c.location}` : ""}
                </option>
              ))}
            </select>
          </div>

          {entityType === "item" && bins.length > 0 && (
            <div>
              <label className="label">Destination bin (optional)</label>
              <select
                className="input"
                value={toBinId}
                onChange={(e) => setToBinId(e.target.value === "" ? "" : Number(e.target.value))}
              >
                <option value="">No bin (direct in cabinet)</option>
                {bins.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.label}{b.locationNote ? ` — ${b.locationNote}` : ""}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="label">Notes (optional)</label>
            <input
              className="input"
              placeholder="Reason for move"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary flex-1 justify-center">
              Cancel
            </button>
            <button type="submit" disabled={isLoading || toCabinetId === ""} className="btn-primary flex-1 justify-center">
              {isLoading ? "Moving…" : "Move"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
