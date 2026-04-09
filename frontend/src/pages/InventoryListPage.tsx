import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search, AlertTriangle } from "lucide-react";
import { listItems } from "@/api/items";
import { apiClient } from "@/api/client";
import type { Bin, Cabinet } from "@/types";

async function fetchCabinets(): Promise<Cabinet[]> {
  const { data } = await apiClient.get("/cabinets");
  return data;
}

async function fetchAllBins(): Promise<Bin[]> {
  const { data } = await apiClient.get("/bins");
  return data;
}

export function InventoryListPage() {
  const [search, setSearch] = useState("");
  const [cabinetFilter, setCabinetFilter] = useState<string>("");
  const [binFilter, setBinFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");

  const { data: items = [], isLoading } = useQuery({
    queryKey: ["all-items"],
    queryFn: () => listItems(),
  });
  const { data: cabinets = [] } = useQuery({
    queryKey: ["cabinets"],
    queryFn: fetchCabinets,
  });
  const { data: allBins = [] } = useQuery({
    queryKey: ["all-bins"],
    queryFn: fetchAllBins,
  });

  const cabinetMap = Object.fromEntries(cabinets.map((c) => [c.id, c]));
  const binMap = Object.fromEntries(allBins.map((b) => [b.id, b]));

  // When cabinet filter changes, reset bin filter
  const handleCabinetFilter = (val: string) => {
    setCabinetFilter(val);
    setBinFilter("");
  };

  // Bins available for the selected cabinet (or all bins if no cabinet selected)
  const filteredBinOptions = cabinetFilter
    ? allBins.filter((b) => String(b.cabinetId) === cabinetFilter)
    : allBins;

  const filtered = items.filter((item) => {
    const matchSearch =
      !search ||
      item.name.toLowerCase().includes(search.toLowerCase()) ||
      (item.sku?.toLowerCase().includes(search.toLowerCase()) ?? false);
    const matchCabinet = !cabinetFilter || String(item.cabinetId) === cabinetFilter;
    const matchBin = !binFilter || String(item.binId) === binFilter;
    const matchStatus =
      !statusFilter ||
      (statusFilter === "available" && item.quantityAvailable > 0) ||
      (statusFilter === "out_of_stock" && item.quantityAvailable === 0) ||
      (statusFilter === "low_stock" && item.quantityAvailable > 0 && item.quantityAvailable <= 2) ||
      (statusFilter === "consumable" && item.isConsumable);
    return matchSearch && matchCabinet && matchBin && matchStatus;
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">All Inventory</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          {filtered.length} of {items.length} items
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search name or SKU…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input pl-9 w-full"
          />
        </div>
        <select
          value={cabinetFilter}
          onChange={(e) => handleCabinetFilter(e.target.value)}
          className="input w-full sm:w-44"
        >
          <option value="">All cabinets</option>
          {cabinets.map((c) => (
            <option key={c.id} value={String(c.id)}>{c.name}</option>
          ))}
        </select>
        <select
          value={binFilter}
          onChange={(e) => setBinFilter(e.target.value)}
          className="input w-full sm:w-40"
        >
          <option value="">All bins</option>
          {filteredBinOptions.map((b) => (
            <option key={b.id} value={String(b.id)}>
              {b.label}{b.locationNote ? ` — ${b.locationNote}` : ""}
            </option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="input w-full sm:w-44"
        >
          <option value="">All statuses</option>
          <option value="available">Available</option>
          <option value="low_stock">Low stock (≤2)</option>
          <option value="out_of_stock">Out of stock</option>
          <option value="consumable">Consumables</option>
        </select>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="card p-8 text-center text-slate-500">No items match your filters.</div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-slate-600">Name</th>
                <th className="px-4 py-3 text-left font-medium text-slate-600 hidden sm:table-cell">Location</th>
                <th className="px-4 py-3 text-left font-medium text-slate-600 hidden md:table-cell">SKU</th>
                <th className="px-4 py-3 text-right font-medium text-slate-600">Stock</th>
                <th className="px-4 py-3 text-left font-medium text-slate-600 hidden sm:table-cell">Type</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((item) => {
                const isLow = item.quantityAvailable > 0 && item.quantityAvailable <= 2;
                const isOut = item.quantityAvailable === 0;
                const cabinet = cabinetMap[item.cabinetId];
                const bin = item.binId ? binMap[item.binId] : null;

                const locationLabel = bin
                  ? `${cabinet?.name ?? `Cabinet ${item.cabinetId}`} / ${bin.label}`
                  : cabinet?.name ?? `Cabinet ${item.cabinetId}`;

                return (
                  <tr key={item.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3">
                      <Link
                        to={`/inventory/items/${item.id}`}
                        className="font-medium text-brand-600 hover:underline"
                      >
                        {item.name}
                      </Link>
                      {/* Show location inline on mobile */}
                      <p className="sm:hidden text-xs text-slate-400 mt-0.5">{locationLabel}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-600 hidden sm:table-cell">
                      {locationLabel}
                    </td>
                    <td className="px-4 py-3 text-slate-400 hidden md:table-cell">
                      {item.sku ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span
                        className={`inline-flex items-center gap-1 font-medium ${
                          isOut
                            ? "text-red-600"
                            : isLow
                            ? "text-amber-600"
                            : "text-slate-900"
                        }`}
                      >
                        {isLow && <AlertTriangle className="h-3.5 w-3.5" />}
                        {item.quantityAvailable}/{item.quantityTotal}
                      </span>
                    </td>
                    <td className="px-4 py-3 hidden sm:table-cell">
                      {item.isConsumable ? (
                        <span className="badge-yellow">Consumable</span>
                      ) : (
                        <span className="badge-slate">Standard</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
