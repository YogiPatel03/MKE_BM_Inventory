import { apiClient } from "./client";
import type { PurchaseRecord, ReceiptRecord } from "@/types";

export async function logPurchase(data: {
  itemId: number;
  quantityPurchased: number;
  unitPrice?: number;
  totalPrice?: number;
  vendor?: string;
  notes?: string;
  receiptId?: number;
}): Promise<PurchaseRecord> {
  const { data: res } = await apiClient.post("/purchases", {
    item_id: data.itemId,
    quantity_purchased: data.quantityPurchased,
    unit_price: data.unitPrice,
    total_price: data.totalPrice,
    vendor: data.vendor,
    notes: data.notes,
    receipt_id: data.receiptId,
  });
  return res;
}

export async function getPurchasesForItem(itemId: number): Promise<PurchaseRecord[]> {
  const { data } = await apiClient.get(`/purchases/item/${itemId}`);
  return data;
}

export async function uploadReceipt(formData: FormData): Promise<ReceiptRecord> {
  const { data } = await apiClient.post("/purchases/receipts", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}
