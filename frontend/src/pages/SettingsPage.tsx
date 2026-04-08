import { useState } from "react";
import { Link2, CheckCircle, Copy } from "lucide-react";
import { apiClient } from "@/api/client";
import { useAuthStore } from "@/store/auth";

async function generateLinkToken(): Promise<{ token: string; instructions: string }> {
  const { data } = await apiClient.get("/users/me/link-token");
  return data;
}

export function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const [token, setToken] = useState<string | null>(null);
  const [instructions, setInstructions] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");

  const handleGenerate = async () => {
    setIsLoading(true);
    setError("");
    try {
      const result = await generateLinkToken();
      setToken(result.token);
      setInstructions(result.instructions);
    } catch {
      setError("Failed to generate token. Try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopy = () => {
    if (!token) return;
    navigator.clipboard.writeText(`/link ${token}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6 max-w-xl">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
        <p className="text-sm text-slate-500 mt-0.5">Account preferences</p>
      </div>

      {/* Profile */}
      <div className="card p-5 space-y-3">
        <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">Profile</h2>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-xs text-slate-400">Full name</p>
            <p className="font-medium text-slate-900">{user?.fullName}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400">Username</p>
            <p className="font-medium text-slate-900">{user?.username}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400">Role</p>
            <p className="font-medium text-slate-900">{user?.role.name}</p>
          </div>
          <div>
            <p className="text-xs text-slate-400">Telegram</p>
            <p className="font-medium text-slate-900">
              {user?.telegramHandle ? `@${user.telegramHandle}` : "—"}
            </p>
          </div>
        </div>
      </div>

      {/* Telegram linking */}
      <div className="card p-5 space-y-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide flex items-center gap-2">
            <Link2 className="h-4 w-4" />
            Link Telegram
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            Link your Telegram account to receive overdue reminders and use bot commands like{" "}
            <code className="bg-slate-100 px-1 rounded text-xs">/myitems</code>.
          </p>
        </div>

        {user?.telegramHandle && (
          <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 rounded-lg px-3 py-2">
            <CheckCircle className="h-4 w-4 flex-shrink-0" />
            Telegram handle <strong>@{user.telegramHandle}</strong> is set on your account.
            {!user.telegramChatId && (
              <span className="text-slate-500 ml-1">(not yet linked via bot)</span>
            )}
          </div>
        )}

        {user?.telegramChatId && (
          <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 rounded-lg px-3 py-2">
            <CheckCircle className="h-4 w-4 flex-shrink-0" />
            Telegram is fully linked. You'll receive notifications directly.
          </div>
        )}

        {token ? (
          <div className="space-y-3">
            <p className="text-sm text-slate-600">
              Open the bot and send this command:
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 bg-slate-100 rounded-lg px-3 py-2 text-sm font-mono break-all">
                /link {token}
              </code>
              <button
                onClick={handleCopy}
                className="btn-secondary flex-shrink-0 text-xs py-2"
              >
                {copied ? <CheckCircle className="h-4 w-4 text-green-600" /> : <Copy className="h-4 w-4" />}
              </button>
            </div>
            <p className="text-xs text-slate-400">
              This token expires when used. Generate a new one if needed.
            </p>
            <button onClick={handleGenerate} className="text-xs text-slate-500 hover:text-slate-700 underline">
              Generate new token
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            <button
              onClick={handleGenerate}
              disabled={isLoading}
              className="btn-primary"
            >
              <Link2 className="h-4 w-4" />
              {isLoading ? "Generating…" : "Generate link token"}
            </button>
            {error && <p className="text-sm text-red-600">{error}</p>}
          </div>
        )}
      </div>
    </div>
  );
}
