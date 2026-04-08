import { apiClient } from "./client";
import type { CheckoutRequest, ReturnRequest, Transaction, TransactionDetail } from "@/types";

export async function listTransactions(params: {
  status_filter?: string;
  user_id_filter?: number;
  item_id_filter?: number;
  skip?: number;
  limit?: number;
}): Promise<Transaction[]> {
  const { data } = await apiClient.get<Transaction[]>("/transactions", { params });
  return data;
}

export async function getTransaction(id: number): Promise<TransactionDetail> {
  const { data } = await apiClient.get<TransactionDetail>(`/transactions/${id}`);
  return data;
}

export async function checkout(payload: CheckoutRequest): Promise<Transaction> {
  const { data } = await apiClient.post<Transaction>("/transactions/checkout", {
    item_id: payload.itemId,
    user_id: payload.userId,
    quantity: payload.quantity,
    due_at: payload.dueAt,
    notes: payload.notes,
  });
  return data;
}

export async function returnItem(
  transactionId: number,
  payload: ReturnRequest
): Promise<Transaction> {
  const { data } = await apiClient.post<Transaction>(
    `/transactions/${transactionId}/return`,
    payload
  );
  return data;
}

export async function cancelTransaction(transactionId: number): Promise<Transaction> {
  const { data } = await apiClient.post<Transaction>(`/transactions/${transactionId}/cancel`, {});
  return data;
}
