import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { resolveQRToken } from "@/api/qr";

/**
 * QR scan landing page: /qr/:token
 * Resolves the token via the API and redirects to the correct item or bin page.
 */
export function QRScanPage() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();

  useEffect(() => {
    if (!token) {
      navigate("/dashboard", { replace: true });
      return;
    }

    resolveQRToken(token)
      .then(({ type, id }) => {
        if (type === "item") {
          navigate(`/inventory/items/${id}`, { replace: true });
        } else {
          // Bins live on cabinet detail page; redirect to inventory for now
          navigate(`/inventory?bin=${id}`, { replace: true });
        }
      })
      .catch(() => {
        navigate("/dashboard", { replace: true });
      });
  }, [token, navigate]);

  return (
    <div className="flex h-full items-center justify-center">
      <div className="text-center space-y-3">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-600 border-t-transparent mx-auto" />
        <p className="text-sm text-slate-500">Resolving QR code…</p>
      </div>
    </div>
  );
}
