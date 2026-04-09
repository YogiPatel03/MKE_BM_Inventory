import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, X, Clock } from "lucide-react";
import { listRequests, approveRequest, denyRequest, cancelRequest } from "@/api/requests";
import { useAuthStore } from "@/store/auth";
import type { InventoryRequest } from "@/types";

const STATUS_COLORS: Record<string, string> = {
  PENDING: "badge-yellow",
  APPROVED: "badge-green",
  DENIED: "badge-red",
  FULFILLED: "badge-blue",
  CANCELLED: "badge-slate",
};

export function RequestsPage() {
  const user = useAuthStore((s) => s.user);
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("PENDING");
  const canApprove = user?.role.canApproveRequests || user?.role.canManageUsers;

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ["requests", statusFilter],
    queryFn: () => listRequests(statusFilter || undefined),
  });

  const approveMut = useMutation({
    mutationFn: (id: number) => approveRequest(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["requests"] }),
  });

  const denyMut = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) => denyRequest(id, reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["requests"] }),
  });

  const cancelMut = useMutation({
    mutationFn: (id: number) => cancelRequest(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["requests"] }),
  });

  const handleDeny = (req: InventoryRequest) => {
    const reason = window.prompt("Reason for denial (optional):");
    if (reason === null) return; // cancelled
    denyMut.mutate({ id: req.id, reason: reason || undefined });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Requests</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {canApprove ? "All inventory requests" : "Your requests"}
          </p>
        </div>
      </div>

      {/* Status filter */}
      <div className="flex gap-2 flex-wrap">
        {["PENDING", "APPROVED", "DENIED", "FULFILLED", "CANCELLED", ""].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1 text-sm rounded-full border transition-colors ${
              statusFilter === s
                ? "bg-brand-600 text-white border-brand-600"
                : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
            }`}
          >
            {s || "All"}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
        </div>
      ) : requests.length === 0 ? (
        <div className="card p-8 text-center text-slate-500">No requests found.</div>
      ) : (
        <div className="space-y-3">
          {requests.map((req) => (
            <div key={req.id} className="card p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-slate-900">
                      Request #{req.id}
                    </span>
                    <span className={STATUS_COLORS[req.status] ?? "badge-slate"}>
                      {req.status}
                    </span>
                  </div>
                  <div className="text-sm text-slate-600 mt-1">
                    {req.itemId ? `Item #${req.itemId}` : `Bin #${req.binId}`}
                    {req.quantityRequested > 1 && ` × ${req.quantityRequested}`}
                  </div>
                  {req.reason && (
                    <p className="text-sm text-slate-500 mt-1">"{req.reason}"</p>
                  )}
                  {req.denialReason && (
                    <p className="text-sm text-red-600 mt-1">Denied: {req.denialReason}</p>
                  )}
                  <div className="flex items-center gap-1 text-xs text-slate-400 mt-2">
                    <Clock className="h-3 w-3" />
                    {new Date(req.createdAt).toLocaleDateString()}
                  </div>
                </div>

                {req.status === "PENDING" && (
                  <div className="flex gap-2 flex-shrink-0">
                    {canApprove && (
                      <>
                        <button
                          onClick={() => approveMut.mutate(req.id)}
                          disabled={approveMut.isPending}
                          className="btn-primary text-xs py-1.5 px-3"
                        >
                          <Check className="h-3.5 w-3.5" />
                          Approve
                        </button>
                        <button
                          onClick={() => handleDeny(req)}
                          disabled={denyMut.isPending}
                          className="btn-secondary text-xs py-1.5 px-3 text-red-600 border-red-200 hover:bg-red-50"
                        >
                          <X className="h-3.5 w-3.5" />
                          Deny
                        </button>
                      </>
                    )}
                    {req.requesterId === user?.id && !canApprove && (
                      <button
                        onClick={() => cancelMut.mutate(req.id)}
                        disabled={cancelMut.isPending}
                        className="btn-secondary text-xs py-1.5 px-3"
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
