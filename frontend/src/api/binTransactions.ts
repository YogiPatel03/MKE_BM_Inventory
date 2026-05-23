import { apiClient } from "./client";
import type { BinCheckoutResult, BinTransaction, CheckoutPurpose } from "@/types";

export async function checkoutBin(data: {
  binId: number;
  dueAt?: string;
  notes?: string;
  purpose?: CheckoutPurpose;
}): Promise<BinCheckoutResult> {
  const purpose: CheckoutPurpose = data.purpose ?? "GENERAL";
  const { data: res } = await apiClient.post("/bin-transactions", {
    bin_id: data.binId,
    due_at: data.dueAt,
    notes: data.notes,
    purpose,
  });
  return res;
}

export async function returnBin(
  binTransactionId: number,
  notes?: string
): Promise<BinTransaction> {
  const { data } = await apiClient.post(`/bin-transactions/${binTransactionId}/return`, {
    notes,
  });
  return data;
}

export async function listBinTransactions(): Promise<BinTransaction[]> {
  const { data } = await apiClient.get("/bin-transactions");
  return data;
}
