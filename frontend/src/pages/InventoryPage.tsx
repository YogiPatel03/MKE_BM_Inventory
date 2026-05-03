import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Box,
  ChevronDown,
  ChevronRight,
  DoorOpen,
  Package,
  PackageSearch,
  Search,
} from "lucide-react";
import { listItems } from "@/api/items";
import { listCabinets } from "@/api/cabinets";
import { listRooms } from "@/api/rooms";
import type { Bin, Cabinet, Item, Room } from "@/types";
import { clsx } from "clsx";
import { apiClient } from "@/api/client";

async function fetchAllBins(): Promise<Bin[]> {
  const { data } = await apiClient.get("/bins");
  return data;
}

// ── Filter chip types ─────────────────────────────────────────────────────────

type FilterChip =
  | "all"
  | "items"
  | "bins"
  | "cabinets"
  | "rooms"
  | "available"
  | "checked_out"
  | "low_stock"
  | "out_of_stock";

const CHIPS: { id: FilterChip; label: string }[] = [
  { id: "all", label: "All" },
  { id: "items", label: "Items" },
  { id: "bins", label: "Bins" },
  { id: "cabinets", label: "Cabinets" },
  { id: "rooms", label: "Rooms" },
  { id: "available", label: "Available" },
  { id: "checked_out", label: "Checked Out" },
  { id: "low_stock", label: "Low Stock" },
  { id: "out_of_stock", label: "Out of Stock" },
];

// ── Search result type ────────────────────────────────────────────────────────

interface SearchResult {
  type: "item" | "bin" | "cabinet" | "room";
  id: number;
  label: string;
  sublabel: string;
  to: string;
  badge?: string;
  badgeColor?: string;
}

function formatQty(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/\.?0+$/, "");
}

function getLowStockThreshold(item: Item): number {
  return item.lowStockThreshold ?? Math.max(1, Math.floor(item.quantityTotal / 10));
}

// ── Room browser section ──────────────────────────────────────────────────────

function RoomBrowserCard({
  room,
  cabinets,
}: {
  room: Room;
  cabinets: Cabinet[];
}) {
  const [expanded, setExpanded] = useState(false);
  const roomCabinets = cabinets.filter((c) => c.roomId === room.id);

  return (
    <div className="card overflow-hidden">
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-50 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="rounded-md bg-brand-50 p-2 flex-shrink-0">
          <DoorOpen className="h-4 w-4 text-brand-600" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-slate-900 truncate">{room.name}</p>
          <p className="text-xs text-slate-500">
            {roomCabinets.length} cabinet{roomCabinets.length !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <Link
            to={`/rooms/${room.id}`}
            onClick={(e) => e.stopPropagation()}
            className="text-xs text-brand-600 hover:underline"
          >
            View
          </Link>
          {expanded ? (
            <ChevronDown className="h-4 w-4 text-slate-400" />
          ) : (
            <ChevronRight className="h-4 w-4 text-slate-400" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-slate-100 divide-y divide-slate-50">
          {roomCabinets.length === 0 ? (
            <p className="px-4 py-3 text-sm text-slate-400 italic">No cabinets</p>
          ) : (
            roomCabinets.map((cab) => (
              <Link
                key={cab.id}
                to={`/inventory/cabinets/${cab.id}`}
                className="flex items-center gap-3 px-4 py-2.5 hover:bg-slate-50 transition-colors"
              >
                <div className="rounded-md bg-slate-100 p-1.5 flex-shrink-0">
                  <Box className="h-3.5 w-3.5 text-slate-500" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-800 truncate">{cab.name}</p>
                  {cab.location && (
                    <p className="text-xs text-slate-400 truncate">{cab.location}</p>
                  )}
                </div>
                <div className="text-xs text-slate-400 flex-shrink-0">
                  {cab.binCount ?? 0} bins · {cab.itemCount ?? 0} items
                </div>
              </Link>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ── Search result card ────────────────────────────────────────────────────────

function ResultCard({ result }: { result: SearchResult }) {
  const typeIcon = {
    item: <Package className="h-4 w-4 text-brand-500" />,
    bin: <Box className="h-4 w-4 text-purple-500" />,
    cabinet: <Box className="h-4 w-4 text-slate-500" />,
    room: <DoorOpen className="h-4 w-4 text-green-500" />,
  }[result.type];

  const typeLabel = {
    item: "Item",
    bin: "Bin",
    cabinet: "Cabinet",
    room: "Room",
  }[result.type];

  return (
    <Link
      to={result.to}
      className="flex items-center gap-3 px-4 py-3 hover:bg-slate-50 transition-colors"
    >
      <div className="rounded-lg bg-slate-100 p-2 flex-shrink-0">{typeIcon}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-slate-900">{result.label}</span>
          {result.badge && (
            <span
              className={clsx(
                "text-xs px-1.5 py-0.5 rounded-full font-medium",
                result.badgeColor ?? "bg-slate-100 text-slate-600"
              )}
            >
              {result.badge}
            </span>
          )}
        </div>
        <p className="text-xs text-slate-500 truncate mt-0.5">{result.sublabel}</p>
      </div>
      <span className="text-xs text-slate-400 flex-shrink-0 bg-slate-100 px-1.5 py-0.5 rounded">
        {typeLabel}
      </span>
    </Link>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function InventoryPage() {
  const [search, setSearch] = useState("");
  const [activeChip, setActiveChip] = useState<FilterChip>("all");
  const [roomBrowserOpen, setRoomBrowserOpen] = useState(false);

  const { data: items = [], isLoading: itemsLoading } = useQuery({
    queryKey: ["all-items"],
    queryFn: () => listItems({ isActive: true }),
  });
  const { data: bins = [], isLoading: binsLoading } = useQuery({
    queryKey: ["all-bins"],
    queryFn: fetchAllBins,
  });
  const { data: cabinets = [], isLoading: cabinetsLoading } = useQuery({
    queryKey: ["cabinets"],
    queryFn: () => listCabinets(),
  });
  const { data: rooms = [], isLoading: roomsLoading } = useQuery({
    queryKey: ["rooms"],
    queryFn: listRooms,
  });

  const cabinetMap = useMemo(
    () => Object.fromEntries(cabinets.map((c) => [c.id, c])),
    [cabinets]
  );
  const roomMap = useMemo(
    () => Object.fromEntries(rooms.map((r) => [r.id, r])),
    [rooms]
  );
  const binMap = useMemo(
    () => Object.fromEntries(bins.map((b) => [b.id, b])),
    [bins]
  );

  const isLoading = itemsLoading || binsLoading || cabinetsLoading || roomsLoading;

  // Build search results
  const results = useMemo((): SearchResult[] => {
    const q = search.toLowerCase().trim();
    const out: SearchResult[] = [];

    const showItems =
      activeChip === "all" || activeChip === "items" ||
      activeChip === "available" || activeChip === "checked_out" ||
      activeChip === "low_stock" || activeChip === "out_of_stock";
    const showBins = activeChip === "all" || activeChip === "bins";
    const showCabinets = activeChip === "all" || activeChip === "cabinets";
    const showRooms = activeChip === "all" || activeChip === "rooms";

    if (showItems) {
      for (const item of items) {
        const threshold = getLowStockThreshold(item);
        const isLowStock = item.quantityAvailable > 0 && item.quantityAvailable <= threshold;
        const isOutOfStock = item.quantityAvailable === 0;
        const isCheckedOut = item.quantityAvailable < item.quantityTotal;

        // Status filter
        if (activeChip === "available" && item.quantityAvailable === 0) continue;
        if (activeChip === "checked_out" && !isCheckedOut) continue;
        if (activeChip === "low_stock" && !isLowStock) continue;
        if (activeChip === "out_of_stock" && !isOutOfStock) continue;

        // Search filter
        if (
          q &&
          !item.name.toLowerCase().includes(q) &&
          !(item.sku?.toLowerCase().includes(q))
        ) continue;

        const cabinet = cabinetMap[item.cabinetId];
        const bin = item.binId ? binMap[item.binId] : null;
        let sublabel = cabinet?.name ?? `Cabinet #${item.cabinetId}`;
        if (bin) sublabel += ` › Bin: ${bin.label}`;
        sublabel += ` · ${formatQty(item.quantityAvailable)}/${formatQty(item.quantityTotal)} available`;

        let badge: string | undefined;
        let badgeColor: string | undefined;
        if (isOutOfStock) {
          badge = "Out of stock";
          badgeColor = "bg-red-100 text-red-700";
        } else if (isLowStock) {
          badge = "Low stock";
          badgeColor = "bg-amber-100 text-amber-700";
        } else if (item.isConsumable) {
          badge = "Consumable";
          badgeColor = "bg-blue-100 text-blue-700";
        }

        out.push({
          type: "item",
          id: item.id,
          label: item.name,
          sublabel,
          to: `/inventory/items/${item.id}`,
          badge,
          badgeColor,
        });
      }
    }

    if (showBins) {
      for (const bin of bins) {
        if (q && !bin.label.toLowerCase().includes(q)) continue;
        const cabinet = cabinetMap[bin.cabinetId];
        const room = cabinet ? roomMap[cabinet.roomId] : null;
        const sublabel = [room?.name, cabinet?.name].filter(Boolean).join(" › ");
        out.push({
          type: "bin",
          id: bin.id,
          label: `Bin: ${bin.label}`,
          sublabel: sublabel || `Cabinet #${bin.cabinetId}`,
          to: `/inventory/cabinets/${bin.cabinetId}`,
        });
      }
    }

    if (showCabinets) {
      for (const cabinet of cabinets) {
        if (q && !cabinet.name.toLowerCase().includes(q)) continue;
        const room = roomMap[cabinet.roomId];
        out.push({
          type: "cabinet",
          id: cabinet.id,
          label: cabinet.name,
          sublabel: room?.name ?? `Room #${cabinet.roomId}`,
          to: `/inventory/cabinets/${cabinet.id}`,
        });
      }
    }

    if (showRooms) {
      for (const room of rooms) {
        if (q && !room.name.toLowerCase().includes(q)) continue;
        out.push({
          type: "room",
          id: room.id,
          label: room.name,
          sublabel: `${room.cabinetCount ?? 0} cabinets`,
          to: `/rooms/${room.id}`,
        });
      }
    }

    return out;
  }, [search, activeChip, items, bins, cabinets, rooms, cabinetMap, binMap, roomMap]);

  const isSearching = search.trim().length > 0 || activeChip !== "all";
  const totalCounts = {
    items: items.length,
    bins: bins.length,
    cabinets: cabinets.length,
    rooms: rooms.length,
  };

  return (
    <div className="space-y-5">
      {/* Page title */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Inventory</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          {totalCounts.items} items · {totalCounts.bins} bins · {totalCounts.cabinets} cabinets · {totalCounts.rooms} rooms
        </p>
      </div>

      {/* Search bar */}
      <div className="relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400 pointer-events-none" />
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search items, bins, cabinets, rooms…"
          className="input pl-12 py-3 text-base w-full"
          autoFocus={false}
        />
      </div>

      {/* Filter chips */}
      <div className="flex gap-2 flex-wrap">
        {CHIPS.map((chip) => (
          <button
            key={chip.id}
            onClick={() => setActiveChip(chip.id)}
            className={clsx(
              "px-3 py-1 text-sm rounded-full border transition-colors whitespace-nowrap",
              activeChip === chip.id
                ? "bg-brand-600 text-white border-brand-600"
                : "bg-white text-slate-600 border-slate-200 hover:border-slate-300 hover:bg-slate-50"
            )}
          >
            {chip.label}
          </button>
        ))}
      </div>

      {/* Results */}
      {isLoading ? (
        <div className="card divide-y divide-slate-100">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="px-4 py-3 flex items-center gap-3 animate-pulse">
              <div className="h-9 w-9 bg-slate-100 rounded-lg flex-shrink-0" />
              <div className="flex-1">
                <div className="h-4 bg-slate-100 rounded w-1/3 mb-1" />
                <div className="h-3 bg-slate-100 rounded w-1/2" />
              </div>
            </div>
          ))}
        </div>
      ) : isSearching && results.length === 0 ? (
        <div className="card p-10 text-center">
          <PackageSearch className="h-10 w-10 text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500 font-medium">No results found</p>
          <p className="text-sm text-slate-400 mt-1">
            Try a different search or filter
          </p>
        </div>
      ) : isSearching ? (
        <div className="card divide-y divide-slate-100 overflow-hidden">
          <div className="px-4 py-2 bg-slate-50 border-b border-slate-100">
            <p className="text-xs text-slate-500 font-medium">{results.length} result{results.length !== 1 ? "s" : ""}</p>
          </div>
          {results.map((r) => (
            <ResultCard key={`${r.type}-${r.id}`} result={r} />
          ))}
        </div>
      ) : (
        /* Default state: show item stats overview when no search/filter */
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <button
            onClick={() => setActiveChip("available")}
            className="card p-4 text-left hover:shadow-md transition-shadow"
          >
            <p className="text-2xl font-bold text-green-600">
              {items.filter((i) => i.quantityAvailable > 0).length}
            </p>
            <p className="text-sm text-slate-600 mt-0.5">Items available</p>
          </button>
          <button
            onClick={() => setActiveChip("checked_out")}
            className="card p-4 text-left hover:shadow-md transition-shadow"
          >
            <p className="text-2xl font-bold text-brand-600">
              {items.filter((i) => i.quantityAvailable < i.quantityTotal).length}
            </p>
            <p className="text-sm text-slate-600 mt-0.5">Items checked out</p>
          </button>
          <button
            onClick={() => setActiveChip("low_stock")}
            className="card p-4 text-left hover:shadow-md transition-shadow"
          >
            <p className="text-2xl font-bold text-amber-600">
              {items.filter((i) => {
                const t = getLowStockThreshold(i);
                return i.quantityAvailable > 0 && i.quantityAvailable <= t;
              }).length}
            </p>
            <p className="text-sm text-slate-600 mt-0.5">Low stock</p>
            {items.filter((i) => {
              const t = getLowStockThreshold(i);
              return i.quantityAvailable > 0 && i.quantityAvailable <= t;
            }).length > 0 && (
              <AlertTriangle className="h-4 w-4 text-amber-500 mt-1" />
            )}
          </button>
          <button
            onClick={() => setActiveChip("out_of_stock")}
            className="card p-4 text-left hover:shadow-md transition-shadow"
          >
            <p className="text-2xl font-bold text-red-600">
              {items.filter((i) => i.quantityAvailable === 0).length}
            </p>
            <p className="text-sm text-slate-600 mt-0.5">Out of stock</p>
          </button>
        </div>
      )}

      {/* Room browser (secondary, collapsible) */}
      <div>
        <button
          className="flex items-center gap-2 text-sm font-semibold text-slate-700 hover:text-slate-900 transition-colors mb-3"
          onClick={() => setRoomBrowserOpen((v) => !v)}
        >
          {roomBrowserOpen ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
          Browse by Room
          <span className="text-xs font-normal text-slate-400">({rooms.length} rooms)</span>
        </button>

        {roomBrowserOpen && (
          <div className="space-y-3">
            {rooms.length === 0 ? (
              <div className="card p-6 text-center text-slate-400 text-sm">
                No rooms yet
              </div>
            ) : (
              rooms.map((room) => (
                <RoomBrowserCard key={room.id} room={room} cabinets={cabinets} />
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
