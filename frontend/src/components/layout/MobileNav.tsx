import { NavLink } from "react-router-dom";
import { Box, ClipboardList, LayoutDashboard, Settings, Shield } from "lucide-react";
import { useAuthStore } from "@/store/auth";
import { clsx } from "clsx";

export function MobileNav() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role.canManageUsers ?? false;

  const items = [
    { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { to: "/inventory", label: "Inventory", icon: Box },
    { to: "/transactions", label: "Txns", icon: ClipboardList },
    ...(isAdmin ? [{ to: "/admin", label: "Admin", icon: Shield }] : []),
    { to: "/settings", label: "Settings", icon: Settings },
  ];

  return (
    <nav className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-white border-t border-slate-200 flex">
      {items.map(({ to, label, icon: Icon }) => (
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
    </nav>
  );
}
