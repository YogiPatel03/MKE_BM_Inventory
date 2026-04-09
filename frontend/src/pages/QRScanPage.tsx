import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { resolveQRToken } from "@/api/qr";
import { useAuthStore } from "@/store/auth";
import { checkoutBin, returnBin, listBinTransactions } from "@/api/binTransactions";
import { submitRequest } from "@/api/requests";

type QRResult = { type: "item"; id: number } | { type: "bin"; id: number } | null;

/**
 * QR scan landing page: /qr/:token
 *
 * Items → always redirect to item detail page.
 * Bins  → role-aware:
 *   - canProcessAnyTransaction: show checkout / return inline
 *   - USER: create a checkout request and redirect to /requests
 */
export function QRScanPage() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const canProcess = user?.role.canProcessAnyTransaction || user?.role.canManageUsers;

  const [resolved, setResolved] = useState<QRResult>(null);
  const [error, setError] = useState("");
  const [binStatus, setBinStatus] = useState<"idle" | "checked_out" | "available">("idle");
  const [activeBinTxnId, setActiveBinTxnId] = useState<number | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionDone, setActionDone] = useState(false);

  useEffect(() => {
    if (!token) {
      navigate("/dashboard", { replace: true });
      return;
    }

    resolveQRToken(token)
      .then(async ({ type, id }) => {
        if (type === "item") {
          navigate(`/inventory/items/${id}`, { replace: true });
          return;
        }
        // Bin: check current status
        setResolved({ type: "bin", id });
        try {
          const txns = await listBinTransactions();
          const active = txns.find((t) => t.binId === id && t.status === "CHECKED_OUT");
          if (active) {
            setBinStatus("checked_out");
            setActiveBinTxnId(active.id);
          } else {
            setBinStatus("available");
          }
        } catch {
          setBinStatus("available");
        }
      })
      .catch(() => {
        setError("QR code not recognised.");
      });
  }, [token, navigate]);

  const handleBinAction = async (action: "checkout" | "return" | "request") => {
    if (!resolved || resolved.type !== "bin") return;
    setActionLoading(true);
    try {
      if (action === "checkout") {
        await checkoutBin({ binId: resolved.id });
        setActionDone(true);
        setTimeout(() => navigate("/transactions", { replace: true }), 1500);
      } else if (action === "return" && activeBinTxnId) {
        await returnBin(activeBinTxnId);
        setActionDone(true);
        setTimeout(() => navigate("/transactions", { replace: true }), 1500);
      } else if (action === "request") {
        await submitRequest({ binId: resolved.id, reason: "Scanned via QR code" });
        setActionDone(true);
        setTimeout(() => navigate("/requests", { replace: true }), 1500);
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Action failed. Try again.");
    } finally {
      setActionLoading(false);
    }
  };

  if (error) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center space-y-3">
          <p className="text-red-600 font-medium">{error}</p>
          <button onClick={() => navigate("/dashboard")} className="btn-secondary text-sm">
            Go to dashboard
          </button>
        </div>
      </div>
    );
  }

  if (!resolved) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center space-y-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-600 border-t-transparent mx-auto" />
          <p className="text-sm text-slate-500">Resolving QR code…</p>
        </div>
      </div>
    );
  }

  if (actionDone) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center space-y-2">
          <div className="h-12 w-12 rounded-full bg-green-100 flex items-center justify-center mx-auto">
            <span className="text-green-600 text-2xl">✓</span>
          </div>
          <p className="font-medium text-slate-800">Done! Redirecting…</p>
        </div>
      </div>
    );
  }

  // Bin action UI
  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="card w-full max-w-sm p-6 space-y-5 text-center">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-400 mb-1">Bin scanned</p>
          <p className="text-lg font-bold text-slate-900">Bin #{resolved.id}</p>
          <span className={`mt-2 inline-block ${binStatus === "checked_out" ? "badge-yellow" : "badge-green"}`}>
            {binStatus === "checked_out" ? "Currently checked out" : "Available"}
          </span>
        </div>

        {binStatus === "idle" ? (
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-brand-600 border-t-transparent mx-auto" />
        ) : canProcess ? (
          <div className="space-y-3">
            {binStatus === "available" && (
              <button
                onClick={() => handleBinAction("checkout")}
                disabled={actionLoading}
                className="btn-primary w-full justify-center"
              >
                {actionLoading ? "Processing…" : "Check out bin"}
              </button>
            )}
            {binStatus === "checked_out" && (
              <button
                onClick={() => handleBinAction("return")}
                disabled={actionLoading}
                className="btn-primary w-full justify-center bg-green-600 hover:bg-green-700"
              >
                {actionLoading ? "Processing…" : "Return bin"}
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-slate-500">
              You need approval to check out this bin. Submit a request?
            </p>
            <button
              onClick={() => handleBinAction("request")}
              disabled={actionLoading}
              className="btn-primary w-full justify-center"
            >
              {actionLoading ? "Submitting…" : "Request bin checkout"}
            </button>
          </div>
        )}

        <button
          onClick={() => navigate("/dashboard")}
          className="btn-secondary w-full justify-center text-sm"
        >
          Cancel
        </button>

        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>
    </div>
  );
}
