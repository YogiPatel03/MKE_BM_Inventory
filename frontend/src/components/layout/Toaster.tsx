import { useEffect } from "react";
import { CheckCircle, Info, X, XCircle } from "lucide-react";
import { clsx } from "clsx";
import { useToastStore, type ToastItem } from "@/store/toast";

const ICONS = {
  success: CheckCircle,
  error: XCircle,
  info: Info,
};

const STYLES = {
  success: {
    wrap: "bg-green-50 border-green-200",
    text: "text-green-800",
    icon: "text-green-500",
  },
  error: {
    wrap: "bg-red-50 border-red-200",
    text: "text-red-800",
    icon: "text-red-500",
  },
  info: {
    wrap: "bg-blue-50 border-blue-200",
    text: "text-blue-800",
    icon: "text-blue-500",
  },
};

const AUTO_DISMISS_MS = 4000;

function Toast({ id, message, type }: ToastItem) {
  const removeToast = useToastStore((s) => s.removeToast);
  const Icon = ICONS[type];
  const s = STYLES[type];

  useEffect(() => {
    const timer = setTimeout(() => removeToast(id), AUTO_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [id, removeToast]);

  return (
    <div
      role="alert"
      aria-live="polite"
      className={clsx(
        "flex items-start gap-3 rounded-xl border px-4 py-3 shadow-lg text-sm w-full max-w-sm",
        s.wrap
      )}
    >
      <Icon className={clsx("h-5 w-5 flex-shrink-0 mt-0.5", s.icon)} aria-hidden="true" />
      <p className={clsx("flex-1", s.text)}>{message}</p>
      <button
        onClick={() => removeToast(id)}
        aria-label="Dismiss notification"
        className={clsx("p-0.5 rounded hover:opacity-70 transition-opacity flex-shrink-0", s.text)}
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

export function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  if (toasts.length === 0) return null;

  return (
    /* bottom-20 on mobile clears the 64 px bottom nav; md:bottom-6 on desktop */
    <div className="fixed bottom-20 md:bottom-6 right-4 z-[200] flex flex-col gap-2 items-end pointer-events-none">
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto">
          <Toast {...t} />
        </div>
      ))}
    </div>
  );
}
