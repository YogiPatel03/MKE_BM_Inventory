import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { useAuthStore } from "@/store/auth";
import { AppShell } from "@/components/layout/AppShell";
import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { RoomsPage } from "@/pages/RoomsPage";
import { RoomDetailPage } from "@/pages/RoomDetailPage";
import { InventoryPage } from "@/pages/InventoryPage";
import { CabinetDetailPage } from "@/pages/CabinetDetailPage";
import { ItemDetailPage } from "@/pages/ItemDetailPage";
import { TransactionsPage } from "@/pages/TransactionsPage";
import { AdminPage } from "@/pages/AdminPage";
import { SettingsPage } from "@/pages/SettingsPage";
// InventoryListPage now merged into InventoryPage
import { RequestsPage } from "@/pages/RequestsPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { QRScanPage } from "@/pages/QRScanPage";
function RequireAuth({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user);
  const isLoading = useAuthStore((s) => s.isLoading);

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-600 border-t-transparent" />
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  const hydrate = useAuthStore((s) => s.hydrate);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <ErrorBoundary>
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            </ErrorBoundary>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />

          {/* Inventory — search-first page (merges old rooms list + inventory list) */}
          <Route path="inventory" element={<InventoryPage />} />
          <Route path="inventory/cabinets/:id" element={<CabinetDetailPage />} />
          <Route path="inventory/items/:id" element={<ItemDetailPage />} />

          {/* Rooms — kept for detail view and direct links */}
          <Route path="rooms" element={<RoomsPage />} />
          <Route path="rooms/:id" element={<RoomDetailPage />} />

          {/* Legacy redirects */}
          <Route path="inventory-list" element={<Navigate to="/inventory" replace />} />
          <Route path="transactions" element={<TransactionsPage />} />
          <Route path="admin" element={<AdminPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="requests" element={<RequestsPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="checklist" element={<Navigate to="/dashboard" replace />} />
          <Route path="qr/:token" element={<QRScanPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
