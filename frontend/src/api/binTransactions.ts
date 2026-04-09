import { apiClient } from "./client";
import type { BinTransaction } from "@/types";

export async function checkoutBin(data: {
  binId: number;
  dueAt?: string;
  notes?: string;
}): Promise<BinTransaction> {
  const { data: res } = await apiClient.post("/bin-transactions", {
    bin_id: data.binId,
    due_at: data.dueAt,
    notes: data.notes,
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
