import { useEffect, useState } from "react";
import { api } from "./api/client.js";

const NAV_ITEMS = ["Dashboard", "Content", "Leads", "Conversations", "Settings"];

export default function App() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");
  const [active, setActive] = useState("Dashboard");

  useEffect(() => {
    api("/api/health")
      .then(setHealth)
      .catch((err) => setError(err instanceof Error ? err.message : "API unreachable."));
  }, []);

  return (
    <div className="min-h-screen flex">
      <aside className="w-56 shrink-0 border-r border-slate-800 p-4">
        <h1 className="text-lg font-bold mb-1">Marketing Platform</h1>
        <p className="text-xs text-slate-400 mb-6">AI content · compliant leads · CRM</p>
        <nav className="space-y-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item}
              onClick={() => setActive(item)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm ${
                active === item ? "bg-sky-600 text-white" : "text-slate-300 hover:bg-slate-800"
              }`}
            >
              {item}
            </button>
          ))}
        </nav>
      </aside>
      <main className="flex-1 p-8">
        <h2 className="text-2xl font-bold mb-4">{active}</h2>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
          {error ? (
            <p className="text-red-400 text-sm">Backend error: {error}</p>
          ) : health ? (
            <div className="space-y-2 text-sm">
              <p>
                Backend: <span className="text-emerald-400 font-semibold">{health.status}</span> ·
                v{health.version} · {health.environment}
              </p>
              <p className="text-slate-400">
                Integrations — Claude API: {health.integrations.anthropic_configured ? "configured" : "not configured"},
                WhatsApp Cloud API: {health.integrations.whatsapp_configured ? "configured" : "not configured"}
              </p>
              <p className="text-xs text-slate-500">
                Phase 1 skeleton. Content / Leads / Conversations panels arrive in Phases 2–4.
              </p>
            </div>
          ) : (
            <p className="text-slate-400 text-sm animate-pulse">Checking backend…</p>
          )}
        </div>
      </main>
    </div>
  );
}
