export interface ItemCreatePayload {
  name: string;
  description?: string;
  quantityTotal: number;
  cabinetId: number;
  binId?: number;
  sku: string;
  condition?: string;
  isConsumable?: boolean;
  unitPrice?: number;
  requiresRequest?: boolean;
}

export interface ItemUpdatePayload {
  name?: string;
  description?: string | null;
  unitPrice?: number | null;
  lowStockThreshold?: number | null;
  isActive?: boolean;
  condition?: string;
  requiresRequest?: boolean;
}

export function toItemCreateApiPayload(payload: ItemCreatePayload) {
  return {
    name: payload.name,
    description: payload.description,
    quantity_total: payload.quantityTotal,
    cabinet_id: payload.cabinetId,
    bin_id: payload.binId,
    sku: payload.sku,
    condition: payload.condition,
    is_consumable: payload.isConsumable ?? false,
    unit_price: payload.unitPrice,
    requires_request: payload.requiresRequest ?? false,
  };
}

export function toItemUpdateApiPayload(payload: ItemUpdatePayload) {
  return {
    name: payload.name,
    description: payload.description,
    unit_price: payload.unitPrice,
    low_stock_threshold: payload.lowStockThreshold,
    is_active: payload.isActive,
    condition: payload.condition,
    requires_request: payload.requiresRequest,
  };
}
