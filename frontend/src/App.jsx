import { useEffect, useState } from "react";
import { api, clearSession, getUser, setSession } from "./api/client";

const PLATFORMS = ["facebook", "instagram", "tiktok", "whatsapp_status", "other"];
const NAV_ITEMS = ["Dashboard", "Content", "Leads", "Conversations", "Settings"];

function AuthScreen({ onAuthed }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ business_name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const path = mode === "login" ? "/api/auth/login" : "/api/auth/register";
      const payload =
        mode === "login"
          ? { email: form.email, password: form.password }
          : { business_name: form.business_name, email: form.email, password: form.password };
      const body = await api(path, { method: "POST", body: JSON.stringify(payload) });
      setSession(body.token, body.user);
      onAuthed(body.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Auth failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl border border-slate-800 bg-slate-900 p-6">
        <h1 className="text-xl font-bold">LeadCraft AI</h1>
        <p className="text-xs text-slate-400">AI content · compliant leads · CRM</p>
        {mode === "register" && (
          <input
            className="w-full rounded-lg bg-slate-800 px-3 py-2 text-sm"
            placeholder="Business name"
            value={form.business_name}
            onChange={(e) => setForm({ ...form, business_name: e.target.value })}
            required
          />
        )}
        <input
          className="w-full rounded-lg bg-slate-800 px-3 py-2 text-sm"
          type="email"
          placeholder="Email"
          value={form.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
          required
        />
        <input
          className="w-full rounded-lg bg-slate-800 px-3 py-2 text-sm"
          type="password"
          placeholder={mode === "register" ? "Password (min 8 chars)" : "Password"}
          value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
          required
        />
        {error && <p className="text-xs text-red-400">{error}</p>}
        <button className="w-full rounded-lg bg-sky-600 py-2 text-sm font-semibold hover:bg-sky-500" disabled={busy}>
          {busy ? "…" : mode === "login" ? "Log in" : "Create account"}
        </button>
        <button
          type="button"
          className="w-full text-xs text-slate-400 hover:text-slate-200"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
        >
          {mode === "login" ? "No account? Register" : "Have an account? Log in"}
        </button>
      </form>
    </div>
  );
}

function ContentPanel() {
  const [platform, setPlatform] = useState("facebook");
  const [tone, setTone] = useState("friendly");
  const [options, setOptions] = useState([]);
  const [genNotice, setGenNotice] = useState("");
  const [posts, setPosts] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [scheduleFor, setScheduleFor] = useState(null); // option text
  const [scheduleAt, setScheduleAt] = useState("");

  const loadPosts = () =>
    api("/api/content/posts")
      .then((b) => setPosts(b.posts))
      .catch((err) => setError(err.message));

  useEffect(() => {
    loadPosts();
  }, []);

  const generate = async () => {
    setBusy(true);
    setError("");
    setOptions([]);
    setGenNotice("");
    try {
      const body = await api("/api/content/generate", {
        method: "POST",
        body: JSON.stringify({ platform, tone, count: 3 }),
      });
      setOptions(body.options);
      setGenNotice(body.notice ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed.");
    } finally {
      setBusy(false);
    }
  };

  const schedule = async (text, at) => {
    setBusy(true);
    setError("");
    try {
      await api("/api/content/schedule", {
        method: "POST",
        body: JSON.stringify({
          content_text: text,
          platform,
          scheduled_at: at || null,
        }),
      });
      setScheduleFor(null);
      setScheduleAt("");
      await loadPosts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scheduling failed.");
    } finally {
      setBusy(false);
    }
  };

  const saveDraft = (text) => schedule(text, null);

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
        <h3 className="font-semibold mb-3">Generate content</h3>
        <div className="flex flex-wrap gap-3 items-end">
          <label className="text-sm">
            Platform
            <select className="block rounded-lg bg-slate-800 px-3 py-2 mt-1" value={platform} onChange={(e) => setPlatform(e.target.value)}>
              {PLATFORMS.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            Tone
            <input className="block rounded-lg bg-slate-800 px-3 py-2 mt-1 w-40" value={tone} onChange={(e) => setTone(e.target.value)} />
          </label>
          <button className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold hover:bg-sky-500 disabled:opacity-50" onClick={generate} disabled={busy}>
            {busy ? "Generating…" : "Generate"}
          </button>
        </div>
        {genNotice && <p className="mt-3 text-xs text-amber-400">{genNotice}</p>}
        {error && <p className="mt-3 text-xs text-red-400">{error}</p>}
        {options.length > 0 && (
          <ul className="mt-4 space-y-3">
            {options.map((opt, i) => (
              <li key={i} className="rounded-lg border border-slate-800 bg-slate-950 p-4 text-sm">
                <p className="whitespace-pre-wrap">{opt}</p>
                <div className="mt-2 flex gap-2">
                  <button className="rounded bg-slate-800 px-2 py-1 text-xs hover:bg-slate-700" onClick={() => saveDraft(opt)} disabled={busy}>
                    Save as draft
                  </button>
                  <button className="rounded bg-emerald-700 px-2 py-1 text-xs hover:bg-emerald-600" onClick={() => setScheduleFor(opt)}>
                    Schedule…
                  </button>
                </div>
                {scheduleFor === opt && (
                  <div className="mt-2 flex gap-2 items-center">
                    <input
                      type="datetime-local"
                      className="rounded bg-slate-800 px-2 py-1 text-xs"
                      value={scheduleAt}
                      onChange={(e) => setScheduleAt(e.target.value)}
                    />
                    <button
                      className="rounded bg-emerald-700 px-2 py-1 text-xs hover:bg-emerald-600"
                      onClick={() => schedule(opt, scheduleAt ? new Date(scheduleAt).toISOString() : null)}
                      disabled={busy || !scheduleAt}
                    >
                      Confirm schedule
                    </button>
                    <button className="text-xs text-slate-400" onClick={() => setScheduleFor(null)}>
                      Cancel
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
        <h3 className="font-semibold mb-3">Posts ({posts.length})</h3>
        {posts.length === 0 && <p className="text-sm text-slate-400">No posts yet.</p>}
        <ul className="space-y-2">
          {posts.map((p) => (
            <li key={p.id} className="rounded-lg border border-slate-800 bg-slate-950 p-3 text-sm">
              <span className={`mr-2 rounded px-2 py-0.5 text-xs ${p.status === "ready_to_publish" ? "bg-emerald-800" : "bg-slate-800"}`}>
                {p.status}
              </span>
              <span className="text-xs text-slate-400">{p.platform}{p.scheduled_at ? ` · ${new Date(p.scheduled_at).toLocaleString()}` : ""}</span>
              <p className="mt-1 whitespace-pre-wrap text-slate-200">{p.content_text}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function SettingsPanel({ user, onLogout }) {
  const [settings, setSettings] = useState({ niche: "", target_area: "", brand_voice: "", landing_slug: null });
  const [slugInput, setSlugInput] = useState("");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/api/settings")
      .then((b) => {
        setSettings(b.settings);
        setSlugInput(b.settings.landing_slug ?? "");
      })
      .catch((err) => setError(err.message));
  }, []);

  const save = async () => {
    try {
      const payload = {
        niche: settings.niche,
        target_area: settings.target_area,
        brand_voice: settings.brand_voice,
        // Empty input keeps the existing slug; "auto" derives from the name.
        landing_slug: slugInput === (settings.landing_slug ?? "") ? null : slugInput || null,
      };
      const b = await api("/api/settings", { method: "PATCH", body: JSON.stringify(payload) });
      setSettings(b.settings);
      setSlugInput(b.settings.landing_slug ?? "");
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    }
  };

  const field = (key, label, textarea = false) => (
    <label className="block text-sm">
      {label}
      {textarea ? (
        <textarea
          className="mt-1 block w-full rounded-lg bg-slate-800 px-3 py-2"
          rows={3}
          value={settings[key]}
          onChange={(e) => setSettings({ ...settings, [key]: e.target.value })}
        />
      ) : (
        <input
          className="mt-1 block w-full rounded-lg bg-slate-800 px-3 py-2"
          value={settings[key]}
          onChange={(e) => setSettings({ ...settings, [key]: e.target.value })}
        />
      )}
    </label>
  );

  return (
    <div className="space-y-6 max-w-lg">
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
        <h3 className="font-semibold">Business profile</h3>
        <p className="text-xs text-slate-400">
          {user.business_name} · {user.email}
        </p>
        {field("niche", "Niche (e.g. bridal makeup, real estate)")}
        {field("target_area", "Target area (e.g. DHA Lahore)")}
        {field("brand_voice", "Brand voice (e.g. warm, premium)", true)}
        <label className="block text-sm">
          Landing page slug
          <div className="flex gap-2 mt-1">
            <input
              className="flex-1 rounded-lg bg-slate-800 px-3 py-2"
              placeholder="gulberg-salon (or type: auto)"
              value={slugInput}
              onChange={(e) => setSlugInput(e.target.value)}
            />
            <button
              type="button"
              className="rounded-lg bg-slate-800 px-3 text-xs hover:bg-slate-700"
              onClick={() => setSlugInput("auto")}
            >
              Auto
            </button>
          </div>
        </label>
        {settings.landing_slug && (
          <p className="text-xs text-emerald-400">
            Public page: <a className="underline" href={`/l/${settings.landing_slug}`} target="_blank" rel="noreferrer">/l/{settings.landing_slug}</a> — share this with customers.
          </p>
        )}
        {error && <p className="text-xs text-red-400">{error}</p>}
        <button className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold hover:bg-sky-500" onClick={save}>
          Save
        </button>
        {saved && <span className="text-xs text-emerald-400"> Saved ✓</span>}
        <p className="text-xs text-slate-500">These power the AI content prompts — personalized per business, not generic.</p>
      </div>
      <button className="text-sm text-red-400 hover:text-red-300" onClick={onLogout}>
        Log out
      </button>
    </div>
  );
}

function LandingPage({ slug }) {
  const [config, setConfig] = useState(null);
  const [form, setForm] = useState({ name: "", phone: "", email: "", area: "", intent_notes: "" });
  const [consent, setConsent] = useState(false);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Honeypot: hidden field humans never fill. Never label it as a honeypot.
  const [company, setCompany] = useState("");

  useEffect(() => {
    api(`/api/public/landing/${encodeURIComponent(slug)}`)
      .then(setConfig)
      .catch(() => setConfig(null));
  }, [slug]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/api/leads/capture", {
        method: "POST",
        body: JSON.stringify({
          slug,
          name: form.name,
          phone: form.phone,
          email: form.email,
          area: form.area,
          intent_notes: form.intent_notes,
          company,
          consent,
        }),
      });
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Submission failed.");
    } finally {
      setBusy(false);
    }
  };

  if (config === null && !error) {
    return <div className="min-h-screen flex items-center justify-center text-slate-400 text-sm">Loading…</div>;
  }
  if (!config) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4 text-center">
        <div>
          <h1 className="text-xl font-bold mb-2">Page not found</h1>
          <p className="text-sm text-slate-400">This business page does not exist.</p>
        </div>
      </div>
    );
  }

  const field = (key, label, placeholder, type = "text") => (
    <label className="block text-sm">
      {label}
      <input
        className="mt-1 block w-full rounded-lg bg-slate-800 px-3 py-2"
        type={type}
        placeholder={placeholder}
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
      />
    </label>
  );

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md rounded-xl border border-slate-800 bg-slate-900 p-6">
        {done ? (
          <div className="text-center space-y-3 py-6">
            <div className="text-4xl">✅</div>
            <h1 className="text-xl font-bold">Thank you, {form.name.split(" ")[0]}!</h1>
            <p className="text-sm text-slate-400">
              {config.business_name} has received your request and will reach out soon.
            </p>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <div>
              <h1 className="text-2xl font-bold">{config.business_name}</h1>
              <p className="text-sm text-slate-400">
                {config.niche || "Quality services"}
                {config.target_area ? ` · ${config.target_area}` : ""}
              </p>
            </div>
            {field("name", "Your name", "Full name")}
            {field("phone", "Phone", "03xx xxxxxxx")}
            {field("email", "Email (optional)", "you@example.com", "email")}
            {field("area", "Your area (optional)", "e.g. Gulberg, Lahore")}
            <label className="block text-sm">
              What do you need?
              <textarea
                className="mt-1 block w-full rounded-lg bg-slate-800 px-3 py-2"
                rows={3}
                placeholder="Tell the business what you're looking for…"
                value={form.intent_notes}
                onChange={(e) => setForm({ ...form, intent_notes: e.target.value })}
              />
            </label>
            {/* Honeypot — visually hidden, humans never fill this */}
            <input
              aria-hidden="true"
              tabIndex={-1}
              autoComplete="off"
              className="absolute opacity-0 h-0 w-0"
              placeholder="Company"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
            />
            <label className="flex items-start gap-2 text-xs text-slate-300">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
                required
              />
              <span>
                I agree that {config.business_name} may contact me using the details above. My consent and the
                submission time are recorded.
              </span>
            </label>
            {error && <p className="text-xs text-red-400">{error}</p>}
            <button
              className="w-full rounded-lg bg-sky-600 py-2 text-sm font-semibold hover:bg-sky-500 disabled:opacity-50"
              disabled={busy || !consent}
            >
              {busy ? "Sending…" : "Request a callback"}
            </button>
            <p className="text-[10px] text-slate-500 text-center">Powered by LeadCraft AI</p>
          </form>
        )}
      </div>
    </div>
  );
}

function LeadsPanel() {
  const [leads, setLeads] = useState([]);
  const [error, setError] = useState("");
  const STATUSES = ["new", "contacted", "converted", "archived"];

  const loadLeads = () =>
    api("/api/leads")
      .then((b) => setLeads(b.leads))
      .catch((err) => setError(err.message));

  useEffect(() => {
    loadLeads();
  }, []);

  const setStatus = async (id, status) => {
    try {
      const b = await api(`/api/leads/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
      setLeads((rows) => rows.map((l) => (l.id === id ? b.lead : l)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed.");
    }
  };

  return (
    <div className="space-y-4 max-w-2xl">
      {error && <p className="text-xs text-red-400">{error}</p>}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
        <h3 className="font-semibold mb-3">Leads ({leads.length})</h3>
        {leads.length === 0 && (
          <p className="text-sm text-slate-400">
            No leads yet. Share your landing page URL (see Settings) — submissions appear here with consent recorded.
          </p>
        )}
        <ul className="space-y-3">
          {leads.map((l) => (
            <li key={l.id} className="rounded-lg border border-slate-800 bg-slate-950 p-4 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded bg-sky-900 px-2 py-0.5 text-xs">{l.source}</span>
                <span className="rounded bg-slate-800 px-2 py-0.5 text-xs">{l.status}</span>
                <span className="text-xs text-slate-500">
                  consent: {l.consent_timestamp ? new Date(l.consent_timestamp).toLocaleString() : "—"}
                </span>
                <select
                  className="ml-auto rounded bg-slate-800 px-2 py-1 text-xs"
                  value={l.status}
                  onChange={(e) => setStatus(l.id, e.target.value)}
                >
                  {STATUSES.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </div>
              <p className="mt-2 font-semibold">{l.name}</p>
              <p className="text-slate-300">
                {l.phone}
                {l.phone && l.email ? " · " : ""}
                {l.email}
                {l.area ? ` · ${l.area}` : ""}
              </p>
              {l.intent_notes && <p className="mt-1 text-slate-400 whitespace-pre-wrap">{l.intent_notes}</p>}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default function App() {
  // Public landing pages live at /l/<slug> — render them with no dashboard,
  // no auth state, and no dashboard data in the bundle path.
  const landingMatch = /^\/l\/([a-z0-9-]+)\/?$/.exec(window.location.pathname);
  if (landingMatch) return <LandingPage slug={landingMatch[1]} />;
  return <DashboardApp />;
}

function DashboardApp() {
  const [user, setUser] = useState(getUser());
  const [active, setActive] = useState("Dashboard");

  if (!user) return <AuthScreen onAuthed={setUser} />;

  const logout = () => {
    clearSession();
    setUser(null);
  };

  return (
    <div className="min-h-screen flex">
      <aside className="w-56 shrink-0 border-r border-slate-800 p-4">
        <h1 className="text-lg font-bold mb-1">LeadCraft AI</h1>
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
        {active === "Dashboard" && (
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm">
            <p className="text-emerald-400 font-semibold">Connected</p>
            <p className="mt-2 text-slate-300">
              Welcome back, {user.business_name}. Use <b>Settings</b> to define your niche and brand voice, then{" "}
              <b>Content</b> to generate and schedule posts.
            </p>
            <p className="mt-2 text-xs text-slate-500">Conversations panel arrives in Phase 4 (WhatsApp funnel).</p>
          </div>
        )}
        {active === "Content" && <ContentPanel />}
        {active === "Leads" && <LeadsPanel />}
        {active === "Settings" && <SettingsPanel user={user} onLogout={logout} />}
        {active === "Conversations" && (
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm text-slate-400">
            This panel ships in Phase 4 (WhatsApp funnel).
          </div>
        )}
      </main>
    </div>
  );
}
