import { useState } from "react";
import { useEscapeKey } from "@/hooks/useEscapeKey";

interface Props {
  title: string;
  label: string;
  placeholder?: string;
  confirmLabel?: string;
  optional?: boolean;
  onConfirm: (value: string) => void;
  onCancel: () => void;
}

export function PromptModal({
  title,
  label,
  placeholder,
  confirmLabel = "Confirm",
  optional = true,
  onConfirm,
  onCancel,
}: Props) {
  const [value, setValue] = useState("");
  useEscapeKey(onCancel);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onConfirm(value);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="prompt-modal-title"
        className="card w-full max-w-sm p-6"
      >
        <h2 id="prompt-modal-title" className="text-lg font-semibold text-slate-900 mb-4">
          {title}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label htmlFor="prompt-modal-input" className="label">
              {label}
              {optional && <span className="text-slate-400 font-normal ml-1">(optional)</span>}
            </label>
            <input
              id="prompt-modal-input"
              className="input"
              placeholder={placeholder}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              autoFocus
            />
          </div>
          <div className="flex gap-3">
            <button type="button" onClick={onCancel} className="btn-secondary flex-1 justify-center">
              Cancel
            </button>
            <button type="submit" className="btn-primary flex-1 justify-center">
              {confirmLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
