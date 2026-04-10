import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Box, ChevronRight, MapPin, Pencil, Plus, Search } from "lucide-react";
import { getRoom } from "@/api/rooms";
import { listCabinets } from "@/api/cabinets";
import { useAuthStore } from "@/store/auth";
import type { Cabinet } from "@/types";
import { CabinetModal } from "@/components/modals/CabinetModal";

function CabinetCard({ cabinet, canManage, onEdit }: { cabinet: Cabinet; canManage: boolean; onEdit: () => void }) {
  return (
    <div className="card p-5 hover:shadow-md transition-shadow group relative">
      {canManage && (
        <button
          onClick={(e) => { e.preventDefault(); onEdit(); }}
          className="absolute top-3 right-3 p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-md transition-colors"
          title="Edit cabinet"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
      )}
      <Link to={`/inventory/cabinets/${cabinet.id}`} className="block">
        <div className="flex items-start gap-3 min-w-0 pr-6">
          <div className="rounded-lg bg-brand-50 p-2.5 flex-shrink-0 group-hover:bg-brand-100 transition-colors">
            <Box className="h-5 w-5 text-brand-600" />
          </div>
          <div className="min-w-0">
            <h3 className="font-semibold text-slate-900 truncate">{cabinet.name}</h3>
            {cabinet.location && (
              <p className="text-xs text-slate-500 flex items-center gap-1 mt-0.5">
                <MapPin className="h-3 w-3" />
                {cabinet.location}
              </p>
            )}
            {cabinet.description && (
              <p className="text-sm text-slate-500 mt-1 line-clamp-2">{cabinet.description}</p>
            )}
          </div>
        </div>

        <div className="flex gap-4 mt-4 pt-4 border-t border-slate-100">
          <span className="text-xs text-slate-500">
            <span className="font-semibold text-slate-700">{cabinet.binCount ?? 0}</span> bins
          </span>
          <span className="text-xs text-slate-500">
            <span className="font-semibold text-slate-700">{cabinet.itemCount ?? 0}</span> items
          </span>
        </div>
      </Link>
    </div>
  );
}

export function RoomDetailPage() {
  const { id } = useParams<{ id: string }>();
  const roomId = Number(id);
  const user = useAuthStore((s) => s.user);
  const canManage = user?.role.canManageCabinets ?? false;
  const [search, setSearch] = useState("");
  const [cabinetModalOpen, setCabinetModalOpen] = useState(false);
  const [editingCabinet, setEditingCabinet] = useState<Cabinet | null>(null);

  const { data: room, isLoading: roomLoading } = useQuery({
    queryKey: ["room", roomId],
    queryFn: () => getRoom(roomId),
    enabled: !!roomId,
  });

  const { data: cabinets = [], isLoading: cabinetsLoading } = useQuery({
    queryKey: ["cabinets", roomId],
    queryFn: () => listCabinets(roomId),
    enabled: !!roomId,
  });

  const filtered = cabinets.filter(
    (c) =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      (c.location ?? "").toLowerCase().includes(search.toLowerCase())
  );

  if (roomLoading) {
    return <div className="animate-pulse h-8 bg-slate-100 rounded w-48" />;
  }

  if (!room) {
    return <p className="text-slate-500">Room not found.</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <Link
          to="/rooms"
          className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-3"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Rooms
        </Link>

        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">{room.name}</h1>
            {room.description && (
              <p className="text-sm text-slate-500 mt-0.5">{room.description}</p>
            )}
            <p className="text-sm text-slate-500 mt-0.5">{cabinets.length} cabinet{cabinets.length !== 1 ? "s" : ""}</p>
          </div>
          {canManage && (
            <button className="btn-primary" onClick={() => setCabinetModalOpen(true)}>
              <Plus className="h-4 w-4" />
              Add Cabinet
            </button>
          )}
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
        <input
          type="text"
          placeholder="Search cabinets…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input pl-9"
        />
      </div>

      {cabinetsLoading ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="card p-5 animate-pulse">
              <div className="h-5 bg-slate-100 rounded w-2/3 mb-2" />
              <div className="h-4 bg-slate-100 rounded w-1/2" />
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-20 text-center">
          <Box className="h-10 w-10 text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500">
            {search ? "No cabinets match your search" : "No cabinets in this room yet"}
          </p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((cabinet) => (
            <CabinetCard
              key={cabinet.id}
              cabinet={cabinet}
              canManage={canManage}
              onEdit={() => setEditingCabinet(cabinet)}
            />
          ))}
        </div>
      )}

      {cabinetModalOpen && (
        <CabinetModal
          roomId={roomId}
          onClose={() => setCabinetModalOpen(false)}
        />
      )}
      {editingCabinet && (
        <CabinetModal
          cabinet={editingCabinet}
          onClose={() => setEditingCabinet(null)}
        />
      )}
    </div>
  );
}
