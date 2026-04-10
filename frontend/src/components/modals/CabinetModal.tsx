import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { createCabinet, updateCabinet } from "@/api/cabinets";
import { listRooms } from "@/api/rooms";
import type { Cabinet } from "@/types";

interface Props {
  cabinet?: Cabinet;       // if provided → edit mode
  roomId?: number;         // pre-select room when creating
  onClose: () => void;
}

export function CabinetModal({ cabinet: editCabinet, roomId: defaultRoomId, onClose }: Props) {
  const qc = useQueryClient();
  const isEdit = !!editCabinet;

  const [name, setName] = useState(editCabinet?.name ?? "");
  const [location, setLocation] = useState(editCabinet?.location ?? "");
  const [description, setDescription] = useState(editCabinet?.description ?? "");
  const [selectedRoomId, setSelectedRoomId] = useState<number | "">(
    editCabinet?.roomId ?? defaultRoomId ?? ""
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const { data: rooms = [] } = useQuery({
    queryKey: ["rooms"],
    queryFn: listRooms,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedRoomId) {
      setError("Please select a room");
      return;
    }
    setIsLoading(true);
    setError("");
    try {
      if (isEdit) {
        await updateCabinet(editCabinet.id, {
          name,
          roomId: selectedRoomId as number,
          location: location || null,
          description: description || null,
        });
      } else {
        await createCabinet({
          name,
          roomId: selectedRoomId as number,
          location: location || null,
          description: description || null,
        });
      }
      qc.invalidateQueries({ queryKey: ["cabinets"] });
      qc.invalidateQueries({ queryKey: ["rooms"] });
      if (isEdit) {
        qc.invalidateQueries({ queryKey: ["cabinet", editCabinet.id] });
      }
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? `Failed to ${isEdit ? "update" : "create"} cabinet`);
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
        <h2 className="text-lg font-semibold text-slate-900 mb-5">
          {isEdit ? "Edit Cabinet" : "Add Cabinet"}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Room *</label>
            <select
              className="input"
              value={selectedRoomId}
              onChange={(e) => setSelectedRoomId(e.target.value ? Number(e.target.value) : "")}
              required
              disabled={!isEdit && !!defaultRoomId}
            >
              <option value="">Select a room…</option>
              {rooms.map((r) => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Name *</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div>
            <label className="label">Location</label>
            <input className="input" placeholder="e.g. Shelf B, Near window" value={location} onChange={(e) => setLocation(e.target.value)} />
          </div>
          <div>
            <label className="label">Description</label>
            <textarea className="input resize-none" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary flex-1 justify-center">Cancel</button>
            <button type="submit" disabled={isLoading} className="btn-primary flex-1 justify-center">
              {isLoading ? (isEdit ? "Saving…" : "Creating…") : isEdit ? "Save changes" : "Create cabinet"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
