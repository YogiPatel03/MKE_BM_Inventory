import { useState, useRef, useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  ClipboardCheck,
  ClipboardList,
  DoorOpen,
  FileText,
  Inbox,
  LayoutDashboard,
  LogOut,
  MoreHorizontal,
  PackageSearch,
  Settings,
  Shield,
  X,
} from "lucide-react";
import { useAuthStore } from "@/store/auth";
import { clsx } from "clsx";
import { useNavigate } from "react-router-dom";

export function MobileNav() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const location = useLocation();
  const [moreOpen, setMoreOpen] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);

  const isAdmin = user?.role.canManageUsers ?? false;
  const canViewReports = isAdmin || (user?.role.canManageInventory ?? false);

  // Close drawer when route changes
  useEffect(() => {
    setMoreOpen(false);
  }, [location.pathname]);

  // Close drawer when clicking outside
  useEffect(() => {
    if (!moreOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (drawerRef.current && !drawerRef.current.contains(e.target as Node)) {
        setMoreOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [moreOpen]);

  // Primary tabs (always visible)
  const primaryItems = [
    { to: "/dashboard", label: "Home", icon: LayoutDashboard },
    { to: "/rooms", label: "Rooms", icon: DoorOpen },
    { to: "/transactions", label: "Activity", icon: ClipboardList },
    { to: "/requests", label: "Requests", icon: Inbox },
  ];

  // Secondary items (in "More" drawer)
  const secondaryItems = [
    { to: "/inventory-list", label: "All Items", icon: PackageSearch },
    { to: "/checklist", label: "Checklist", icon: ClipboardCheck },
    ...(canViewReports ? [{ to: "/reports", label: "Reports", icon: FileText }] : []),
    ...(isAdmin ? [{ to: "/admin", label: "Admin", icon: Shield }] : []),
    { to: "/settings", label: "Settings", icon: Settings },
  ];

  // Is any secondary route active?
  const secondaryActive = secondaryItems.some((item) =>
    location.pathname.startsWith(item.to)
  );

  const handleLogout = () => {
    logout();
    navigate("/login");
    setMoreOpen(false);
  };

  return (
    <>
      {/* Backdrop */}
      {moreOpen && (
        <div
          className="md:hidden fixed inset-0 z-30 bg-slate-900/40"
          onClick={() => setMoreOpen(false)}
        />
      )}

      {/* More drawer (slides up) */}
      {moreOpen && (
        <div
          ref={drawerRef}
          className="md:hidden fixed bottom-16 inset-x-0 z-40 bg-white border-t border-slate-200 rounded-t-xl shadow-xl"
        >
          <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100">
            <span className="text-sm font-semibold text-slate-700">More</span>
            <button
              onClick={() => setMoreOpen(false)}
              className="p-1 text-slate-400 hover:text-slate-700"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <nav className="p-3 space-y-1">
            {secondaryItems.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                onClick={() => setMoreOpen(false)}
                className={({ isActive }) =>
                  clsx(
                    "flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-brand-50 text-brand-700"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  )
                }
              >
                <Icon className="h-5 w-5 flex-shrink-0" />
                {label}
              </NavLink>
            ))}
            <button
              onClick={handleLogout}
              className="flex w-full items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors"
            >
              <LogOut className="h-5 w-5 flex-shrink-0" />
              Sign out
            </button>
          </nav>
        </div>
      )}

      {/* Bottom tab bar */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-white border-t border-slate-200 flex safe-bottom">
        {primaryItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              clsx(
                "flex-1 flex flex-col items-center justify-center py-2 gap-0.5 text-xs font-medium transition-colors",
                isActive ? "text-brand-600" : "text-slate-500"
              )
            }
          >
            <Icon className="h-5 w-5" />
            {label}
          </NavLink>
        ))}

        {/* More button */}
        <button
          onClick={() => setMoreOpen((v) => !v)}
          className={clsx(
            "flex-1 flex flex-col items-center justify-center py-2 gap-0.5 text-xs font-medium transition-colors",
            secondaryActive || moreOpen ? "text-brand-600" : "text-slate-500"
          )}
        >
          <MoreHorizontal className="h-5 w-5" />
          More
        </button>
      </nav>
    </>
  );
}
