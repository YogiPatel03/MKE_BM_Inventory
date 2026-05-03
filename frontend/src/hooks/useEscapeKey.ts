import { useEffect, useRef } from "react";

/**
 * Calls handler when Escape is pressed. Uses a ref so the caller doesn't need
 * to memoize the handler to avoid re-registering the listener.
 */
export function useEscapeKey(handler: () => void): void {
  const handlerRef = useRef(handler);
  handlerRef.current = handler;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") handlerRef.current();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
}
