import { useEscapeKey } from "@/hooks/useEscapeKey";

interface Props {
  title: string;
  message: string;
  confirmLabel?: string;
  isDangerous?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmModal({
  title,
  message,
  confirmLabel = "Confirm",
  isDangerous = false,
  onConfirm,
  onCancel,
}: Props) {
  useEscapeKey(onCancel);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        aria-describedby="confirm-modal-desc"
        className="card w-full max-w-sm p-6"
      >
        <h2 id="confirm-modal-title" className="text-lg font-semibold text-slate-900 mb-2">
          {title}
        </h2>
        <p id="confirm-modal-desc" className="text-sm text-slate-600 mb-6">
          {message}
        </p>
        <div className="flex gap-3">
          <button onClick={onCancel} className="btn-secondary flex-1 justify-center">
            Cancel
          </button>
          <button
            onClick={onConfirm}
            autoFocus
            className={
              isDangerous
                ? "btn-danger flex-1 justify-center"
                : "btn-primary flex-1 justify-center"
            }
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
