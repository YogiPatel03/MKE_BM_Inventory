import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, X, Clock, AlertCircle } from "lucide-react";
import { listRequests, approveRequest, denyRequest, cancelRequest } from "@/api/requests";
import { useAuthStore } from "@/store/auth";
import { PromptModal } from "@/components/modals/PromptModal";
import type { InventoryRequest } from "@/types";

const STATUS_COLORS: Record<string, string> = {
  PENDING: "badge-yellow",
  APPROVED: "badge-green",
  DENIED: "badge-red",
  FULFILLED: "badge-blue",
  CANCELLED: "badge-slate",
};

function safeDate(value: string | null | undefined): string {
  if (!value) return "Unknown date";
  const d = new Date(value);
  return isNaN(d.getTime()) ? "Unknown date" : d.toLocaleDateString();
}

function targetLabel(req: InventoryRequest): string {
  if (req.itemId) return `Item #${req.itemId}`;
  if (req.binId) return `Bin #${req.binId}`;
  return "Unknown target";
}

function quantityDisplay(qty: number): string {
  const n = Number(qty);
  if (isNaN(n)) return "";
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}

export function RequestsPage() {
  const user = useAuthStore((s) => s.user);
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("PENDING");
  const canApprove = user?.role?.canApproveRequests || user?.role?.canManageUsers;
  const [denyingRequest, setDenyingRequest] = useState<InventoryRequest | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);

  const { data: requests = [], isLoading, isError, error } = useQuery({
    queryKey: ["requests", statusFilter],
    queryFn: () => listRequests(statusFilter || undefined),
  });

  function extractErrorMessage(err: unknown, fallback: string): string {
    if (err && typeof err === "object" && "response" in err) {
      const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
      if (typeof detail === "string") return detail;
    }
    return err instanceof Error ? err.message : fallback;
  }

  const approveMut = useMutation({
    mutationFn: (id: number) => approveRequest(id),
    onSuccess: () => setMutationError(null),
    onError: (err: unknown) => {
      setMutationError(extractErrorMessage(err, "Approval failed. Please try again."));
    },
    // Always refetch — keeps the list consistent even when the backend committed
    // but the response errored (e.g. post-commit notification failure → 500).
    onSettled: () => qc.invalidateQueries({ queryKey: ["requests"] }),
  });

  const denyMut = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) => denyRequest(id, reason),
    onSuccess: () => setMutationError(null),
    onError: (err: unknown) => {
      setMutationError(extractErrorMessage(err, "Denial failed. Please try again."));
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["requests"] }),
  });

  const cancelMut = useMutation({
    mutationFn: (id: number) => cancelRequest(id),
    onSuccess: () => setMutationError(null),
    onError: (err: unknown) => {
      setMutationError(extractErrorMessage(err, "Cancel failed. Please try again."));
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["requests"] }),
  });

  const handleDeny = (req: InventoryRequest) => setDenyingRequest(req);

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

      {/* Mutation error banner */}
      {mutationError && (
        <div className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          {mutationError}
          <button
            className="ml-auto text-red-500 hover:text-red-700"
            onClick={() => setMutationError(null)}
          >
            ✕
          </button>
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-16">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
        </div>
      ) : isError ? (
        <div className="card p-8 text-center">
          <AlertCircle className="h-8 w-8 text-red-400 mx-auto mb-2" />
          <p className="text-slate-700 font-medium">Failed to load requests</p>
          <p className="text-sm text-slate-500 mt-1">
            {error instanceof Error ? error.message : "An unexpected error occurred."}
          </p>
        </div>
      ) : requests.length === 0 ? (
        <div className="card p-8 text-center text-slate-500">No requests found.</div>
      ) : (
        <div className="space-y-3">
          {requests.map((req) => {
            const qty = Number(req.quantityRequested);
            const showQty = !isNaN(qty) && qty !== 1;
            return (
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
                      {req.purpose === "SABHA" && (
                        <span className="inline-flex items-center rounded-full bg-purple-100 px-2 py-0.5 text-xs font-medium text-purple-700">
                          Sabha
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-slate-600 mt-1">
                      {targetLabel(req)}
                      {showQty && ` × ${quantityDisplay(qty)}`}
                    </div>
                    {req.reason && (
                      <p className="text-sm text-slate-500 mt-1">"{req.reason}"</p>
                    )}
                    {req.denialReason && (
                      <p className="text-sm text-red-600 mt-1">Denied: {req.denialReason}</p>
                    )}
                    <div className="flex items-center gap-1 text-xs text-slate-400 mt-2">
                      <Clock className="h-3 w-3" />
                      {safeDate(req.createdAt)}
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
            );
          })}
        </div>
      )}

      {denyingRequest && (
        <PromptModal
          title="Deny Request"
          label="Reason for denial"
          placeholder="Enter denial reason..."
          confirmLabel="Deny"
          onConfirm={(reason) => {
            denyMut.mutate({ id: denyingRequest.id, reason: reason || undefined });
            setDenyingRequest(null);
          }}
          onCancel={() => setDenyingRequest(null)}
        />
      )}
    </div>
  );
}
