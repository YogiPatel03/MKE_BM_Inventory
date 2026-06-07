export function isMarkAsUsedQtyValid(qty: number, available: number): boolean {
  return qty > 0 && qty <= available;
}

// Mirrors the onChange handler: parseFloat("") and parseFloat("abc") both
// produce NaN, which the || 0 coerces to 0, blocked as invalid by isMarkAsUsedQtyValid.
export function parseMarkAsUsedQtyInput(rawValue: string): number {
  return parseFloat(rawValue) || 0;
}

export function toUsageEventPayload(data: {
  itemId: number;
  quantityUsed: number;
  notes?: string;
}): { item_id: number; quantity_used: number; notes?: string } {
  const payload: { item_id: number; quantity_used: number; notes?: string } = {
    item_id: data.itemId,
    quantity_used: data.quantityUsed,
  };
  if (data.notes !== undefined) {
    payload.notes = data.notes;
  }
  return payload;
}
