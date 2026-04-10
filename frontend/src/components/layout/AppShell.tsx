import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { MobileNav } from "./MobileNav";

export function AppShell() {
  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      <Sidebar />
      {/*
        On mobile the bottom nav bar is 64px tall.
        pb-16 (= 4rem = 64px) ensures content is never hidden behind it.
        We use min-h-0 + overflow-y-auto to fix the mobile "cabinet view
        disappears on first load" bug — without min-h-0 the flex child
        can't scroll independently.
      */}
      <main className="flex-1 min-h-0 overflow-y-auto pb-16 md:pb-0">
        <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
          <Outlet />
        </div>
      </main>
      <MobileNav />
    </div>
  );
}
