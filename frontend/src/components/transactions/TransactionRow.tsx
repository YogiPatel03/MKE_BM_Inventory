import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { format, formatDistanceToNow } from "date-fns";
import { returnItem } from "@/api/transactions";
import { useAuthStore } from "@/store/auth";
import type { Transaction } from "@/types";

const STATUS_CONFIG: Record<
  string,
  { label: string; className: string }
> = {
  CHECKED_OUT: { label: "Checked out", className: "badge-blue" },
  RETURNED: { label: "Returned", className: "badge-green" },
  OVERDUE: { label: "Overdue", className: "badge-red" },
  CANCELLED: { label: "Cancelled", className: "badge-slate" },
};

interface Props {
  transaction: Transaction;
}

export function TransactionRow({ transaction: t }: Props) {
  const user = useAuthStore((s) => s.user);
  const qc = useQueryClient();
  const [returning, setReturning] = useState(false);

  const config = STATUS_CONFIG[t.status] ?? { label: t.status, className: "badge-slate" };
  const canReturn =
    t.status === "CHECKED_OUT" || t.status === "OVERDUE";
  const isOwnTransaction = user?.id === t.userId;
  const canAct = isOwnTransaction || (user?.role.canProcessAnyTransaction ?? false);

  const handleReturn = async () => {
    setReturning(true);
    try {
      await returnItem(t.id, {});
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["items"] });
    } catch (e) {
      console.error(e);
    } finally {
      setReturning(false);
    }
  };

  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3 flex-wrap">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-slate-900">
            #{t.id}
          </span>
          <span className={config.className}>{config.label}</span>
          {t.photoRequestedViaTelegram && t.status === "RETURNED" && (
            <span className="badge badge-yellow text-xs">📷 Photo requested via Telegram</span>
          )}
        </div>
        <p className="text-xs text-slate-500 mt-0.5">
          Item #{t.itemId} · qty {t.quantity}
          {t.dueAt && (
            <> · due {format(new Date(t.dueAt), "MMM d, yyyy")}</>
          )}
          {t.checkedOutAt && (
            <> · {formatDistanceToNow(new Date(t.checkedOutAt), { addSuffix: true })}</>
          )}
        </p>
        {t.notes && <p className="text-xs text-slate-400 mt-0.5 italic">{t.notes}</p>}
      </div>

      {canReturn && canAct && (
        <button
          onClick={handleReturn}
          disabled={returning}
          className="btn-secondary text-xs py-1 px-3 flex-shrink-0"
        >
          {returning ? "Returning…" : "Return"}
        </button>
      )}
    </div>
  );
}
