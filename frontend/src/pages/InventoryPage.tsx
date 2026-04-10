import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

/**
 * /inventory is now superseded by the Room > Cabinet hierarchy.
 * Redirect to /rooms for backwards compatibility.
 */
export function InventoryPage() {
  const navigate = useNavigate();
  useEffect(() => {
    navigate("/rooms", { replace: true });
  }, [navigate]);
  return null;
}
