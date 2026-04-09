// ─── Roles ────────────────────────────────────────────────────────────────────

export interface Role {
  id: number;
  name: "ADMIN" | "COORDINATOR" | "GROUP_LEAD" | "USER";
  canManageInventory: boolean;
  canManageCabinets: boolean;
  canManageBins: boolean;
  canManageUsers: boolean;
  canProcessAnyTransaction: boolean;
  canViewAllTransactions: boolean;
  canViewAuditLogs: boolean;
  canApproveRequests: boolean;
}

// ─── Users ────────────────────────────────────────────────────────────────────

export interface User {
  id: number;
  fullName: string;
  username: string;
  telegramHandle: string | null;
  telegramChatId: string | null;
  roleId: number;
  role: Role;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

// ─── Cabinets ─────────────────────────────────────────────────────────────────

export interface Cabinet {
  id: number;
  name: string;
  location: string | null;
  description: string | null;
  createdAt: string;
  updatedAt: string;
  binCount?: number;
  itemCount?: number;
}

// ─── Bins ─────────────────────────────────────────────────────────────────────

export interface Bin {
  id: number;
  cabinetId: number;
  label: string;
  groupNumber: number | null;
  locationNote: string | null;
  description: string | null;
  qrCodeToken: string | null;
  createdAt: string;
  updatedAt: string;
}

// ─── Items ────────────────────────────────────────────────────────────────────

export type ItemCondition = "GOOD" | "FAIR" | "POOR" | "DAMAGED";

export interface Item {
  id: number;
  name: string;
  description: string | null;
  quantityTotal: number;
  quantityAvailable: number;
  cabinetId: number;
  binId: number | null;
  sku: string | null;
  condition: ItemCondition;
  isActive: boolean;
  isConsumable: boolean;
  unitPrice: number | null;
  qrCodeToken: string | null;
  createdAt: string;
  updatedAt: string;
}

// ─── Transactions ─────────────────────────────────────────────────────────────

export type TransactionStatus = "CHECKED_OUT" | "RETURNED" | "OVERDUE" | "CANCELLED";

export interface Transaction {
  id: number;
  itemId: number;
  userId: number;
  processedByUserId: number | null;
  quantity: number;
  status: TransactionStatus;
  checkedOutAt: string;
  dueAt: string | null;
  returnedAt: string | null;
  notes: string | null;
  photoRequestedViaTelegram: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface TransactionDetail extends Transaction {
  item: Item;
  user: User;
  processedBy: User | null;
}

// ─── API ──────────────────────────────────────────────────────────────────────

export interface CheckoutRequest {
  itemId: number;
  userId: number;
  quantity: number;
  dueAt?: string;
  notes?: string;
}

export interface ReturnRequest {
  notes?: string;
}

// ─── Stock Adjustments ────────────────────────────────────────────────────────

export interface StockAdjustment {
  id: number;
  itemId: number;
  adjustedByUserId: number;
  delta: number;
  quantityBefore: number;
  quantityAfter: number;
  reason: string;
  notes: string | null;
  adjustedAt: string;
  createdAt: string;
}

// ─── Usage Events ─────────────────────────────────────────────────────────────

export interface UsageEvent {
  id: number;
  itemId: number;
  userId: number;
  processedByUserId: number | null;
  quantityUsed: number;
  notes: string | null;
  usedAt: string;
  createdAt: string;
}

// ─── Bin Transactions ─────────────────────────────────────────────────────────

export type BinTransactionStatus = "CHECKED_OUT" | "RETURNED" | "OVERDUE" | "CANCELLED";

export interface BinTransaction {
  id: number;
  binId: number;
  userId: number;
  processedByUserId: number | null;
  status: BinTransactionStatus;
  checkedOutAt: string;
  dueAt: string | null;
  returnedAt: string | null;
  notes: string | null;
  createdAt: string;
  updatedAt: string;
}

// ─── Inventory Requests ───────────────────────────────────────────────────────

export type RequestStatus = "PENDING" | "APPROVED" | "DENIED" | "FULFILLED" | "CANCELLED";

export interface InventoryRequest {
  id: number;
  requesterId: number;
  approverId: number | null;
  itemId: number | null;
  binId: number | null;
  quantityRequested: number;
  status: RequestStatus;
  reason: string | null;
  denialReason: string | null;
  dueAt: string | null;
  approvedAt: string | null;
  fulfilledAt: string | null;
  createdAt: string;
  updatedAt: string;
}

// ─── Purchases ────────────────────────────────────────────────────────────────

export interface PurchaseRecord {
  id: number;
  itemId: number;
  purchasedByUserId: number;
  receiptId: number | null;
  quantityPurchased: number;
  unitPrice: number | null;
  totalPrice: number | null;
  vendor: string | null;
  notes: string | null;
  purchasedAt: string;
  createdAt: string;
}

export interface ReceiptRecord {
  id: number;
  uploadedByUserId: number | null;
  filePath: string | null;
  fileName: string | null;
  mimeType: string | null;
  totalAmount: number | null;
  vendor: string | null;
  notes: string | null;
  uploadedVia: string;
  uploadedAt: string;
  createdAt: string;
}
