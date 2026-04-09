import { Link } from "react-router-dom";
import {
  ArrowRightLeft, Box, CheckCircle, Edit2, Flame, Package, RefreshCw,
  ShoppingCart, Trash2, TrendingDown, TrendingUp, UserCheck, UserX,
  RotateCcw, Archive,
} from "lucide-react";
import { format } from "date-fns";
import type { ActivityLog, ActivityType } from "@/types";

interface ActivityConfig {
  icon: React.ElementType;
  color: string;
  label: string;
  badge?: string;
}

const CONFIG: Record<ActivityType, ActivityConfig> = {
  ITEM_CREATED:            { icon: Package,       color: "text-green-600 bg-green-50",  label: "Item created",           badge: "badge-green" },
  ITEM_EDITED:             { icon: Edit2,         color: "text-blue-600 bg-blue-50",    label: "Item edited",            badge: "badge-blue" },
  ITEM_DEACTIVATED:        { icon: Trash2,        color: "text-slate-500 bg-slate-100", label: "Item deactivated",       badge: "badge-slate" },
  ITEM_REACTIVATED:        { icon: RefreshCw,     color: "text-green-600 bg-green-50",  label: "Item reactivated",       badge: "badge-green" },
  CABINET_EDITED:          { icon: Edit2,         color: "text-blue-600 bg-blue-50",    label: "Cabinet edited",         badge: "badge-blue" },
  USER_EDITED:             { icon: UserCheck,     color: "text-blue-600 bg-blue-50",    label: "User updated",           badge: "badge-blue" },
  USER_PASSWORD_RESET:     { icon: UserX,         color: "text-amber-600 bg-amber-50",  label: "Password reset",         badge: "badge-yellow" },
  ITEM_CHECKED_OUT:        { icon: ArrowRightLeft, color: "text-blue-600 bg-blue-50",   label: "Checked out",            badge: "badge-blue" },
  ITEM_RETURNED:           { icon: CheckCircle,   color: "text-green-600 bg-green-50",  label: "Returned",               badge: "badge-green" },
  BIN_CHECKED_OUT:         { icon: Box,           color: "text-blue-600 bg-blue-50",    label: "Bin checked out",        badge: "badge-blue" },
  BIN_RETURNED:            { icon: Box,           color: "text-green-600 bg-green-50",  label: "Bin returned",           badge: "badge-green" },
  USAGE_RECORDED:          { icon: Flame,         color: "text-amber-600 bg-amber-50",  label: "Used",                   badge: "badge-yellow" },
  USAGE_REVERSED:          { icon: RotateCcw,     color: "text-purple-600 bg-purple-50", label: "Usage reversed",        badge: "badge-blue" },
  STOCK_ADJUSTMENT_INCREASE: { icon: TrendingUp,  color: "text-green-600 bg-green-50",  label: "Stock increased",        badge: "badge-green" },
  STOCK_ADJUSTMENT_DECREASE: { icon: TrendingDown, color: "text-red-600 bg-red-50",     label: "Stock decreased",        badge: "badge-red" },
  PURCHASE_LOGGED:         { icon: ShoppingCart,  color: "text-green-600 bg-green-50",  label: "Purchase logged",        badge: "badge-green" },
  ITEM_MOVED:              { icon: ArrowRightLeft, color: "text-slate-600 bg-slate-100", label: "Item moved",            badge: "badge-slate" },
  BIN_MOVED:               { icon: ArrowRightLeft, color: "text-slate-600 bg-slate-100", label: "Bin moved",             badge: "badge-slate" },
  ITEM_MOVED_TO_RESTOCK:   { icon: Archive,       color: "text-amber-600 bg-amber-50",  label: "Moved to Restock Me",   badge: "badge-yellow" },
  ITEM_RESTORED_FROM_RESTOCK: { icon: RefreshCw,  color: "text-green-600 bg-green-50",  label: "Restored from Restock", badge: "badge-green" },
  REQUEST_FULFILLED:       { icon: CheckCircle,   color: "text-green-600 bg-green-50",  label: "Request fulfilled",      badge: "badge-green" },
};

function buildDescription(activity: ActivityLog): string {
  const itemName = activity.targetItem?.name;
  const binLabel = activity.targetBin?.label;
  const cabinetName = activity.targetCabinet?.name;
  const targetUserName = activity.targetUser?.fullName;

  switch (activity.activityType) {
    case "ITEM_CHECKED_OUT":
      return itemName ? `${itemName}${activity.quantityDelta ? ` × ${Math.abs(activity.quantityDelta)}` : ""}` : "";
    case "ITEM_RETURNED":
      return itemName ? `${itemName}${activity.quantityDelta ? ` × ${Math.abs(activity.quantityDelta)}` : ""}` : "";
    case "BIN_CHECKED_OUT":
      return binLabel ? `Bin: ${binLabel}` : "";
    case "BIN_RETURNED":
      return binLabel ? `Bin: ${binLabel}` : "";
    case "USAGE_RECORDED":
      return itemName ? `${itemName} × ${Math.abs(activity.quantityDelta ?? 0)} used` : "";
    case "USAGE_REVERSED":
      return itemName ? `${itemName} (${Math.abs(activity.quantityDelta ?? 0)} restored)` : "";
    case "STOCK_ADJUSTMENT_INCREASE":
    case "STOCK_ADJUSTMENT_DECREASE":
      return itemName ? `${itemName} ${activity.quantityDelta !== null ? `(${activity.quantityDelta > 0 ? "+" : ""}${activity.quantityDelta})` : ""}` : "";
    case "PURCHASE_LOGGED":
      return itemName ? `${itemName} × ${activity.quantityDelta ?? 0}${activity.costImpact ? ` ($${activity.costImpact.toFixed(2)})` : ""}` : "";
    case "ITEM_MOVED":
      return itemName ? `${itemName}${cabinetName ? ` → ${cabinetName}` : ""}` : "";
    case "BIN_MOVED":
      return binLabel ? `Bin: ${binLabel}${cabinetName ? ` → ${cabinetName}` : ""}` : "";
    case "ITEM_MOVED_TO_RESTOCK":
      return itemName ? `${itemName} → Restock Me` : "";
    case "ITEM_RESTORED_FROM_RESTOCK":
      return itemName ? `${itemName} restored to ${cabinetName ?? "original location"}` : "";
    case "ITEM_CREATED":
      return itemName ? `${itemName} (qty: ${activity.quantityDelta ?? 0})` : "";
    case "ITEM_EDITED":
    case "ITEM_DEACTIVATED":
    case "ITEM_REACTIVATED":
      return itemName ?? "";
    case "CABINET_EDITED":
      return cabinetName ?? "";
    case "USER_EDITED":
    case "USER_PASSWORD_RESET":
      return targetUserName ?? "";
    default:
      return activity.notes ?? "";
  }
}

interface Props {
  activity: ActivityLog;
}

export function ActivityRow({ activity }: Props) {
  const cfg = CONFIG[activity.activityType] ?? {
    icon: Package, color: "text-slate-500 bg-slate-100", label: activity.activityType
  };
  const Icon = cfg.icon;
  const description = buildDescription(activity);

  return (
    <div className="px-4 py-3 flex items-start gap-3 hover:bg-slate-50 transition-colors">
      <div className={`rounded-lg p-2 flex-shrink-0 ${cfg.color}`}>
        <Icon className="h-3.5 w-3.5" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-slate-900">{cfg.label}</span>
          {description && (
            <span className="text-sm text-slate-600 truncate">{description}</span>
          )}
        </div>
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          {activity.actor && (
            <span className="text-xs text-slate-400">{activity.actor.fullName}</span>
          )}
          {!activity.actor && (
            <span className="text-xs text-slate-400 italic">System</span>
          )}
          {activity.notes && !description.includes(activity.notes) && (
            <span className="text-xs text-slate-400 truncate max-w-xs">— {activity.notes}</span>
          )}
        </div>
      </div>
      <div className="text-right flex-shrink-0">
        <p className="text-xs text-slate-400">
          {format(new Date(activity.occurredAt), "MMM d, h:mm a")}
        </p>
        {activity.targetItemId && (
          <Link
            to={`/inventory/items/${activity.targetItemId}`}
            className="text-xs text-brand-600 hover:underline"
          >
            View item
          </Link>
        )}
      </div>
    </div>
  );
}
