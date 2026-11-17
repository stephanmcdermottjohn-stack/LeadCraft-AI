import { useEffect, useState } from "react";
import { api, clearSession, getToken, getUser, setSession } from "./api/client";

const PLATFORMS = ["facebook", "instagram", "tiktok", "whatsapp_status", "other"];
const NAV_ITEMS = ["Dashboard", "Content", "Leads", "Conversations", "Settings"];

// Business templates (mirrors backend/app/services/business_types.py keys).
// Selecting one prefills a niche suggestion and turns on the landing extras.
const BUSINESS_TYPES = [
  { value: "", label: "General / Other", hint: "" },
  { value: "property", label: "Property / Real Estate", hint: "real estate agency and dealer services" },
  { value: "ecommerce", label: "E-Commerce / Retail Store", hint: "online store and retail products" },
  { value: "hospitality", label: "Hotel / Guest House", hint: "hotel rooms and guest house bookings" },
  { value: "restaurant", label: "Restaurant / Cafe / Catering", hint: "restaurant dining and catering services" },
  { value: "salon", label: "Salon / Beauty / Spa", hint: "salon, bridal makeup and spa services" },
  { value: "health", label: "Clinic / Healthcare", hint: "clinic consultations and healthcare services" },
  { value: "education", label: "Education / Coaching / Tuition", hint: "coaching classes and tuition services" },
  { value: "fitness", label: "Gym / Fitness Trainer", hint: "gym membership and personal training" },
  { value: "travel", label: "Travel Agency / Tours", hint: "tour packages and travel bookings" },
  { value: "auto", label: "Car Dealer / Auto Workshop", hint: "car sales and auto services" },
  { value: "construction", label: "Construction / Architect", hint: "construction and architectural design services" },
  { value: "legal", label: "Lawyer / Legal Services", hint: "legal consultation and representation" },
  { value: "events", label: "Event Management / Wedding Planner", hint: "event planning and wedding services" },
  { value: "photography", label: "Photography / Studio", hint: "photography and videography services" },
  { value: "cleaning", label: "Cleaning / Maintenance Services", hint: "cleaning, repair and maintenance services" },
  { value: "finance", label: "Finance / Insurance / Loans", hint: "insurance policies and loan advisory" },
  { value: "it", label: "IT / Software Services", hint: "software development and IT services" },
];

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
  const [settings, setSettings] = useState({ niche: "", target_area: "", brand_voice: "", landing_slug: null, show_property_fields: false, business_type: "" });
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

  const setType = (value) => {
    const tmpl = BUSINESS_TYPES.find((t) => t.value === value);
    setSettings((s) => ({
      ...s,
      business_type: value,
      // One-click convenience: suggest a niche when the field is empty, and
      // turn the extras toggle on for any template that has extra fields.
      niche: !s.niche && tmpl?.hint ? tmpl.hint : s.niche,
      show_property_fields: value && tmpl?.hint ? true : s.show_property_fields,
    }));
  };

  const save = async () => {
    try {
      const payload = {
        niche: settings.niche,
        target_area: settings.target_area,
        brand_voice: settings.brand_voice,
        // Empty input keeps the existing slug; "auto" derives from the name.
        landing_slug: slugInput === (settings.landing_slug ?? "") ? null : slugInput || null,
        // Toggle + template are always sent so the controls are the source of truth.
        show_property_fields: settings.show_property_fields,
        business_type: settings.business_type,
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
          Business type
          <select
            className="mt-1 block w-full rounded-lg bg-slate-800 px-3 py-2"
            value={settings.business_type}
            onChange={(e) => setType(e.target.value)}
          >
            {BUSINESS_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
          <span className="block text-xs text-slate-500 mt-1">
            Ready-made template: sets a niche suggestion and the right extra fields on your landing page.
          </span>
        </label>
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
        <label className="block text-sm">
          <span className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={settings.show_property_fields}
              onChange={(e) => setSettings({ ...settings, show_property_fields: e.target.checked })}
            />
            Property fields on the landing page (real estate)
          </span>
          <span className="block text-xs text-slate-500 mt-1">
            Adds optional buy/rent/sell, property type and budget fields to <code>/l/&lt;slug&gt;</code>.
          </span>
        </label>
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
  const [extra, setExtra] = useState({});
  const [consent, setConsent] = useState(false);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Honeypot: hidden field humans never fill. Never label it as a honeypot.
  const [company, setCompany] = useState("");
  // Attribution: UTM/campaign params from the share link (roadmap P0).
  const attribution = (() => {
    const p = new URLSearchParams(window.location.search);
    const get = (k) => (p.get(k) || "").slice(0, 200);
    return {
      campaign: get("campaign") || get("utm_campaign"),
      utm_source: get("utm_source"),
      utm_medium: get("utm_medium"),
      utm_content: get("utm_content"),
      utm_term: get("utm_term"),
      landing_variant: (p.get("v") || "").slice(0, 50),
    };
  })();

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
          extra: config.extra_fields?.length ? extra : {},
          ...attribution,
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
            {config.extra_fields?.length > 0 && (
              <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-950 p-3">
                <p className="text-xs text-slate-400 font-semibold">Additional details (optional)</p>
                {config.extra_fields.map((f, idx) => (
                  <label key={f.key} className={`block text-sm ${idx < config.extra_fields.length - 1 ? "" : ""}`}>
                    {f.label}
                    {f.type === "select" ? (
                      <select
                        className="mt-1 block w-full rounded-lg bg-slate-800 px-3 py-2"
                        value={extra[f.key] ?? ""}
                        onChange={(e) => setExtra({ ...extra, [f.key]: e.target.value })}
                      >
                        <option value="">—</option>
                        {(f.options ?? []).map((o) => (
                          <option key={o} value={o}>{o}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        className="mt-1 block w-full rounded-lg bg-slate-800 px-3 py-2"
                        type={f.type === "number" ? "number" : "text"}
                        placeholder={f.label}
                        value={extra[f.key] ?? ""}
                        onChange={(e) => setExtra({ ...extra, [f.key]: e.target.value })}
                      />
                    )}
                  </label>
                ))}
              </div>
            )}
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
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [openNotes, setOpenNotes] = useState(null); // lead id
  const [notes, setNotes] = useState({});
  const [noteDraft, setNoteDraft] = useState("");
  const [showImport, setShowImport] = useState(false);
  const [importSource, setImportSource] = useState("meta_lead_ad");
  const [importConsent, setImportConsent] = useState(false);
  const [importMsg, setImportMsg] = useState("");
  const STATUSES = ["new", "contacted", "converted", "archived"];
  const SOURCES = ["landing_page", "meta_lead_ad", "google_lead_form", "whatsapp_inbound", "direct_message"];
  const LIFECYCLE_STAGES = ["capture", "qualify", "nurture", "convert", "retain", "reactivate"];

  const loadLeads = (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v));
    setError("");
    return api(`/api/leads${qs.size ? `?${qs}` : ""}`)
      .then((b) => setLeads(b.leads))
      .catch((err) => setError(err.message));
  };

  useEffect(() => {
    loadLeads();
  }, []);

  // Debounced re-fetch on filter changes
  useEffect(() => {
    const t = setTimeout(() => loadLeads({ q, status: statusFilter, source: sourceFilter }), 300);
    return () => clearTimeout(t);
  }, [q, statusFilter, sourceFilter]);

  const setStatus = async (id, status) => {
    try {
      const b = await api(`/api/leads/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
      setLeads((rows) => rows.map((l) => (l.id === id ? b.lead : l)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed.");
    }
  };

  const setStage = async (id, stage) => {
    try {
      const b = await api(`/api/leads/${id}/stage`, { method: "PATCH", body: JSON.stringify({ stage }) });
      setLeads((rows) => rows.map((l) => (l.id === id ? b.lead : l)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Stage update failed.");
    }
  };

  const exportCsv = async () => {
    try {
      const token = getToken();
      const res = await fetch("/api/leads/export.csv", { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error(`Export failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `leads-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed.");
    }
  };

  const toggleNotes = async (id) => {
    if (openNotes === id) {
      setOpenNotes(null);
      return;
    }
    setOpenNotes(id);
    if (!notes[id]) {
      try {
        const b = await api(`/api/leads/${id}/notes`);
        setNotes((n) => ({ ...n, [id]: b.notes }));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Notes failed.");
      }
    }
  };

  const addNote = async (id) => {
    if (!noteDraft.trim()) return;
    try {
      const b = await api(`/api/leads/${id}/notes`, { method: "POST", body: JSON.stringify({ body: noteDraft }) });
      setNotes((n) => ({ ...n, [id]: [b.note, ...(n[id] ?? [])] }));
      setNoteDraft("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Note failed.");
    }
  };

  const mdLine = (md) => {
    const entries = Object.entries(md ?? {}).filter(([, v]) => String(v).trim());
    if (!entries.length) return "";
    // Legacy property keys display bare; template extras show as key: value.
    return entries.map(([k, v]) => (["deal_type", "property_type", "budget"].includes(k) ? v : `${k}: ${v}`)).join(" · ");
  };

  // Minimal quoted-CSV parser (handles "quoted, values" and "" escapes).
  const parseCsv = (text) => {
    const rows = [];
    let cur = [];
    let val = "";
    let inQ = false;
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (inQ) {
        if (ch === '"') {
          if (text[i + 1] === '"') { val += '"'; i++; } else { inQ = false; }
        } else val += ch;
      } else if (ch === '"') inQ = true;
      else if (ch === ",") { cur.push(val); val = ""; }
      else if (ch === "\n" || ch === "\r") {
        if (ch === "\r" && text[i + 1] === "\n") i++;
        cur.push(val); val = "";
        rows.push(cur); cur = [];
      } else val += ch;
    }
    if (val !== "" || cur.length) { cur.push(val); rows.push(cur); }
    return rows.filter((r) => r.some((c) => c.trim() !== ""));
  };

  const importCsv = async (file) => {
    setError("");
    setImportMsg("");
    const text = await file.text();
    const table = parseCsv(text);
    if (table.length < 2) {
      setImportMsg("CSV has no data rows.");
      return;
    }
    const header = table[0].map((h) => h.trim().toLowerCase());
    const find = (...names) => names.find((n) => header.includes(n));
    const iName = find("name", "full name");
    const iPhone = find("phone", "phone number", "mobile");
    const iEmail = find("email", "email address");
    const iArea = find("area", "city", "location", "address");
    const iNotes = find("notes", "note", "what do you need", "details", "message", "comments");
    if (iName === undefined || (iPhone === undefined && iEmail === undefined)) {
      setImportMsg("CSV needs a Name column and a Phone or Email column.");
      return;
    }
    const rows = table.slice(1).map((r) => ({
      name: (r[iName] ?? "").trim(),
      phone: iPhone !== undefined ? (r[iPhone] ?? "").trim() : "",
      email: iEmail !== undefined ? (r[iEmail] ?? "").trim() : "",
      area: iArea !== undefined ? (r[iArea] ?? "").trim() : "",
      notes: iNotes !== undefined ? (r[iNotes] ?? "").trim() : "",
    }));
    if (!importConsent) {
      setImportMsg("Confirm the consent checkbox first.");
      return;
    }
    try {
      const b = await api("/api/leads/import", {
        method: "POST",
        body: JSON.stringify({ source: importSource, consent: true, rows }),
      });
      setImportMsg(`Imported ${b.imported} leads (${b.skipped} skipped).`);
      loadLeads();
    } catch (err) {
      setImportMsg(err instanceof Error ? err.message : "Import failed.");
    }
  };

  return (
    <div className="space-y-4 max-w-2xl">
      {error && <p className="text-xs text-red-400">{error}</p>}
      <div className="flex flex-wrap gap-2 items-center">
        <input
          className="flex-1 min-w-40 rounded-lg bg-slate-800 px-3 py-2 text-sm"
          placeholder="Search name, phone, email, area, notes…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select className="rounded-lg bg-slate-800 px-2 py-2 text-sm" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        <select className="rounded-lg bg-slate-800 px-2 py-2 text-sm" value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
          <option value="">All sources</option>
          {SOURCES.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        <button className="rounded-lg bg-slate-800 px-3 py-2 text-sm hover:bg-slate-700" onClick={() => { setShowImport(!showImport); setImportMsg(""); }}>
          Import CSV
        </button>
        <button className="rounded-lg bg-slate-800 px-3 py-2 text-sm hover:bg-slate-700" onClick={exportCsv}>
          Export CSV
        </button>
      </div>
      {showImport && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-3 text-sm">
          <p className="font-semibold">Import leads from a platform export</p>
          <p className="text-xs text-slate-400">
            Meta Lead Ads ya Google lead form ki CSV export yahan import karo — leads us platform pe pehle se
            consent de chuki hoti hain. Consent timestamp import time pe record hota hai.
          </p>
          <div className="flex flex-wrap gap-3 items-center">
            <select className="rounded-lg bg-slate-800 px-2 py-2 text-sm" value={importSource} onChange={(e) => setImportSource(e.target.value)}>
              <option value="meta_lead_ad">Meta Lead Ads export</option>
              <option value="google_lead_form">Google lead form export</option>
            </select>
            <input
              type="file"
              accept=".csv,text/csv"
              className="text-xs"
              onChange={(e) => e.target.files?.[0] && importCsv(e.target.files[0])}
            />
          </div>
          <label className="flex items-center gap-2 text-xs">
            <input type="checkbox" checked={importConsent} onChange={(e) => setImportConsent(e.target.checked)} />
            I confirm these leads consented on the source platform (Meta / Google form).
          </label>
          {importMsg && <p className="text-xs text-sky-300">{importMsg}</p>}
        </div>
      )}
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
                <select
                  className="rounded bg-indigo-900 px-2 py-1 text-xs"
                  value={l.lifecycle_stage}
                  onChange={(e) => setStage(l.id, e.target.value)}
                  title="Lifecycle stage"
                >
                  {LIFECYCLE_STAGES.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
                {l.grade && <span className="rounded bg-emerald-900 px-2 py-0.5 text-xs">Grade {l.grade}</span>}
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
              {mdLine(l.metadata) && (
                <p className="mt-1 text-xs text-sky-300">🏠 {mdLine(l.metadata)}</p>
              )}
              {(l.campaign || l.utm_source) && (
                <p className="mt-1 text-xs text-violet-300">
                  📣 {[l.campaign, l.utm_source, l.utm_medium].filter(Boolean).join(" / ")}
                  {l.landing_variant ? ` · variant ${l.landing_variant}` : ""}
                </p>
              )}
              {l.next_action && (
                <p className="mt-1 text-xs text-amber-300">
                  ▶ {l.next_action}
                  {l.next_action_at ? ` (by ${new Date(l.next_action_at).toLocaleDateString()})` : ""}
                </p>
              )}
              {l.intent_notes && <p className="mt-1 text-slate-400 whitespace-pre-wrap">{l.intent_notes}</p>}
              <button className="mt-2 text-xs text-slate-400 hover:text-slate-200" onClick={() => toggleNotes(l.id)}>
                {openNotes === l.id ? "Hide notes" : `Notes${(notes[l.id]?.length ?? 0) ? ` (${notes[l.id].length})` : ""}`}
              </button>
              {openNotes === l.id && (
                <div className="mt-2 space-y-2 border-t border-slate-800 pt-2">
                  <div className="flex gap-2">
                    <input
                      className="flex-1 rounded bg-slate-800 px-2 py-1 text-xs"
                      placeholder="Add a follow-up note…"
                      value={noteDraft}
                      onChange={(e) => setNoteDraft(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && addNote(l.id)}
                    />
                    <button className="rounded bg-sky-700 px-2 py-1 text-xs hover:bg-sky-600" onClick={() => addNote(l.id)}>
                      Add
                    </button>
                  </div>
                  <ul className="space-y-1">
                    {(notes[l.id] ?? []).map((n) => (
                      <li key={n.id} className="rounded bg-slate-950 p-2 text-xs">
                        <span className="text-slate-500">{n.created_at ? new Date(n.created_at).toLocaleString() : ""}</span>
                        <p className="text-slate-300 mt-0.5">{n.body}</p>
                      </li>
                    ))}
                    {!(notes[l.id] ?? []).length && <li className="text-xs text-slate-500">No notes yet.</li>}
                  </ul>
                </div>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function AdminPanel() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/api/admin/overview")
      .then(setStats)
      .catch((err) => setError(err instanceof Error ? err.message : "Load failed."));
  }, []);

  if (error) {
    return <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm text-red-400">{error}</div>;
  }
  if (!stats) {
    return <div className="text-sm text-slate-400">Loading platform stats…</div>;
  }
  return (
    <div className="space-y-4 max-w-3xl">
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
          <p className="text-3xl font-bold">{stats.total_users}</p>
          <p className="text-xs text-slate-400">Registered businesses</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
          <p className="text-3xl font-bold">{stats.total_leads}</p>
          <p className="text-xs text-slate-400">Total leads (all businesses)</p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
          <p className="font-semibold mb-2">Leads by source</p>
          <ul className="text-sm text-slate-300 space-y-1">
            {Object.entries(stats.leads_by_source).map(([k, v]) => (
              <li key={k} className="flex justify-between"><span>{k}</span><span>{v}</span></li>
            ))}
          </ul>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
          <p className="font-semibold mb-2">Leads by status</p>
          <ul className="text-sm text-slate-300 space-y-1">
            {Object.entries(stats.leads_by_status).map(([k, v]) => (
              <li key={k} className="flex justify-between"><span>{k}</span><span>{v}</span></li>
            ))}
          </ul>
        </div>
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
        <p className="font-semibold mb-3">Recent businesses</p>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-500">
              <th className="pb-2">Business</th><th className="pb-2">Email</th><th className="pb-2">Plan</th><th className="pb-2">Leads</th><th className="pb-2">Joined</th>
            </tr>
          </thead>
          <tbody>
            {stats.recent_users.map((u) => (
              <tr key={u.id} className="border-t border-slate-800">
                <td className="py-2">{u.business_name}</td>
                <td className="py-2 text-slate-400">{u.email}</td>
                <td className="py-2 text-slate-400">{u.plan_tier}</td>
                <td className="py-2">{u.lead_count}</td>
                <td className="py-2 text-slate-500">{u.created_at ? new Date(u.created_at).toLocaleDateString() : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">
        Admins see aggregate stats only — individual leads stay visible to their owning business (privacy rule).
      </p>
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

  const navItems = user.is_admin ? [...NAV_ITEMS, "Admin"] : NAV_ITEMS;
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
          {navItems.map((item) => (
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
        {active === "Admin" && <AdminPanel />}
        {active === "Conversations" && (
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm text-slate-400">
            This panel ships in Phase 4 (WhatsApp funnel).
          </div>
        )}
      </main>
    </div>
  );
}
