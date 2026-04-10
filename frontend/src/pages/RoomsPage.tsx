import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ChevronRight, DoorOpen, Edit2, Plus, Trash2, X } from "lucide-react";
import { listRooms, createRoom, updateRoom, deleteRoom } from "@/api/rooms";
import { useAuthStore } from "@/store/auth";
import type { Room } from "@/types";

function RoomFormModal({
  room,
  onClose,
}: {
  room?: Room;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState(room?.name ?? "");
  const [description, setDescription] = useState(room?.description ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      if (room) {
        await updateRoom(room.id, { name: name.trim(), description: description.trim() || null });
      } else {
        await createRoom({ name: name.trim(), description: description.trim() || null });
      }
      qc.invalidateQueries({ queryKey: ["rooms"] });
      onClose();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Failed to save room");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50">
      <div className="card w-full max-w-md p-6 relative">
        <button onClick={onClose} className="absolute top-4 right-4 text-slate-400 hover:text-slate-700">
          <X className="h-5 w-5" />
        </button>
        <h2 className="text-lg font-semibold text-slate-900 mb-5">
          {room ? "Edit Room" : "Add Room"}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">Room Name *</label>
            <input
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Main Hall, Storage Room"
              required
            />
          </div>
          <div>
            <label className="label">Description</label>
            <textarea
              className="input resize-none"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional notes about this room"
            />
          </div>
          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
          )}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary flex-1 justify-center">
              Cancel
            </button>
            <button type="submit" disabled={loading} className="btn-primary flex-1 justify-center">
              {loading ? "Saving…" : room ? "Save changes" : "Create room"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function RoomCard({
  room,
  canManage,
  onEdit,
  onDelete,
}: {
  room: Room;
  canManage: boolean;
  onEdit: (room: Room) => void;
  onDelete: (room: Room) => void;
}) {
  return (
    <div className="card p-5 hover:shadow-md transition-shadow group">
      <div className="flex items-start justify-between gap-3">
        <Link
          to={`/rooms/${room.id}`}
          className="flex items-start gap-3 min-w-0 flex-1"
        >
          <div className="rounded-lg bg-brand-50 p-2.5 flex-shrink-0 group-hover:bg-brand-100 transition-colors">
            <DoorOpen className="h-5 w-5 text-brand-600" />
          </div>
          <div className="min-w-0">
            <h3 className="font-semibold text-slate-900 truncate">{room.name}</h3>
            {room.description && (
              <p className="text-sm text-slate-500 mt-1 line-clamp-2">{room.description}</p>
            )}
          </div>
        </Link>
        <div className="flex items-center gap-1 flex-shrink-0">
          {canManage && (
            <>
              <button
                onClick={() => onEdit(room)}
                className="p-1.5 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                title="Edit room"
              >
                <Edit2 className="h-4 w-4" />
              </button>
              <button
                onClick={() => onDelete(room)}
                className="p-1.5 rounded text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                title="Delete room"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </>
          )}
          <Link to={`/rooms/${room.id}`}>
            <ChevronRight className="h-4 w-4 text-slate-400 group-hover:text-brand-600 transition-colors" />
          </Link>
        </div>
      </div>

      <div className="mt-4 pt-4 border-t border-slate-100">
        <span className="text-xs text-slate-500">
          <span className="font-semibold text-slate-700">{room.cabinetCount ?? 0}</span> cabinet
          {(room.cabinetCount ?? 0) !== 1 ? "s" : ""}
        </span>
      </div>
    </div>
  );
}

export function RoomsPage() {
  const user = useAuthStore((s) => s.user);
  const canManage = user?.role.canManageUsers ?? false; // admin-only
  const qc = useQueryClient();

  const [formOpen, setFormOpen] = useState(false);
  const [editingRoom, setEditingRoom] = useState<Room | undefined>();

  const { data: rooms = [], isLoading } = useQuery({
    queryKey: ["rooms"],
    queryFn: listRooms,
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteRoom(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rooms"] }),
  });

  const handleDelete = (room: Room) => {
    if (!confirm(`Delete room "${room.name}"? This will fail if it still contains cabinets.`)) return;
    deleteMut.mutate(room.id);
  };

  const handleEdit = (room: Room) => {
    setEditingRoom(room);
    setFormOpen(true);
  };

  const handleAdd = () => {
    setEditingRoom(undefined);
    setFormOpen(true);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Rooms</h1>
          <p className="text-sm text-slate-500 mt-0.5">{rooms.length} room{rooms.length !== 1 ? "s" : ""}</p>
        </div>
        {canManage && (
          <button className="btn-primary" onClick={handleAdd}>
            <Plus className="h-4 w-4" />
            Add Room
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="card p-5 animate-pulse">
              <div className="h-5 bg-slate-100 rounded w-2/3 mb-2" />
              <div className="h-4 bg-slate-100 rounded w-1/2" />
            </div>
          ))}
        </div>
      ) : rooms.length === 0 ? (
        <div className="py-20 text-center">
          <DoorOpen className="h-10 w-10 text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500">No rooms yet</p>
          {canManage && (
            <button className="btn-primary mt-4" onClick={handleAdd}>
              <Plus className="h-4 w-4" />
              Add your first room
            </button>
          )}
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {rooms.map((room) => (
            <RoomCard
              key={room.id}
              room={room}
              canManage={canManage}
              onEdit={handleEdit}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      {formOpen && (
        <RoomFormModal
          room={editingRoom}
          onClose={() => {
            setFormOpen(false);
            setEditingRoom(undefined);
          }}
        />
      )}
    </div>
  );
}
