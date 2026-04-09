import { apiClient } from "./client";

export interface LowStockItem {
  itemId: number;
  itemName: string;
  cabinetId: number;
  binId: number | null;
  quantityAvailable: number;
  quantityTotal: number;
  lowStockThreshold: number | null;
}

export interface OutOfStockItem {
  itemId: number;
  itemName: string;
  cabinetId: number;
  binId: number | null;
}

export interface InventoryStatusReport {
  totalItems: number;
  lowStockItems: LowStockItem[];
  outOfStockItems: OutOfStockItem[];
  checkedOutCount: number;
  overdueCount: number;
}

export interface ItemPurchaseSummary {
  itemId: number;
  itemName: string;
  cabinetId: number;
  totalPurchased: number;
  totalPurchaseCost: number | null;
}

export interface ItemUsageSummary {
  itemId: number;
  itemName: string;
  cabinetId: number;
  totalUsed: number;
  totalCost: number | null;
}

export interface ExpenseReport {
  periodStart: string;
  periodEnd: string;
  totalPurchaseSpend: number;
  totalUsageCost: number;
  byPurchase: ItemPurchaseSummary[];
  byUsage: ItemUsageSummary[];
}

export async function getInventoryStatus(): Promise<InventoryStatusReport> {
  const { data } = await apiClient.get("/reports/inventory-status");
  return data;
}

export async function getExpenseReport(
  start?: string,
  end?: string,
  itemId?: number | null,
): Promise<ExpenseReport> {
  const { data } = await apiClient.get("/reports/expenses", {
    params: { start, end, item_id: itemId ?? undefined },
  });
  return data;
}
