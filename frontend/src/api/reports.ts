import { apiClient } from "./client";

export interface InventoryStatusReport {
  totalItems: number;
  lowStockItems: {
    itemId: number;
    itemName: string;
    cabinetId: number;
    binId: number | null;
    quantityAvailable: number;
    quantityTotal: number;
  }[];
  checkedOutCount: number;
  overdueCount: number;
}

export interface ExpenseReport {
  periodStart: string;
  periodEnd: string;
  totalSpend: number;
  byItem: {
    itemId: number;
    itemName: string;
    cabinetId: number;
    totalUsed: number;
    totalCost: number | null;
  }[];
}

export async function getInventoryStatus(): Promise<InventoryStatusReport> {
  const { data } = await apiClient.get("/reports/inventory-status");
  return data;
}

export async function getExpenseReport(start?: string, end?: string): Promise<ExpenseReport> {
  const { data } = await apiClient.get("/reports/expenses", {
    params: { start, end },
  });
  return data;
}
