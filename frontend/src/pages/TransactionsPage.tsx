import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ClipboardList, Filter } from "lucide-react";
import { listActivity } from "@/api/activity";
import { useAuthStore } from "@/store/auth";
import { ActivityRow } from "@/components/activity/ActivityRow";
import type { ActivityType } from "@/types";

const TYPE_OPTIONS: { value: ActivityType | ""; label: string }[] = [
  { value: "", label: "All activity" },
  { value: "ITEM_CHECKED_OUT", label: "Checkouts" },
  { value: "ITEM_RETURNED", label: "Returns" },
  { value: "BIN_CHECKED_OUT", label: "Bin checkouts" },
  { value: "BIN_RETURNED", label: "Bin returns" },
  { value: "USAGE_RECORDED", label: "Usage recorded" },
  { value: "USAGE_REVERSED", label: "Usage reversed" },
  { value: "STOCK_ADJUSTMENT_INCREASE", label: "Stock added" },
  { value: "STOCK_ADJUSTMENT_DECREASE", label: "Stock reduced" },
  { value: "PURCHASE_LOGGED", label: "Purchases" },
  { value: "ITEM_MOVED", label: "Items moved" },
  { value: "BIN_MOVED", label: "Bins moved" },
  { value: "ITEM_MOVED_TO_RESTOCK", label: "Moved to Restock Me" },
  { value: "ITEM_RESTORED_FROM_RESTOCK", label: "Restored from Restock" },
  { value: "ITEM_CREATED", label: "Items created" },
  { value: "ITEM_EDITED", label: "Items edited" },
  { value: "ITEM_DEACTIVATED", label: "Items deactivated" },
  { value: "CABINET_EDITED", label: "Cabinets edited" },
  { value: "USER_EDITED", label: "Users edited" },
  { value: "USER_PASSWORD_RESET", label: "Password resets" },
  { value: "REQUEST_FULFILLED", label: "Requests fulfilled" },
];

export function TransactionsPage() {
  const user = useAuthStore((s) => s.user);
  const canViewAll = user?.role.canViewAllTransactions ?? false;
  const [typeFilter, setTypeFilter] = useState<ActivityType | "">("");

  const { data: activities = [], isLoading } = useQuery({
    queryKey: ["activity", typeFilter],
    queryFn: () => listActivity({ activityType: typeFilter || undefined, limit: 150 }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Activity</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {canViewAll ? "All inventory activity" : "Your activity"}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-slate-400" />
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value as ActivityType | "")}
            className="input py-1.5 text-sm w-auto"
          >
            {TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="card overflow-hidden divide-y divide-slate-100">
        {isLoading ? (
          <div className="py-10 text-center">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-brand-600 border-t-transparent mx-auto" />
          </div>
        ) : activities.length === 0 ? (
          <div className="py-16 text-center">
            <ClipboardList className="h-10 w-10 text-slate-300 mx-auto mb-3" />
            <p className="text-slate-500">No activity found</p>
          </div>
        ) : (
          activities.map((a) => <ActivityRow key={a.id} activity={a} />)
        )}
      </div>
    </div>
  );
}
