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
  groupName: string | null;
  createdAt: string;
  updatedAt: string;
}

export type GroupName = "SHISHU_MANDAL" | "GROUP_1" | "GROUP_2" | "GROUP_3";

export const GROUP_DISPLAY: Record<GroupName, string> = {
  SHISHU_MANDAL: "Shishu Mandal",
  GROUP_1: "Group 1",
  GROUP_2: "Group 2",
  GROUP_3: "Group 3",
};

export const GROUP_NAMES: GroupName[] = ["SHISHU_MANDAL", "GROUP_1", "GROUP_2", "GROUP_3"];

// ─── Rooms ────────────────────────────────────────────────────────────────────

export interface Room {
  id: number;
  name: string;
  description: string | null;
  cabinetCount?: number;
  createdAt: string;
  updatedAt: string;
}

// ─── Cabinets ─────────────────────────────────────────────────────────────────

export interface Cabinet {
  id: number;
  name: string;
  location: string | null;
  description: string | null;
  roomId: number;
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
  lowStockThreshold: number | null;
  priorCabinetId: number | null;
  priorBinId: number | null;
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
  isReversal: boolean;
  reversesEventId: number | null;
  usedAt: string;
  createdAt: string;
}

// ─── Activity Log ─────────────────────────────────────────────────────────────

export type ActivityType =
  | "ITEM_CREATED" | "ITEM_EDITED" | "ITEM_DEACTIVATED" | "ITEM_REACTIVATED"
  | "CABINET_EDITED" | "USER_EDITED" | "USER_PASSWORD_RESET"
  | "ITEM_CHECKED_OUT" | "ITEM_RETURNED" | "BIN_CHECKED_OUT" | "BIN_RETURNED"
  | "USAGE_RECORDED" | "USAGE_REVERSED"
  | "STOCK_ADJUSTMENT_INCREASE" | "STOCK_ADJUSTMENT_DECREASE"
  | "PURCHASE_LOGGED" | "ITEM_MOVED" | "BIN_MOVED"
  | "ITEM_MOVED_TO_RESTOCK" | "ITEM_RESTORED_FROM_RESTOCK"
  | "REQUEST_FULFILLED";

export interface ActivityActor {
  id: number;
  username: string;
  fullName: string;
}

export interface ActivityItemRef {
  id: number;
  name: string;
}

export interface ActivityBinRef {
  id: number;
  label: string;
}

export interface ActivityCabinetRef {
  id: number;
  name: string;
}

export interface ActivityLog {
  id: number;
  activityType: ActivityType;
  actorId: number | null;
  actor: ActivityActor | null;
  targetItemId: number | null;
  targetItem: ActivityItemRef | null;
  targetBinId: number | null;
  targetBin: ActivityBinRef | null;
  targetCabinetId: number | null;
  targetCabinet: ActivityCabinetRef | null;
  targetUserId: number | null;
  targetUser: ActivityActor | null;
  quantityDelta: number | null;
  costImpact: number | null;
  notes: string | null;
  metadata: Record<string, unknown> | null;
  sourceType: string | null;
  sourceId: number | null;
  occurredAt: string;
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

// ─── Checklists ───────────────────────────────────────────────────────────────

export interface ChecklistAssignmentUser {
  id: number;
  fullName: string;
  username: string;
  groupName: string | null;
}

export interface ChecklistAssignment {
  id: number;
  checklistId: number;
  userId: number;
  assignedById: number;
  assignedAt: string;
  user: ChecklistAssignmentUser;
}

export interface ChecklistItem {
  id: number;
  checklistId: number;
  title: string;
  description: string | null;
  itemOrder: number;
  isAutoGenerated: boolean;
  autoType: "ITEM_RETURN" | "BIN_RETURN" | null;
  linkedTransactionId: number | null;
  linkedBinTransactionId: number | null;
  isCompleted: boolean;
  completedAt: string | null;
  completedByUserId: number | null;
  completionNotes: string | null;
  photoRequestedViaTelegram: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface Checklist {
  id: number;
  groupName: GroupName;
  weekStart: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
  items: ChecklistItem[];
  assignments: ChecklistAssignment[];
}

export interface ChecklistSummary {
  id: number;
  groupName: GroupName;
  weekStart: string;
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
  itemCount: number;
  completedCount: number;
  assigneeCount: number;
}

// ─── Reports ──────────────────────────────────────────────────────────────────

export interface HeldValueItem {
  itemId: number;
  itemName: string;
  cabinetId: number;
  cabinetName: string;
  roomId: number;
  roomName: string;
  binId: number | null;
  quantityTotal: number;
  quantityAvailable: number;
  unitPrice: number | null;
  heldValue: number;
}

export interface HeldValueByCabinet {
  cabinetId: number;
  cabinetName: string;
  roomId: number;
  roomName: string;
  totalValue: number;
  itemCount: number;
}

export interface HeldValueByRoom {
  roomId: number;
  roomName: string;
  totalValue: number;
  cabinetCount: number;
  itemCount: number;
}

export interface HeldValueReport {
  totalHeldValue: number;
  totalItems: number;
  byRoom: HeldValueByRoom[];
  byCabinet: HeldValueByCabinet[];
  items: HeldValueItem[];
}
