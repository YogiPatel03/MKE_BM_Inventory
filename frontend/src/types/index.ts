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
