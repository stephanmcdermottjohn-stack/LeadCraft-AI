import { useEffect, useState } from "react";
import { api, apiBaseUrl, clearSession, getToken, getUser, setSession } from "./api/client";

const PLATFORMS = ["facebook", "instagram", "tiktok", "whatsapp_status", "other"];
const NAV_ITEMS = ["Dashboard", "Content", "Leads", "Appointments", "Conversations", "Reports", "Settings"];

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
      // The welcome tour is triggered only by a fresh registration, never by a
      // normal login. Existing accounts therefore never see it retroactively.
      onAuthed(body.user, { isNew: mode === "register" });
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

// One-time welcome tour shown immediately after account creation. It is a
// static, client-only screen: no API calls, no tracking, no auto-anything.
// Existing users never see it because DashboardApp only opens it from the
// register path (and remembers per-user completion in localStorage).
const INTRO_BANNERS = [
  {
    icon: "target",
    accent: "border-sky-500/25 bg-sky-500/10 text-sky-400",
    title: "Get potential leads — not random traffic",
    body:
      "Publish a landing page for your business, or build your own from ready-made blocks. Every form records consent and where the lead came from, so you know exactly who to follow up with.",
    chips: ["Landing pages", "Custom pages", "Per-page stats"],
    cta: "Set up your pages",
    go: "Settings",
  },
  {
    icon: "sparkles",
    accent: "border-violet-500/25 bg-violet-500/10 text-violet-400",
    title: "Plan a week of content in minutes",
    body:
      "Generate on-brand posts for Facebook, Instagram, TikTok and WhatsApp status. You review, edit and schedule — the platform never publishes behind your back.",
    chips: ["AI drafts", "Brand voice", "Scheduling"],
    cta: "Create your first post",
    go: "Content",
  },
  {
    icon: "chart",
    accent: "border-emerald-500/25 bg-emerald-500/10 text-emerald-400",
    title: "See what's working — honestly",
    body:
      "Follow the journey from first visit to won deal. Reports show real counts, and anything still unknown is labelled unknown instead of being filled with a made-up number.",
    chips: ["Funnel", "Source reports", "Revenue"],
    cta: "Open reports",
    go: "Reports",
  },
  {
    icon: "chat",
    accent: "border-amber-500/25 bg-amber-500/10 text-amber-400",
    title: "Keep every follow-up in one place",
    body:
      "Log chats and notes on each lead, take bookings from your public page, and always see the next action. Replies stay manual and consent-first — no auto-messaging.",
    chips: ["Lead timeline", "Bookings", "Conversation log"],
    cta: "Open conversations",
    go: "Conversations",
  },
];

function IntroIcon({ name, className = "h-5 w-5" }) {
  const common = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    className,
    "aria-hidden": true,
  };
  if (name === "target") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="9" />
        <circle cx="12" cy="12" r="5" />
        <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
      </svg>
    );
  }
  if (name === "sparkles") {
    return (
      <svg {...common}>
        <path d="M11 3l1.7 4.3L17 9l-4.3 1.7L11 15l-1.7-4.3L5 9l4.3-1.7L11 3z" />
        <path d="M18.5 14.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8.8-2z" />
      </svg>
    );
  }
  if (name === "chart") {
    return (
      <svg {...common}>
        <path d="M4 19h16" />
        <path d="M7 16v-5" />
        <path d="M12 16V7" />
        <path d="M17 16v-3" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M20 15a2 2 0 0 1-2 2H8l-4 4V5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2z" />
      <path d="M8 8h8M8 11h5" />
    </svg>
  );
}

function WelcomeIntro({ user, onDone, onGo }) {
  const businessName = (user?.business_name || "your business").trim();
  const scrollToFeatures = () => {
    const el = document.getElementById("intro-features");
    if (el && typeof el.scrollIntoView === "function") {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-slate-950 text-slate-100">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-48 left-1/2 h-[30rem] w-[30rem] -translate-x-1/2 rounded-full bg-sky-500/10 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-24 right-0 h-80 w-80 rounded-full bg-emerald-500/5 blur-3xl"
      />

      <main className="relative mx-auto w-full max-w-5xl px-4 py-8 sm:px-6 sm:py-12">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-sky-500/15 text-xs font-bold tracking-wide text-sky-400 ring-1 ring-inset ring-sky-500/30">
              LC
            </span>
            <span className="text-sm font-semibold tracking-wide text-slate-200">LeadCraft AI</span>
          </div>
          <button
            type="button"
            onClick={onDone}
            className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-400 transition hover:bg-slate-900 hover:text-slate-200 focus:outline-none focus:ring-2 focus:ring-sky-400"
          >
            Skip intro
          </button>
        </div>

        <section className="mt-10 sm:mt-14">
          <span className="inline-flex items-center gap-2 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-400">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            Your workspace is ready
          </span>
          <p className="mt-5 text-xs font-semibold uppercase tracking-[0.18em] text-sky-400">
            Welcome aboard, {businessName}
          </p>
          <h1 className="mt-2 max-w-3xl text-3xl font-bold leading-tight sm:text-5xl">
            Meet LeadCraft AI — <span className="text-sky-400">your business copilot.</span>
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-400">
            Capture consented leads, create content, keep follow-ups together and see what actually brings customers
            in. No auto-spam, no fake scores, and nothing here needs a paid add-on to start.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            {["Free to start", "Consent-first", "No auto-spam"].map((chip) => (
              <span
                key={chip}
                className="rounded-full border border-slate-800 bg-slate-900/70 px-3 py-1 text-xs text-slate-300"
              >
                {chip}
              </span>
            ))}
          </div>
          <div className="mt-7 flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={onDone}
              className="rounded-lg bg-sky-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-sky-950/40 transition hover:bg-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-400 focus:ring-offset-2 focus:ring-offset-slate-950"
            >
              Open my dashboard
            </button>
            <button
              type="button"
              onClick={scrollToFeatures}
              className="rounded-lg border border-slate-700 bg-slate-900/60 px-5 py-2.5 text-sm font-semibold text-slate-200 transition hover:border-slate-600 hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-400 focus:ring-offset-2 focus:ring-offset-slate-950"
            >
              See what's inside
            </button>
          </div>
        </section>

        <section id="intro-features" className="mt-12 grid gap-4 scroll-mt-6 md:grid-cols-2">
          {INTRO_BANNERS.map((banner) => (
            <article
              key={banner.title}
              className="group rounded-2xl border border-slate-800 bg-slate-900/60 p-5 transition hover:-translate-y-0.5 hover:border-slate-700 hover:bg-slate-900"
            >
              <div className={`inline-flex h-10 w-10 items-center justify-center rounded-xl border ${banner.accent}`}>
                <IntroIcon name={banner.icon} />
              </div>
              <h3 className="mt-3 text-base font-semibold text-slate-100">{banner.title}</h3>
              <p className="mt-1.5 text-sm leading-6 text-slate-400">{banner.body}</p>
              <ul className="mt-3 flex flex-wrap gap-1.5">
                {banner.chips.map((chip) => (
                  <li
                    key={chip}
                    className="rounded-md border border-slate-800 bg-slate-950/60 px-2 py-0.5 text-[11px] text-slate-400"
                  >
                    {chip}
                  </li>
                ))}
              </ul>
              <button
                type="button"
                onClick={() => onGo(banner.go)}
                className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-sky-400 transition hover:text-sky-300 focus:outline-none focus:ring-2 focus:ring-sky-400"
              >
                {banner.cta}
                <span aria-hidden="true">→</span>
              </button>
            </article>
          ))}
        </section>

        <div className="mt-8 flex flex-col items-start justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/50 p-4 sm:flex-row sm:items-center">
          <p className="text-xs text-slate-500">
            Everything here lives in your sidebar. This one-time intro won't appear again.
          </p>
          <button
            type="button"
            onClick={onDone}
            className="rounded-lg border border-slate-700 px-4 py-2 text-xs font-semibold text-slate-200 transition hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-400"
          >
            Start with dashboard
          </button>
        </div>
      </main>
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

function IcpEditor() {
  const [profiles, setProfiles] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [editing, setEditing] = useState(null); // null = list, {} = new, profile = edit
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const loadProfiles = () =>
    api("/api/icp").then((b) => setProfiles(b.profiles)).catch((err) => setError(err.message));
  useEffect(() => {
    loadProfiles();
    api("/api/icp/templates").then((b) => setTemplates(b.templates)).catch(() => {});
  }, []);

  const blank = { name: "", industry: "", company_size: "", location: "", budget_min: "", budget_max: "", business_type: "", needs: "", preferred_services: "", decision_authority: "", buying_timeline: "", criteria: "", is_default: false };

  const openNew = (template) => {
    const prefill = template ? { ...template } : { ...blank };
    const crit = Array.isArray(prefill.criteria) ? prefill.criteria.join(", ") : (prefill.criteria ?? "");
    setEditing({
      ...blank, ...prefill, id: template?.id,
      criteria: crit,
      budget_min: prefill.budget_min ?? "",
      budget_max: prefill.budget_max ?? "",
      label: undefined, key: undefined,
    });
  };

  const save = async () => {
    setError(""); setMsg("");
    try {
      const payload = {
        name: editing.name,
        industry: editing.industry,
        company_size: editing.company_size,
        location: editing.location,
        budget_min: editing.budget_min === "" ? null : Number(editing.budget_min),
        budget_max: editing.budget_max === "" ? null : Number(editing.budget_max),
        business_type: editing.business_type,
        needs: editing.needs,
        preferred_services: editing.preferred_services,
        decision_authority: editing.decision_authority,
        buying_timeline: editing.buying_timeline,
        criteria: editing.criteria.split(",").map((c) => c.trim()).filter(Boolean),
        is_default: editing.is_default,
      };
      const res = editing.id
        ? await api(`/api/icp/${editing.id}`, { method: "PATCH", body: JSON.stringify(payload) })
        : await api("/api/icp", { method: "POST", body: JSON.stringify(payload) });
      setMsg(`Saved "${res.profile.name}".`);
      setEditing(null);
      loadProfiles();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    }
  };

  const remove = async (id) => {
    try {
      await api(`/api/icp/${id}`, { method: "DELETE" });
      loadProfiles();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    }
  };

  const setDefault = async (p) => {
    try {
      await api(`/api/icp/${p.id}`, { method: "PATCH", body: JSON.stringify({ ...p, criteria: p.criteria }) });
      loadProfiles();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed.");
    }
  };

  const numField = (key, label) => (
    <label className="block text-sm">
      {label}
      <input
        type="number"
        className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2"
        placeholder="PKR (blank = no bound)"
        value={editing[key]}
        onChange={(e) => setEditing({ ...editing, [key]: e.target.value })}
      />
    </label>
  );

  if (editing) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-3 max-w-lg">
        <h3 className="font-semibold">{editing.id ? "Edit ICP" : "New Ideal Customer Profile"}</h3>
        <label className="block text-sm">Profile name
          <input className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2" value={editing.name}
                 onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm">Industry
            <input className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2" value={editing.industry}
                   onChange={(e) => setEditing({ ...editing, industry: e.target.value })} />
          </label>
          <label className="block text-sm">Location
            <input className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2" placeholder="e.g. Gulberg, DHA"
                   value={editing.location} onChange={(e) => setEditing({ ...editing, location: e.target.value })} />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {numField("budget_min", "Budget minimum")}
          {numField("budget_max", "Budget maximum")}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm">Business type
            <select className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2" value={editing.business_type}
                    onChange={(e) => setEditing({ ...editing, business_type: e.target.value })}>
              {BUSINESS_TYPES.map((t) => (<option key={t.value} value={t.value}>{t.label}</option>))}
            </select>
          </label>
          <label className="block text-sm">Company size
            <input className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2" placeholder="e.g. 10-50 staff"
                   value={editing.company_size} onChange={(e) => setEditing({ ...editing, company_size: e.target.value })} />
          </label>
        </div>
        <label className="block text-sm">Customer needs (keywords)
          <input className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2" placeholder="e.g. bridal makeup package"
                 value={editing.needs} onChange={(e) => setEditing({ ...editing, needs: e.target.value })} />
        </label>
        <label className="block text-sm">Preferred services (keywords)
          <input className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2" placeholder="e.g. trial session, consultation"
                 value={editing.preferred_services} onChange={(e) => setEditing({ ...editing, preferred_services: e.target.value })} />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm">Decision authority
            <input className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2" placeholder="e.g. owner, parent"
                   value={editing.decision_authority} onChange={(e) => setEditing({ ...editing, decision_authority: e.target.value })} />
          </label>
          <label className="block text-sm">Buying timeline
            <input className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2" placeholder="e.g. within 1 month"
                   value={editing.buying_timeline} onChange={(e) => setEditing({ ...editing, buying_timeline: e.target.value })} />
          </label>
        </div>
        <label className="block text-sm">Custom criteria (comma separated)
          <input className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2" placeholder="e.g. repeat buyer, local resident"
                 value={editing.criteria} onChange={(e) => setEditing({ ...editing, criteria: e.target.value })} />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={editing.is_default}
                 onChange={(e) => setEditing({ ...editing, is_default: e.target.checked })} />
          Use as the default profile for lead fit checks
        </label>
        {error && <p className="text-xs text-red-400">{error}</p>}
        <div className="flex gap-2">
          <button className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold hover:bg-sky-500" onClick={save}>Save</button>
          <button className="rounded-lg bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700" onClick={() => setEditing(null)}>Cancel</button>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4 max-w-lg">
      <h3 className="font-semibold">Ideal Customer Profile (ICP)</h3>
      <p className="text-xs text-slate-400">
        Describe your ideal customer — leads are then graded (A-D) against it with a transparent, factor-by-factor explanation.
      </p>
      {error && <p className="text-xs text-red-400">{error}</p>}
      {msg && <p className="text-xs text-emerald-400">{msg}</p>}
      <ul className="space-y-2">
        {profiles.map((p) => (
          <li key={p.id} className="rounded-lg border border-slate-800 bg-slate-950 p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold">{p.name}</span>
              {p.is_default && <span className="rounded bg-emerald-900 px-2 py-0.5 text-xs">default</span>}
              {p.industry && <span className="text-xs text-slate-400">{p.industry}</span>}
              <div className="ml-auto flex gap-2">
                {!p.is_default && (
                  <button className="text-xs text-slate-400 hover:text-slate-200" onClick={() => setDefault(p)}>Set default</button>
                )}
                <button className="text-xs text-sky-400 hover:text-sky-300" onClick={() => openNew({ ...p, id: p.id })}>Edit</button>
                <button className="text-xs text-red-400 hover:text-red-300" onClick={() => remove(p.id)}>Delete</button>
              </div>
            </div>
            {(p.needs || p.location) && (
              <p className="text-xs text-slate-500 mt-1">
                {[p.location && `📍 ${p.location}`, p.needs && `🎯 ${p.needs}`, p.buying_timeline && `⏱ ${p.buying_timeline}`].filter(Boolean).join(" · ")}
              </p>
            )}
          </li>
        ))}
        {profiles.length === 0 && (
          <li className="text-sm text-slate-400">No ICP profiles yet — start from a template or create your own.</li>
        )}
      </ul>
      <div className="flex flex-wrap gap-2 items-center">
        <button className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold hover:bg-sky-500" onClick={() => openNew(null)}>
          + New ICP
        </button>
        <select
          className="rounded-lg bg-slate-800 px-3 py-2 text-sm"
          value=""
          onChange={(e) => e.target.value && openNew(templates.find((t) => t.key === e.target.value))}
        >
          <option value="">Start from template…</option>
          {templates.map((t) => (
            <option key={t.key} value={t.key}>{t.label}</option>
          ))}
        </select>
      </div>
    </div>
  );
}

function AbEditor() {
  const [variants, setVariants] = useState([]);
  const [report, setReport] = useState(null);
  const [editing, setEditing] = useState(null); // null=list, {}=new, {id}=edit
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const load = () => {
    api("/api/landing-variants").then((b) => setVariants(b.variants)).catch((e) => setError(e.message));
    api("/api/landing-variants/report").then(setReport).catch(() => {});
  };
  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    setError(""); setMsg("");
    try {
      if (editing.id) {
        await api(`/api/landing-variants/${editing.id}`, { method: "PATCH", body: JSON.stringify(editing) });
        setMsg(`Variant ${editing.label} updated.`);
      } else {
        await api("/api/landing-variants", { method: "POST", body: JSON.stringify(editing) });
        setMsg(`Variant ${editing.label} created.`);
      }
      setEditing(null);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Save failed.");
    }
  };

  const remove = async (v) => {
    try {
      await api(`/api/landing-variants/${v.id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    }
  };

  if (editing) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-3 max-w-lg">
        <h3 className="font-semibold">{editing.id ? `Edit variant ${editing.label}` : "New A/B variant"}</h3>
        <p className="text-xs text-slate-400">
          Overrides headline / subtext / button label on your landing page. Blank = keep the business default.
        </p>
        {!editing.id && (
          <label className="block text-sm">Variant label (A/B/C…)
            <input className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2" placeholder="e.g. B"
                   value={editing.label} onChange={(e) => setEditing({ ...editing, label: e.target.value })} />
          </label>
        )}
        <label className="block text-sm">Headline
          <input className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2" placeholder="defaults to business name"
                 value={editing.headline ?? ""} onChange={(e) => setEditing({ ...editing, headline: e.target.value })} />
        </label>
        <label className="block text-sm">Subtext
          <input className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2" placeholder="defaults to niche · area"
                 value={editing.subtext ?? ""} onChange={(e) => setEditing({ ...editing, subtext: e.target.value })} />
        </label>
        <label className="block text-sm">Button label
          <input className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2" placeholder="defaults to 'Request a callback'"
                 value={editing.cta_label ?? ""} onChange={(e) => setEditing({ ...editing, cta_label: e.target.value })} />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={editing.is_active ?? true}
                 onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })} />
          Active (receiving traffic)
        </label>
        {error && <p className="text-xs text-red-400">{error}</p>}
        <div className="flex gap-2">
          <button className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold hover:bg-sky-500" onClick={save}>Save</button>
          <button className="rounded-lg bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700" onClick={() => setEditing(null)}>Cancel</button>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4 max-w-lg">
      <h3 className="font-semibold">Landing page A/B test</h3>
      <p className="text-xs text-slate-400">
        Visitors are split between your defaults (control) and active variants. Traffic is remembered per visitor — no cookies, no personal data.
      </p>
      {error && <p className="text-xs text-red-400">{error}</p>}
      {msg && <p className="text-xs text-emerald-400">{msg}</p>}
      <ul className="space-y-2 text-sm">
        <li className="rounded-lg border border-slate-800 bg-slate-950 p-3">
          <span className="font-semibold">Control</span>
          <span className="text-xs text-slate-500"> · business defaults (always active)</span>
        </li>
        {variants.map((v) => (
          <li key={v.id} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold">{v.label}</span>
              {!v.is_active && <span className="rounded bg-slate-800 px-2 py-0.5 text-xs">inactive</span>}
              {v.headline && <span className="text-xs text-slate-400">"{v.headline}"</span>}
              <div className="ml-auto flex gap-2 text-xs">
                <button className="text-sky-400 hover:text-sky-300" onClick={() => setEditing({ ...v })}>Edit</button>
                <button className="text-red-400 hover:text-red-300" onClick={() => remove(v)}>Delete</button>
              </div>
            </div>
          </li>
        ))}
        {variants.length === 0 && <li className="text-slate-400 text-sm">No variants yet.</li>}
      </ul>
      {report && (
        <div className="rounded-lg border border-slate-800 bg-slate-950 p-3">
          <p className="text-xs font-semibold text-slate-300">Report ({report.slug || "no landing page set"})</p>
          <table className="mt-1 w-full text-xs text-slate-400">
            <thead><tr className="text-left">
              <th className="py-1">Arm</th><th>Impr.</th><th>Subs</th><th>Qualified</th><th>Rate</th>
            </tr></thead>
            <tbody>
              {report.arms.map((a) => (
                <tr key={a.arm}>
                  <td className="py-1">{a.display}</td>
                  <td className="text-center">{a.impressions}</td>
                  <td className="text-center">{a.submissions}</td>
                  <td className="text-center">{a.qualified}</td>
                  <td className="text-center">{a.submission_rate_pct === null ? "—" : `${a.submission_rate_pct}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {report.arms.filter((a) => a.note).map((a) => (
            <p key={a.arm} className="mt-1 text-[10px] text-slate-500">{a.arm}: {a.note}</p>
          ))}
        </div>
      )}
      <button className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold hover:bg-sky-500"
              onClick={() => setEditing({ label: "", headline: "", subtext: "", cta_label: "", is_active: true })}>
        + New variant
      </button>
    </div>
  );
}

const PAGE_BLOCK_DEFAULTS = {
  hero: () => ({ type: "hero", heading: "", subheading: "", cta_label: "", image_url: "" }),
  text: () => ({ type: "text", heading: "", body: "" }),
  features: () => ({ type: "features", heading: "", items: [{ title: "", body: "" }] }),
  testimonial: () => ({ type: "testimonial", quote: "", author: "", role: "" }),
  faq: () => ({ type: "faq", heading: "", items: [{ question: "", answer: "" }] }),
  cta: () => ({ type: "cta", heading: "", body: "", button_label: "" }),
};
const PAGE_BLOCK_LABELS = {
  hero: "Hero",
  text: "Text",
  features: "Features",
  testimonial: "Testimonial",
  faq: "FAQ",
  cta: "Call to action",
};
const PAGE_MAX_BLOCKS = 12;

// Brand names are text. If a URL was pasted into the brand-name field, never
// print that raw URL into headings or consent copy — fall back to the real
// business name. (The logo belongs in logo_url and is rendered as an image.)
function displayBrandName(brandName, businessName = "", fallback = "") {
  const text = String(brandName || "").trim();
  const looksLikeUrl = /^(https?:\/\/|\/\/|\/)/i.test(text) || text.includes("://");
  const chosen = !text || looksLikeUrl ? String(businessName || "").trim() : text;
  return chosen || fallback;
}

// P7 #1: custom landing pages built from validated, text-only blocks. The
// public URL is /p/<slug>; lead capture reuses the same consent-first endpoint.
function PagesEditor() {
  const [pages, setPages] = useState([]);
  const [limit, setLimit] = useState(20);
  const [editing, setEditing] = useState(null); // null=list, {}=new, {id}=edit
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  // P7 #2: per-page analytics (loaded on demand, cached per page id).
  const [openStats, setOpenStats] = useState(null);
  const [statsById, setStatsById] = useState({});

  const load = () => {
    api("/api/pages")
      .then((b) => {
        setPages(b.pages);
        setLimit(b.limit || 20);
      })
      .catch((err) => setError(err.message.replace(/^API \d+: /, "")));
  };
  useEffect(() => {
    load();
  }, []);

  const fail = (err) => setError(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Request failed.");

  const save = async () => {
    setError("");
    setMsg("");
    setBusy(true);
    try {
      const body = JSON.stringify({
        slug: editing.slug,
        title: editing.title,
        blocks: editing.blocks,
        is_published: editing.is_published,
      });
      if (editing.id) {
        await api(`/api/pages/${editing.id}`, { method: "PATCH", body });
        setMsg("Page updated.");
      } else {
        await api("/api/pages", { method: "POST", body });
        setMsg("Page created.");
      }
      setEditing(null);
      load();
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const togglePublish = async (page) => {
    setError("");
    setMsg("");
    try {
      await api(`/api/pages/${page.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_published: !page.is_published }),
      });
      load();
    } catch (err) {
      fail(err);
    }
  };

  const remove = async (page) => {
    if (!window.confirm(`Delete page "${page.title || page.slug}"? This cannot be undone.`)) return;
    setError("");
    setMsg("");
    try {
      await api(`/api/pages/${page.id}`, { method: "DELETE" });
      setMsg("Page deleted.");
      load();
    } catch (err) {
      fail(err);
    }
  };

  const toggleStats = async (page) => {
    if (openStats === page.id) {
      setOpenStats(null);
      return;
    }
    setOpenStats(page.id);
    if (statsById[page.id]) return;
    try {
      const data = await api(`/api/pages/${page.id}/analytics`);
      setStatsById((cur) => ({ ...cur, [page.id]: data }));
    } catch (err) {
      fail(err);
    }
  };

  // --- block editing helpers -------------------------------------------------
  const setBlocks = (blocks) => setEditing((cur) => ({ ...cur, blocks }));
  const patchBlock = (index, patch) =>
    setBlocks(editing.blocks.map((b, i) => (i === index ? { ...b, ...patch } : b)));
  const addBlock = (type) => {
    if (editing.blocks.length >= PAGE_MAX_BLOCKS) {
      setError(`A page supports at most ${PAGE_MAX_BLOCKS} blocks.`);
      return;
    }
    setError("");
    setBlocks([...editing.blocks, PAGE_BLOCK_DEFAULTS[type]()]);
  };
  const removeBlock = (index) => setBlocks(editing.blocks.filter((_, i) => i !== index));
  const moveBlock = (index, delta) => {
    const target = index + delta;
    if (target < 0 || target >= editing.blocks.length) return;
    const next = [...editing.blocks];
    [next[index], next[target]] = [next[target], next[index]];
    setBlocks(next);
  };
  const patchItem = (index, itemIndex, patch) =>
    patchBlock(index, {
      items: editing.blocks[index].items.map((item, j) => (j === itemIndex ? { ...item, ...patch } : item)),
    });
  const addItem = (index) => {
    const block = editing.blocks[index];
    const blank = block.type === "features" ? { title: "", body: "" } : { question: "", answer: "" };
    patchBlock(index, { items: [...block.items, blank] });
  };
  const removeItem = (index, itemIndex) =>
    patchBlock(index, { items: editing.blocks[index].items.filter((_, j) => j !== itemIndex) });

  const line = (label, value, onChange, placeholder = "") => (
    <label className="block text-xs text-slate-400">
      {label}
      <input
        className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2 text-sm text-slate-100"
        value={value ?? ""}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
  const area = (label, value, onChange, rows = 3, placeholder = "") => (
    <label className="block text-xs text-slate-400">
      {label}
      <textarea
        className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2 text-sm text-slate-100"
        rows={rows}
        value={value ?? ""}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );

  const renderBlockEditor = (block, index) => (
    <div key={index} className="rounded-lg border border-slate-800 bg-slate-950 p-3 space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-slate-300">
          {index + 1}. {PAGE_BLOCK_LABELS[block.type] || block.type}
        </span>
        <div className="ml-auto flex gap-2 text-xs">
          <button type="button" className="text-slate-400 hover:text-slate-200" onClick={() => moveBlock(index, -1)} disabled={index === 0}>
            ↑
          </button>
          <button
            type="button"
            className="text-slate-400 hover:text-slate-200"
            onClick={() => moveBlock(index, 1)}
            disabled={index === editing.blocks.length - 1}
          >
            ↓
          </button>
          <button type="button" className="text-red-400 hover:text-red-300" onClick={() => removeBlock(index)}>
            Remove
          </button>
        </div>
      </div>
      {block.type === "hero" && (
        <>
          {line("Heading", block.heading, (v) => patchBlock(index, { heading: v }), "Bridal season is open")}
          {area("Subheading", block.subheading, (v) => patchBlock(index, { subheading: v }), 2)}
          {line("Button label", block.cta_label, (v) => patchBlock(index, { cta_label: v }), "Get started")}
          {line("Image URL (optional)", block.image_url, (v) => patchBlock(index, { image_url: v }), "https://…")}
        </>
      )}
      {block.type === "text" && (
        <>
          {line("Heading (optional)", block.heading, (v) => patchBlock(index, { heading: v }))}
          {area("Body", block.body, (v) => patchBlock(index, { body: v }), 4, "Plain text — line breaks are kept, HTML is not rendered.")}
        </>
      )}
      {block.type === "features" && (
        <>
          {line("Heading (optional)", block.heading, (v) => patchBlock(index, { heading: v }))}
          {block.items.map((item, j) => (
            <div key={j} className="rounded border border-slate-800 p-2 space-y-2">
              {line(`Feature ${j + 1} title`, item.title, (v) => patchItem(index, j, { title: v }))}
              {area("Description", item.body, (v) => patchItem(index, j, { body: v }), 2)}
              <button type="button" className="text-xs text-red-400" onClick={() => removeItem(index, j)}>
                Remove feature
              </button>
            </div>
          ))}
          <button type="button" className="text-xs text-sky-400" onClick={() => addItem(index)} disabled={block.items.length >= 6}>
            + Add feature (max 6)
          </button>
        </>
      )}
      {block.type === "testimonial" && (
        <>
          {area("Quote", block.quote, (v) => patchBlock(index, { quote: v }), 3)}
          {line("Author", block.author, (v) => patchBlock(index, { author: v }))}
          {line("Author role (optional)", block.role, (v) => patchBlock(index, { role: v }))}
        </>
      )}
      {block.type === "faq" && (
        <>
          {line("Heading (optional)", block.heading, (v) => patchBlock(index, { heading: v }))}
          {block.items.map((item, j) => (
            <div key={j} className="rounded border border-slate-800 p-2 space-y-2">
              {line(`Question ${j + 1}`, item.question, (v) => patchItem(index, j, { question: v }))}
              {area("Answer", item.answer, (v) => patchItem(index, j, { answer: v }), 2)}
              <button type="button" className="text-xs text-red-400" onClick={() => removeItem(index, j)}>
                Remove question
              </button>
            </div>
          ))}
          <button type="button" className="text-xs text-sky-400" onClick={() => addItem(index)} disabled={block.items.length >= 8}>
            + Add question (max 8)
          </button>
        </>
      )}
      {block.type === "cta" && (
        <>
          {line("Heading", block.heading, (v) => patchBlock(index, { heading: v }))}
          {area("Body (optional)", block.body, (v) => patchBlock(index, { body: v }), 2)}
          {line("Button label", block.button_label, (v) => patchBlock(index, { button_label: v }), "Request a callback")}
        </>
      )}
    </div>
  );

  if (editing) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-3 max-w-2xl">
        <h3 className="font-semibold">{editing.id ? "Edit custom page" : "New custom page"}</h3>
        <p className="text-xs text-slate-400">
          Plain-text blocks on a public page at <code>/p/&lt;slug&gt;</code>. No HTML is rendered, and the form only
          stores leads after explicit consent — the platform never messages them automatically.
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          {line("Slug (3–60 lowercase letters, digits, hyphens)", editing.slug, (v) => setEditing({ ...editing, slug: v }), "eid-bridal-offer")}
          {line("Page title", editing.title, (v) => setEditing({ ...editing, title: v }), "Eid bridal offer")}
        </div>
        {editing.id && (
          <p className="text-[11px] text-amber-400/80">
            Renaming a published slug breaks old shared links, and past analytics/leads stay attached to the old slug
            (history is never rewritten).
          </p>
        )}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={!!editing.is_published}
            onChange={(e) => setEditing({ ...editing, is_published: e.target.checked })}
          />
          Published (visible at /p/{editing.slug || "<slug>"})
        </label>

        <div className="space-y-2">
          {editing.blocks.map(renderBlockEditor)}
          {editing.blocks.length === 0 && (
            <p className="text-xs text-slate-500">No blocks yet — add a hero or a text block below.</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {Object.keys(PAGE_BLOCK_LABELS).map((type) => (
            <button
              key={type}
              type="button"
              className="rounded bg-slate-800 px-2 py-1 text-xs hover:bg-slate-700"
              onClick={() => addBlock(type)}
              disabled={editing.blocks.length >= PAGE_MAX_BLOCKS}
            >
              + {PAGE_BLOCK_LABELS[type]}
            </button>
          ))}
        </div>
        <p className="text-[11px] text-slate-500">
          {editing.blocks.length}/{PAGE_MAX_BLOCKS} blocks. Text only; unknown fields and HTML are rejected server-side.
        </p>
        {error && <p className="text-xs text-red-400">{error}</p>}
        <div className="flex gap-2">
          <button
            className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold hover:bg-sky-500 disabled:opacity-60"
            onClick={save}
            disabled={busy}
          >
            {busy ? "Saving…" : "Save page"}
          </button>
          <button
            className="rounded-lg bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700"
            onClick={() => {
              setEditing(null);
              setError("");
            }}
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4 max-w-2xl">
      <h3 className="font-semibold">Custom landing pages</h3>
      <p className="text-xs text-slate-400">
        Build extra pages from blocks (hero, text, features, testimonial, FAQ, call to action). Each page gets its own
        public URL <code>/p/&lt;slug&gt;</code> and its own consent form. Drafts are invisible until published.
      </p>
      {error && <p className="text-xs text-red-400">{error}</p>}
      {msg && <p className="text-xs text-emerald-400">{msg}</p>}
      <ul className="space-y-2 text-sm">
        {pages.map((page) => (
          <li key={page.id} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold">{page.title || page.slug}</span>
              <span className="text-xs text-slate-500">/p/{page.slug}</span>
              {page.is_published ? (
                <span className="rounded bg-emerald-900/60 px-2 py-0.5 text-xs text-emerald-300">published</span>
              ) : (
                <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">draft</span>
              )}
              <div className="ml-auto flex flex-wrap gap-2 text-xs">
                {page.is_published && (
                  <a className="text-sky-400 hover:text-sky-300" href={`/p/${page.slug}`} target="_blank" rel="noreferrer">
                    View
                  </a>
                )}
                <button className="text-sky-400 hover:text-sky-300" onClick={() => togglePublish(page)}>
                  {page.is_published ? "Unpublish" : "Publish"}
                </button>
                <button className="text-sky-400 hover:text-sky-300" onClick={() => toggleStats(page)}>
                  {openStats === page.id ? "Hide stats" : "Stats"}
                </button>
                <button
                  className="text-sky-400 hover:text-sky-300"
                  onClick={() => setEditing({ ...page, blocks: JSON.parse(JSON.stringify(page.blocks || [])) })}
                >
                  Edit
                </button>
                <button className="text-red-400 hover:text-red-300" onClick={() => remove(page)}>
                  Delete
                </button>
              </div>
            </div>
            <p className="mt-1 text-[11px] text-slate-500">
              {(page.blocks || []).length} block(s) · updated {page.updated_at ? new Date(page.updated_at).toLocaleString() : "—"}
            </p>
            {page.stats && (
              <p className="mt-1 text-[11px] text-slate-400">
                {page.stats.views} views · {page.stats.leads} leads ({page.stats.window_days}d)
                {page.stats.conversion_pct !== null && (
                  <> · {page.stats.conversion_pct}% conversion{page.stats.conversion_known ? "" : " (too early)"}</>
                )}
              </p>
            )}
            {openStats === page.id && (
              <div className="mt-2 rounded border border-slate-800 p-2 text-xs text-slate-400">
                {!statsById[page.id] ? (
                  <p>Loading…</p>
                ) : (
                  <>
                    <p className="text-slate-300">
                      Last {statsById[page.id].window_days} days: {statsById[page.id].funnel.page_view_sessions} visitors ·{" "}
                      {statsById[page.id].funnel.form_start_sessions} started the form ·{" "}
                      {statsById[page.id].leads_captured} leads
                    </p>
                    <p className="mt-1 text-[10px] text-slate-500">
                      {statsById[page.id].rates_known
                        ? `Submit rate ${statsById[page.id].submit_rate_pct}% (form starts → submits).`
                        : "Too early to judge rates — needs 30 sessions. Counts are real, rates are not estimated."}
                    </p>
                    <table className="mt-1 w-full text-[10px]">
                      <thead>
                        <tr className="text-left text-slate-500">
                          <th>Day</th><th>Views</th><th>Starts</th><th>Submits</th>
                        </tr>
                      </thead>
                      <tbody>
                        {statsById[page.id].daily.slice(-7).map((d) => (
                          <tr key={d.date}>
                            <td>{d.date.slice(5)}</td><td>{d.page_view}</td><td>{d.form_start}</td><td>{d.submit}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {statsById[page.id].notes.map((note, i) => (
                      <p key={i} className="mt-1 text-[10px] text-slate-500">{note}</p>
                    ))}
                  </>
                )}
              </div>
            )}
          </li>
        ))}
        {pages.length === 0 && <li className="text-sm text-slate-400">No custom pages yet.</li>}
      </ul>
      <button
        className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold hover:bg-sky-500 disabled:opacity-60"
        onClick={() => {
          setError("");
          setMsg("");
          setEditing({ slug: "", title: "", is_published: false, blocks: [] });
        }}
        disabled={pages.length >= limit}
      >
        + New page
      </button>
      <p className="text-[11px] text-slate-500">
        {pages.length}/{limit} pages. Agents and viewers cannot change pages (owner/admin/manager only).
      </p>
    </div>
  );
}

function NurtureEditor() {
  const [campaigns, setCampaigns] = useState([]);
  const [editing, setEditing] = useState(null); // null=list, {id?, name, steps, active}
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const load = () => api("/api/nurture/campaigns").then((b) => setCampaigns(b.campaigns)).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    setError(""); setMsg("");
    try {
      const payload = { name: editing.name, steps: editing.steps, active: editing.active };
      if (editing.id) {
        await api(`/api/nurture/campaigns/${editing.id}`, { method: "PATCH", body: JSON.stringify(payload) });
        setMsg(`Campaign "${editing.name}" updated.`);
      } else {
        await api("/api/nurture/campaigns", { method: "POST", body: JSON.stringify(payload) });
        setMsg(`Campaign "${editing.name}" created.`);
      }
      setEditing(null);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Save failed.");
    }
  };

  const remove = async (c) => {
    try {
      await api(`/api/nurture/campaigns/${c.id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Delete failed.");
    }
  };

  if (editing) {
    const setStep = (i, key, value) => {
      const steps = editing.steps.map((s, j) => (j === i ? { ...s, [key]: value } : s));
      setEditing({ ...editing, steps });
    };
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-3 max-w-lg">
        <h3 className="font-semibold">{editing.id ? `Edit campaign` : "New nurture campaign"}</h3>
        <label className="block text-sm">Campaign name
          <input className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2" value={editing.name}
                 onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
        </label>
        <p className="text-xs text-slate-400">
          Steps are touch scripts — the due step becomes the lead's "next action" on the dashboard. Nothing is auto-sent.
        </p>
        {editing.steps.map((s, i) => (
          <div key={i} className="flex gap-2 items-end">
            <label className="text-sm w-28">
              Day
              <input type="number" min="0" max="365" className="mt-1 w-full rounded-lg bg-slate-800 px-2 py-2"
                     value={s.day_offset} onChange={(e) => setStep(i, "day_offset", Number(e.target.value))} />
            </label>
            <label className="text-sm flex-1">
              Touch message
              <input className="mt-1 w-full rounded-lg bg-slate-800 px-3 py-2" placeholder="e.g. Intro call: ask about the event date"
                     value={s.message} onChange={(e) => setStep(i, "message", e.target.value)} />
            </label>
            {editing.steps.length > 1 && (
              <button className="text-xs text-red-400 pb-2" onClick={() => setEditing({ ...editing, steps: editing.steps.filter((_, j) => j !== i) })}>✕</button>
            )}
          </div>
        ))}
        <button className="text-xs text-sky-400 hover:text-sky-300"
                onClick={() => setEditing({ ...editing, steps: [...editing.steps, { day_offset: 0, message: "" }] })}>
          + Add step
        </button>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={editing.active ?? true}
                 onChange={(e) => setEditing({ ...editing, active: e.target.checked })} />
          Active (accepting enrollments)
        </label>
        {error && <p className="text-xs text-red-400">{error}</p>}
        <div className="flex gap-2">
          <button className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold hover:bg-sky-500" onClick={save}>Save</button>
          <button className="rounded-lg bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700" onClick={() => setEditing(null)}>Cancel</button>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4 max-w-lg">
      <h3 className="font-semibold">Nurture campaigns</h3>
      <p className="text-xs text-slate-400">
        Consent-gated follow-up sequences. Due touches appear as the lead's next action and timeline — nothing is auto-sent. Suppressed contacts are never enrolled.
      </p>
      {error && <p className="text-xs text-red-400">{error}</p>}
      {msg && <p className="text-xs text-emerald-400">{msg}</p>}
      <ul className="space-y-2">
        {campaigns.map((c) => (
          <li key={c.id} className="rounded-lg border border-slate-800 bg-slate-950 p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold">{c.name}</span>
              {!c.active && <span className="rounded bg-slate-800 px-2 py-0.5 text-xs">inactive</span>}
              <div className="ml-auto flex gap-2 text-xs">
                <button className="text-sky-400 hover:text-sky-300" onClick={() => setEditing({ ...c })}>Edit</button>
                <button className="text-red-400 hover:text-red-300" onClick={() => remove(c)}>Delete</button>
              </div>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              {c.steps.length} step(s) · {c.metrics ? `${c.metrics.active} active · ${c.metrics.completed} completed · ${c.metrics.suppressed} suppressed` : ""}
            </p>
            <p className="text-xs text-slate-400">
              {c.steps.map((s) => `D+${s.day_offset}: ${s.message}`).join(" · ")}
            </p>
          </li>
        ))}
        {campaigns.length === 0 && <li className="text-sm text-slate-400">No campaigns yet.</li>}
      </ul>
      <button className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold hover:bg-sky-500"
              onClick={() => setEditing({ name: "", steps: [{ day_offset: 0, message: "" }], active: true })}>
        + New campaign
      </button>
    </div>
  );
}

function TeamCard() {
  const [team, setTeam] = useState(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("agent");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  // Invite links arrive as /settings?invite=<token> (owner shares it manually).
  const [token, setToken] = useState(() => new URLSearchParams(window.location.search).get("invite") || "");

  const load = () =>
    api("/api/team")
      .then((b) => setTeam(b))
      .catch((e) => setError(e instanceof Error ? e.message.replace(/^API \d+: /, "") : "Team load failed."));

  useEffect(() => {
    load();
  }, []);

  const manage = team && (team.my_role === "owner" || team.my_role === "admin");

  const doInvite = async () => {
    setMsg("");
    setError("");
    if (!email.trim()) return;
    try {
      const b = await api("/api/team/invite", {
        method: "POST",
        body: JSON.stringify({ email, role }),
      });
      setMsg(`Invite ready for ${b.member.email}. No email is sent — copy the link and share it yourself.`);
      setEmail("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message.replace(/^API \d+: /, "") : "Invite failed.");
    }
  };

  const copyLink = (path) => {
    const full = `${window.location.origin}${path}`;
    const el = document.createElement("textarea");
    el.value = full;
    document.body.appendChild(el);
    el.select();
    let copied = false;
    try {
      copied = document.execCommand("copy");
    } catch {
      copied = false;
    }
    document.body.removeChild(el);
    setMsg(copied ? "Invite link copied." : `Copy this link yourself: ${full}`);
  };

  const changeRole = async (id, nextRole) => {
    setError("");
    try {
      await api(`/api/team/${id}`, { method: "PATCH", body: JSON.stringify({ role: nextRole }) });
      setMsg("Role updated. It applies on the member's next request.");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message.replace(/^API \d+: /, "") : "Role update failed.");
    }
  };

  const removeMember = async (id) => {
    setError("");
    try {
      await api(`/api/team/${id}`, { method: "DELETE" });
      setMsg("Member removed. They fall back to their own workspace.");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message.replace(/^API \d+: /, "") : "Remove failed.");
    }
  };

  const join = async () => {
    setMsg("");
    setError("");
    try {
      await api("/api/team/accept", { method: "POST", body: JSON.stringify({ token }) });
      const me = await api("/api/auth/me");
      setSession(getToken(), me.user);
      window.location.href = "/";
    } catch (e) {
      setError(e instanceof Error ? e.message.replace(/^API \d+: /, "") : "Join failed.");
    }
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-3">
      <h3 className="font-semibold">Team &amp; roles</h3>
      {!team ? (
        <p className="text-xs text-slate-500">Loading team…</p>
      ) : (
        <>
          <p className="text-xs text-slate-400">
            {team.workspace.business_name} · your role: <b className="text-slate-200">{team.my_role}</b>
          </p>
          <div className="rounded border border-slate-800 divide-y divide-slate-800 text-xs">
            <div className="flex items-center justify-between px-2 py-1.5">
              <span className="text-slate-200">{team.owner.email}</span>
              <span className="rounded bg-sky-900 px-2 py-0.5 text-sky-200">owner</span>
            </div>
            {team.members.map((m) => (
              <div key={m.id} className="px-2 py-1.5 space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <span className={m.status === "removed" ? "text-slate-500 line-through" : "text-slate-200"}>
                    {m.email}
                  </span>
                  {manage && m.status !== "removed" ? (
                    <span className="flex items-center gap-2">
                      <select
                        className="rounded bg-slate-800 px-2 py-0.5"
                        value={m.role}
                        onChange={(e) => changeRole(m.id, e.target.value)}
                      >
                        {["admin", "manager", "agent", "viewer"].map((r) => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                      </select>
                      <button className="text-rose-300 hover:text-rose-200" onClick={() => removeMember(m.id)}>
                        Remove
                      </button>
                    </span>
                  ) : (
                    <span className="rounded bg-slate-800 px-2 py-0.5 text-slate-300">{m.role}</span>
                  )}
                </div>
                <p className="text-slate-500">
                  {m.status}
                  {m.invite_path && (
                    <>
                      {" · "}
                      <button className="text-sky-300 hover:text-sky-200" onClick={() => copyLink(m.invite_path)}>
                        Copy invite link
                      </button>
                    </>
                  )}
                </p>
              </div>
            ))}
          </div>
          {manage && (
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-xs text-slate-400">
                Invite by email
                <input
                  className="mt-1 block w-56 rounded bg-slate-800 px-2 py-1 text-sm"
                  type="email"
                  placeholder="teammate@business.pk"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </label>
              <select
                className="rounded bg-slate-800 px-2 py-1 text-sm"
                value={role}
                onChange={(e) => setRole(e.target.value)}
              >
                {["admin", "manager", "agent", "viewer"].map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
              <button className="rounded bg-sky-600 px-3 py-1.5 text-sm font-semibold hover:bg-sky-500" onClick={doInvite}>
                Create invite
              </button>
            </div>
          )}
          <div className="flex flex-wrap items-end gap-2 pt-1">
            {team.my_role === "owner" && (
              <>
                <label className="text-xs text-slate-400">
                  Join a workspace (invite token)
                  <input
                    className="mt-1 block w-72 rounded bg-slate-800 px-2 py-1 font-mono text-xs"
                    placeholder="paste the token from your invite link"
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                  />
                </label>
                <button className="rounded bg-emerald-800 px-3 py-1.5 text-sm hover:bg-emerald-700" onClick={join} disabled={!token.trim()}>
                  Join workspace
                </button>
              </>
            )}
          </div>
          {msg && <p className="text-xs text-emerald-400">{msg}</p>}
          {error && <p className="text-xs text-rose-400">{error}</p>}
          <p className="text-[11px] text-slate-500">
            Owner/admin: everything + team · manager: everything except team · agent: leads &amp; conversations,
            no business settings · viewer: read-only. {team.seats_note} Invites are single-use links —
            the platform never sends email, and an account that already owns leads cannot join.
          </p>
        </>
      )}
    </div>
  );
}

function BillingCard() {
  const [data, setData] = useState(null);
  const [denied, setDenied] = useState(false);
  const [plan, setPlan] = useState("");
  const [form, setForm] = useState({
    amount: "", currency: "PKR", period_start: "", period_end: "", paid_until: "", note: "",
  });
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const load = () =>
    api("/api/billing")
      .then((b) => {
        setData(b);
        setPlan(b.plan_tier);
      })
      .catch((e) => {
        if (e.status === 403) setDenied(true);
        else setError(e instanceof Error ? e.message.replace(/^API \d+: /, "") : "Billing load failed.");
      });

  useEffect(() => {
    load();
  }, []);

  const addEntry = async () => {
    setMsg("");
    setError("");
    if (!form.amount) return;
    try {
      await api("/api/billing", {
        method: "POST",
        body: JSON.stringify({
          amount: Number(form.amount),
          currency: form.currency || "PKR",
          period_start: form.period_start || null,
          period_end: form.period_end || null,
          paid_until: form.paid_until || null,
          note: form.note,
        }),
      });
      setMsg("Recorded. No payment is processed by the platform.");
      setForm({ amount: "", currency: form.currency || "PKR", period_start: "", period_end: "", paid_until: "", note: "" });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message.replace(/^API \d+: /, "") : "Could not record the payment.");
    }
  };

  const removeEntry = async (id) => {
    setError("");
    try {
      await api(`/api/billing/${id}`, { method: "DELETE" });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message.replace(/^API \d+: /, "") : "Delete failed.");
    }
  };

  const savePlan = async () => {
    setMsg("");
    setError("");
    try {
      const b = await api("/api/billing/plan", { method: "PATCH", body: JSON.stringify({ plan_tier: plan }) });
      setMsg(b.note);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message.replace(/^API \d+: /, "") : "Plan update failed.");
    }
  };

  if (denied) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
        <h3 className="font-semibold">Billing ledger</h3>
        <p className="mt-1 text-xs text-slate-500">Owner or admin role required. Nothing is charged by the platform.</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-3">
      <h3 className="font-semibold">Billing ledger (manual)</h3>
      <p className="text-xs text-slate-500">
        Record what was actually paid. There is no payment gateway, no card data and no auto-charging; totals are
        grouped per currency with no conversion.
      </p>
      {!data ? (
        <p className="text-xs text-slate-500">Loading ledger…</p>
      ) : (
        <>
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-xs text-slate-400">
              Plan label
              <select
                className="mt-1 block rounded bg-slate-800 px-2 py-1 text-sm"
                value={plan}
                onChange={(e) => setPlan(e.target.value)}
              >
                {(data.plan_tiers || []).map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
            <button className="rounded bg-slate-800 px-3 py-1.5 text-sm hover:bg-slate-700" onClick={savePlan}>
              Save plan label
            </button>
            <span className="text-[11px] text-slate-500">Current: {data.plan_tier}</span>
          </div>

          {data.entries.length === 0 ? (
            <p className="text-xs text-slate-500">No payments recorded yet.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="text-slate-500">
                <tr>
                  <th className="text-left font-normal pb-1">Recorded</th>
                  <th className="text-right font-normal pb-1">Amount</th>
                  <th className="text-left font-normal pb-1 pl-2">Period</th>
                  <th className="text-left font-normal pb-1 pl-2">Paid until</th>
                  <th className="text-left font-normal pb-1 pl-2">Note</th>
                  <th className="pb-1" />
                </tr>
              </thead>
              <tbody>
                {data.entries.map((e) => (
                  <tr key={e.id} className="border-t border-slate-800">
                    <td className="py-1 text-slate-400">{e.created_at ? new Date(e.created_at).toLocaleDateString() : ""}</td>
                    <td className="py-1 text-right">{e.amount} {e.currency}</td>
                    <td className="py-1 pl-2 text-slate-400">
                      {e.period_start || "?"} → {e.period_end || "?"}
                    </td>
                    <td className="py-1 pl-2 text-slate-400">{e.paid_until || "—"}</td>
                    <td className="py-1 pl-2 text-slate-400">{e.note || "—"}</td>
                    <td className="py-1 text-right">
                      <button className="text-rose-300 hover:text-rose-200" onClick={() => removeEntry(e.id)}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <div className="rounded border border-slate-800 p-2 space-y-2">
            <p className="text-xs text-slate-400">Record a payment</p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
              <label className="text-slate-400">
                Amount
                <input
                  type="number" min="0" step="0.01"
                  className="mt-1 block w-full rounded bg-slate-800 px-2 py-1"
                  value={form.amount}
                  onChange={(e) => setForm({ ...form, amount: e.target.value })}
                />
              </label>
              <label className="text-slate-400">
                Currency
                <input
                  className="mt-1 block w-full rounded bg-slate-800 px-2 py-1"
                  value={form.currency}
                  onChange={(e) => setForm({ ...form, currency: e.target.value })}
                />
              </label>
              <label className="text-slate-400">
                Paid until
                <input
                  type="date"
                  className="mt-1 block w-full rounded bg-slate-800 px-2 py-1"
                  value={form.paid_until}
                  onChange={(e) => setForm({ ...form, paid_until: e.target.value })}
                />
              </label>
              <label className="text-slate-400">
                Period start
                <input
                  type="date"
                  className="mt-1 block w-full rounded bg-slate-800 px-2 py-1"
                  value={form.period_start}
                  onChange={(e) => setForm({ ...form, period_start: e.target.value })}
                />
              </label>
              <label className="text-slate-400">
                Period end
                <input
                  type="date"
                  className="mt-1 block w-full rounded bg-slate-800 px-2 py-1"
                  value={form.period_end}
                  onChange={(e) => setForm({ ...form, period_end: e.target.value })}
                />
              </label>
              <label className="text-slate-400">
                Note
                <input
                  className="mt-1 block w-full rounded bg-slate-800 px-2 py-1"
                  placeholder="cash / bank transfer"
                  value={form.note}
                  onChange={(e) => setForm({ ...form, note: e.target.value })}
                />
              </label>
            </div>
            <button className="rounded bg-emerald-800 px-3 py-1.5 text-sm hover:bg-emerald-700" onClick={addEntry}>
              Record payment
            </button>
          </div>

          {data.entry_count > 0 && (
            <p className="text-xs text-slate-300">
              Recorded total:{" "}
              {Object.entries(data.totals_by_currency).map(([cur, total]) => `${total} ${cur}`).join(" · ")}
              {data.latest_paid_until && <span className="text-slate-500"> · paid until {data.latest_paid_until}</span>}
            </p>
          )}
          {msg && <p className="text-xs text-emerald-400">{msg}</p>}
          {error && <p className="text-xs text-rose-400">{error}</p>}
          <ul className="list-disc list-inside text-[11px] text-slate-500 space-y-0.5">
            {data.notes.map((n) => (<li key={n}>{n}</li>))}
          </ul>
        </>
      )}
    </div>
  );
}

function IntegrationsCard() {
  const [integrations, setIntegrations] = useState(null);
  const [events, setEvents] = useState([]);
  const [retryable, setRetryable] = useState([]);
  const [pageId, setPageId] = useState("");
  const [phoneId, setPhoneId] = useState("");
  const [denied, setDenied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const clean = (e, fallback) =>
    e instanceof Error ? e.message.replace(/^API \d+: /, "") : fallback;

  const load = async () => {
    try {
      const s = await api("/api/settings");
      const i = s.settings.integrations;
      setIntegrations(i);
      setPageId(i.meta_page_id || "");
      setPhoneId(i.whatsapp_phone_number_id || "");
    } catch (e) {
      setError(clean(e, "Settings load failed."));
    }
    try {
      const ev = await api("/api/integrations/events?limit=20");
      setEvents(ev.events || []);
      setRetryable(ev.retryable_statuses || []);
    } catch (e) {
      if (e.status === 403) setDenied(true);
      else setError(clean(e, "Event log load failed."));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    setBusy(true);
    setMsg("");
    setError("");
    try {
      const s = await api("/api/settings", {
        method: "PATCH",
        body: JSON.stringify({ meta_page_id: pageId, whatsapp_phone_number_id: phoneId }),
      });
      setIntegrations(s.settings.integrations);
      setMsg("Routing ids saved.");
      load();
    } catch (e) {
      setError(clean(e, "Could not save the ids."));
    } finally {
      setBusy(false);
    }
  };

  const retry = async (id) => {
    setMsg("");
    setError("");
    try {
      const r = await api(`/api/integrations/events/${id}/retry`, { method: "POST" });
      setMsg(`Retry recorded: ${r.event.status}.`);
      load();
    } catch (e) {
      setError(clean(e, "Retry failed."));
    }
  };

  const chip = (ok, label) => (
    <span
      className={`rounded-full px-2 py-0.5 text-[11px] ${
        ok ? "bg-emerald-900 text-emerald-300" : "bg-slate-800 text-slate-400"
      }`}
    >
      {label}
    </span>
  );

  const statusColor = (status) =>
    ({
      processed: "text-emerald-300",
      received: "text-slate-300",
      ignored: "text-slate-400",
      unrouted: "text-amber-300",
      pending_credentials: "text-amber-300",
      error: "text-rose-300",
    }[status] || "text-slate-400");

  if (!integrations && !error) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
        <h3 className="font-semibold">Integrations</h3>
        <p className="mt-1 text-xs text-slate-500">Loading webhook status…</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
      <h3 className="font-semibold">Integrations — inbound capture</h3>
      <p className="text-xs text-slate-500">
        Meta Lead Ads and WhatsApp inbound. Inbound only: the platform records what the contact sent and never
        auto-replies. Webhooks answer 503 until the server App Secret is configured.
      </p>

      {integrations && (
        <>
          <div className="flex flex-wrap gap-2">
            {chip(integrations.meta_app_secret_configured, "App secret")}
            {chip(integrations.meta_verify_token_configured, "Verify token")}
            {chip(integrations.meta_page_access_token_configured, "Page token")}
            {chip(integrations.meta_ready, integrations.meta_ready ? "Meta Lead Ads ready" : "Meta Lead Ads not ready")}
            {chip(
              integrations.whatsapp_ready,
              integrations.whatsapp_ready ? "WhatsApp inbound ready" : "WhatsApp inbound not ready"
            )}
          </div>

          <div className="space-y-1 text-[11px] text-slate-500">
            <p>
              Meta webhook URL: <code className="select-all text-slate-300">{apiBaseUrl()}{integrations.meta_webhook_url}</code>
            </p>
            <p>
              WhatsApp webhook URL:{" "}
              <code className="select-all text-slate-300">{apiBaseUrl()}{integrations.whatsapp_webhook_url}</code>
            </p>
            <p>{integrations.credentials_note}</p>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <label className="text-xs text-slate-400">
              Meta Page ID (Lead Ads)
              <input
                className="mt-1 block w-full rounded bg-slate-800 px-2 py-1 text-sm text-slate-100"
                placeholder="numeric page id"
                value={pageId}
                onChange={(e) => setPageId(e.target.value)}
              />
            </label>
            <label className="text-xs text-slate-400">
              WhatsApp phone number ID (Cloud API)
              <input
                className="mt-1 block w-full rounded bg-slate-800 px-2 py-1 text-sm text-slate-100"
                placeholder="numeric phone number id"
                value={phoneId}
                onChange={(e) => setPhoneId(e.target.value)}
              />
            </label>
          </div>
          <p className="text-[11px] text-slate-500">
            These ids route deliveries to this workspace. An id that belongs to no workspace is stored as “unrouted”
            — never assigned to someone else. Server credentials stay in environment variables and are never shown
            here.
          </p>
          <button
            className="rounded bg-slate-800 px-3 py-1.5 text-sm hover:bg-slate-700 disabled:opacity-50"
            onClick={save}
            disabled={busy}
          >
            Save integration ids
          </button>
          {msg && <p className="text-xs text-emerald-400">{msg}</p>}
          {error && <p className="text-xs text-rose-400">{error}</p>}
          <ul className="list-disc list-inside text-[11px] text-slate-500 space-y-0.5">
            {(integrations.notes || []).map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </>
      )}

      <div className="space-y-2">
        <p className="text-xs font-semibold text-slate-300">Recent webhook deliveries</p>
        {denied ? (
          <p className="text-xs text-slate-500">
            Event log is owner/admin only — deliveries can contain contact details.
          </p>
        ) : events.length === 0 ? (
          <p className="text-xs text-slate-500">No deliveries recorded yet.</p>
        ) : (
          <table className="w-full text-[11px]">
            <thead className="text-slate-500">
              <tr>
                <th className="text-left font-normal pb-1">Received</th>
                <th className="text-left font-normal pb-1 pl-2">Source</th>
                <th className="text-left font-normal pb-1 pl-2">Status</th>
                <th className="text-left font-normal pb-1 pl-2">Lead</th>
                <th className="text-left font-normal pb-1 pl-2">Detail</th>
                <th className="pb-1" />
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id} className="border-t border-slate-800">
                  <td className="py-1 text-slate-400">
                    {e.received_at ? new Date(e.received_at).toLocaleString() : ""}
                  </td>
                  <td className="py-1 pl-2 text-slate-400">{e.source}</td>
                  <td className={`py-1 pl-2 ${statusColor(e.status)}`}>{e.status}</td>
                  <td className="py-1 pl-2 text-slate-400">{e.lead_id ?? "—"}</td>
                  <td className="py-1 pl-2 text-slate-500">{e.error || "—"}</td>
                  <td className="py-1 text-right">
                    {retryable.includes(e.status) && (
                      <button className="text-sky-300 hover:text-sky-200" onClick={() => retry(e.id)}>
                        Retry
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function SettingsPanel({ user, onLogout }) {
  const [settings, setSettings] = useState({ niche: "", target_area: "", brand_voice: "", landing_slug: null, show_property_fields: false, business_type: "", brand_name: "", logo_url: "", primary_color: "", support_email: "", footer_text: "", hide_platform_brand: false });
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
        brand_name: settings.brand_name,
        logo_url: settings.logo_url,
        primary_color: settings.primary_color,
        support_email: settings.support_email,
        footer_text: settings.footer_text,
        hide_platform_brand: settings.hide_platform_brand,
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
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
        <h3 className="font-semibold">White-label branding</h3>
        <p className="text-xs text-slate-500">
          Presentation only — no custom domain, no plan enforcement. Applies to your dashboard header and public
          landing page.
        </p>
        {field("brand_name", "Brand name (plain text — use Logo URL below for the image)")}
        {/^(https?:\/\/|\/\/|\/)/i.test((settings.brand_name || "").trim()) && (
          <p className="text-xs text-amber-400">
            This looks like a URL. Brand name is text; paste the image link into Logo URL instead.
          </p>
        )}
        {field("logo_url", "Logo URL (https://… or /path)")}
        <div className="space-y-1">
          <label className="block text-sm">
            Primary colour
            <div className="mt-1 flex gap-2 items-center">
              <input
                className="flex-1 rounded-lg bg-slate-800 px-3 py-2"
                placeholder="#0ea5e9 (leave empty for the default theme)"
                value={settings.primary_color}
                onChange={(e) => setSettings({ ...settings, primary_color: e.target.value })}
              />
              <input
                type="color"
                className="h-9 w-12 rounded bg-slate-800"
                value={/^#[0-9a-fA-F]{6}$/.test(settings.primary_color) ? settings.primary_color : "#0ea5e9"}
                onChange={(e) => setSettings({ ...settings, primary_color: e.target.value })}
              />
            </div>
          </label>
        </div>
        {field("support_email", "Support email (shown on the landing page)")}
        {field("footer_text", "Footer text (landing page)", true)}
        <label className="block text-sm">
          <span className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={settings.hide_platform_brand}
              onChange={(e) => setSettings({ ...settings, hide_platform_brand: e.target.checked })}
            />
            Hide the LeadCraft AI brand (dashboard header + landing footer)
          </span>
        </label>
        <button className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold hover:bg-sky-500" onClick={save}>
          Save branding
        </button>
        <p className="text-[11px] text-slate-500">
          Both Save buttons write the same settings record. Roles: owner/admin/manager only — agents and viewers
          cannot change business settings.
        </p>
      </div>
      <IntegrationsCard />
      <TeamCard />
      <BillingCard />
      <OpsCard />
      <IcpEditor />
      <AbEditor />
      <PagesEditor />
      <NurtureEditor />
      <button className="text-sm text-red-400 hover:text-red-300" onClick={onLogout}>
        Log out
      </button>
    </div>
  );
}

// P7 #1: public renderer for an owner-built page (/p/<slug>). Blocks are plain
// strings validated server-side; React escapes every value, so no markup is
// ever interpreted. The capture form posts to the same consent-first endpoint
// with page_slug.
function BlockPage({ slug }) {
  const [config, setConfig] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [form, setForm] = useState({ name: "", phone: "", email: "", message: "" });
  const [consent, setConsent] = useState(false);
  const [company, setCompany] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [formError, setFormError] = useState("");
  // P7 #2: first-party, cookie-free analytics for this custom page.
  const [formStarted, setFormStarted] = useState(false);

  const track = (eventName) => {
    try {
      let sid = sessionStorage.getItem("lc_sid") || "";
      if (!sid) {
        sid = (typeof crypto !== "undefined" && crypto.randomUUID
          ? crypto.randomUUID()
          : `${Date.now()}${Math.random().toString(36).slice(2)}`
        )
          .replace(/[^A-Za-z0-9_-]/g, "")
          .slice(0, 64);
        sessionStorage.setItem("lc_sid", sid);
      }
      // The server forces path=/p/<slug>; only the event and host are used.
      api(`/api/public/pages/${encodeURIComponent(slug)}/events`, {
        method: "POST",
        body: JSON.stringify({ session_id: sid, event: eventName, referrer: document.referrer || "" }),
      }).catch(() => {});
    } catch {
      /* private mode: analytics just isn't recorded */
    }
  };

  // Same attribution contract as /l/<slug>: share-link params only.
  const attribution = (() => {
    const p = new URLSearchParams(window.location.search);
    const get = (k) => (p.get(k) || "").slice(0, 200);
    return {
      campaign: get("campaign") || get("utm_campaign"),
      utm_source: get("utm_source"),
      utm_medium: get("utm_medium"),
      utm_content: get("utm_content"),
      utm_term: get("utm_term"),
      referral_code: (p.get("ref") || "").slice(0, 32),
    };
  })();

  useEffect(() => {
    api(`/api/public/pages/${encodeURIComponent(slug)}`)
      .then((cfg) => {
        setConfig(cfg);
        document.title = cfg.title || cfg.business?.name || "Landing page";
        track("page_view");
      })
      .catch((err) => setLoadError(err.message.replace(/^API \d+: /, "")));
  }, [slug]);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setFormError("");
    try {
      await api("/api/leads/capture", {
        method: "POST",
        body: JSON.stringify({
          page_slug: slug,
          name: form.name,
          phone: form.phone,
          email: form.email,
          intent_notes: form.message,
          ...attribution,
          company,
          consent,
        }),
      });
      setDone(true);
      track("submit");
    } catch (err) {
      setFormError(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Submission failed.");
    } finally {
      setBusy(false);
    }
  };

  if (!config && !loadError) {
    return <div className="min-h-screen flex items-center justify-center text-slate-400 text-sm">Loading…</div>;
  }
  if (!config) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4 text-center">
        <div>
          <h1 className="text-xl font-bold mb-2">Page not found</h1>
          <p className="text-sm text-slate-400">{loadError || "This page does not exist or is not published yet."}</p>
        </div>
      </div>
    );
  }

  const business = config.business || {};
  const brand = displayBrandName(business.brand_name, business.name, config.title || "this business");
  const accent = /^#[0-9a-fA-F]{6}$/.test(business.primary_color || "") ? business.primary_color : "";
  const footer = business.footer_text || (business.hide_platform_brand ? "" : "Powered by LeadCraft AI");
  const goCapture = () => {
    const el = document.getElementById("capture");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const ctaButton = (label, full = false) =>
    label ? (
      <button
        type="button"
        onClick={goCapture}
        className={`rounded-lg px-5 py-2 text-sm font-semibold text-white hover:opacity-90 ${full ? "w-full" : ""}`}
        style={{ backgroundColor: accent || "#0284c7" }}
      >
        {label}
      </button>
    ) : null;

  const renderBlock = (block, index) => {
    switch (block.type) {
      case "hero":
        return (
          <section key={index} className="space-y-4 py-10 text-center">
            {block.image_url && (
              <img src={block.image_url} alt="" className="mx-auto max-h-64 rounded-xl object-cover" />
            )}
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">{block.heading}</h1>
            {block.subheading && <p className="mx-auto max-w-2xl text-base text-slate-300 whitespace-pre-line">{block.subheading}</p>}
            {ctaButton(block.cta_label || "Get in touch")}
          </section>
        );
      case "text":
        return (
          <section key={index} className="space-y-2 py-4">
            {block.heading && <h2 className="text-2xl font-bold">{block.heading}</h2>}
            <p className="text-sm leading-6 text-slate-300 whitespace-pre-line">{block.body}</p>
          </section>
        );
      case "features":
        return (
          <section key={index} className="space-y-4 py-4">
            {block.heading && <h2 className="text-2xl font-bold">{block.heading}</h2>}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {block.items.map((item, j) => (
                <div key={j} className="rounded-xl border border-slate-800 bg-slate-900 p-4">
                  <h3 className="font-semibold">{item.title}</h3>
                  {item.body && <p className="mt-1 text-sm text-slate-400 whitespace-pre-line">{item.body}</p>}
                </div>
              ))}
            </div>
          </section>
        );
      case "testimonial":
        return (
          <section key={index} className="py-4">
            <blockquote className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <p className="text-base italic text-slate-200 whitespace-pre-line">“{block.quote}”</p>
              <footer className="mt-3 text-sm text-slate-400">
                — {block.author}
                {block.role ? `, ${block.role}` : ""}
              </footer>
            </blockquote>
          </section>
        );
      case "faq":
        return (
          <section key={index} className="space-y-3 py-4">
            {block.heading && <h2 className="text-2xl font-bold">{block.heading}</h2>}
            {block.items.map((item, j) => (
              <details key={j} className="rounded-xl border border-slate-800 bg-slate-900 p-4">
                <summary className="cursor-pointer text-sm font-semibold">{item.question}</summary>
                <p className="mt-2 text-sm text-slate-400 whitespace-pre-line">{item.answer}</p>
              </details>
            ))}
          </section>
        );
      case "cta":
        return (
          <section key={index} className="my-6 rounded-xl border border-slate-800 bg-slate-900 p-6 text-center space-y-3">
            <h2 className="text-2xl font-bold">{block.heading}</h2>
            {block.body && <p className="text-sm text-slate-300 whitespace-pre-line">{block.body}</p>}
            {ctaButton(block.button_label || "Request a callback")}
          </section>
        );
      default:
        return null;
    }
  };

  const field = (key, label, placeholder, type = "text", required = false) => (
    <label className="block text-sm">
      {label}
      <input
        className="mt-1 block w-full rounded-lg bg-slate-800 px-3 py-2"
        type={type}
        placeholder={placeholder}
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        required={required}
      />
    </label>
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-3xl px-4 pb-12">
        <header className="flex items-center justify-between gap-3 py-4">
          <div className="flex items-center gap-2">
            {business.logo_url && (
              <img src={business.logo_url} alt={brand} className="h-8 w-auto max-w-[10rem] rounded object-contain" />
            )}
            <span className="text-sm font-semibold">{brand}</span>
          </div>
          {business.support_email && (
            <a className="text-xs text-slate-400 underline" href={`mailto:${business.support_email}`}>
              {business.support_email}
            </a>
          )}
        </header>
        {Array.isArray(config.blocks) && config.blocks.map(renderBlock)}

        <section id="capture" className="mt-8 rounded-2xl border border-slate-800 bg-slate-900 p-6 space-y-3">
          {done ? (
            <div className="space-y-2 py-6 text-center">
              <div className="text-4xl">✅</div>
              <h2 className="text-xl font-bold">Thank you, {form.name.split(" ")[0]}!</h2>
              <p className="text-sm text-slate-400">{brand} has received your request and will reach out soon.</p>
            </div>
          ) : (
            <>
              <h2 className="text-xl font-bold">Get in touch</h2>
              <p className="text-sm text-slate-400">
                Leave your details and {brand} will contact you. The platform does not send automated messages.
              </p>
              <form
                onSubmit={submit}
                className="space-y-3"
                onFocus={() => {
                  if (!formStarted) {
                    setFormStarted(true);
                    track("form_start");
                  }
                }}
              >
                {field("name", "Your name", "Ayesha Khan", "text", true)}
                {field("phone", "Phone", "0300 1234567")}
                {field("email", "Email (optional)", "you@example.com", "email")}
                <label className="block text-sm">
                  Anything we should know? (optional)
                  <textarea
                    className="mt-1 block w-full rounded-lg bg-slate-800 px-3 py-2"
                    rows={2}
                    value={form.message}
                    onChange={(e) => setForm({ ...form, message: e.target.value })}
                  />
                </label>
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
                  <span>I agree to be contacted about my enquiry. My details are stored so {brand} can reply.</span>
                </label>
                {formError && <p className="text-xs text-red-400">{formError}</p>}
                <button
                  type="submit"
                  className="w-full rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60"
                  style={{ backgroundColor: accent || "#0284c7" }}
                  disabled={busy}
                >
                  {busy ? "Sending…" : "Request a callback"}
                </button>
                <p className="text-[10px] text-slate-500">
                  Provide a phone number or email so the business can reply. Consent is recorded server-side.
                </p>
              </form>
            </>
          )}
        </section>

        {(footer || business.support_email) && (
          <footer className="mt-8 space-y-1 text-center text-xs text-slate-500">
            {footer && <p>{footer}</p>}
            {business.support_email && <p>{business.support_email}</p>}
          </footer>
        )}
      </div>
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
      referral_code: (p.get("ref") || "").slice(0, 32),
    };
  })();

  // First-party analytics (P1 #4): cookie-free session id in sessionStorage.
  const track = (event) => {
    try {
      let sid = sessionStorage.getItem("lc_sid") || "";
      if (!sid) {
        sid = (typeof crypto !== "undefined" && crypto.randomUUID
          ? crypto.randomUUID()
          : `${Date.now()}${Math.random().toString(36).slice(2)}`
        )
          .replace(/[^A-Za-z0-9_-]/g, "")
          .slice(0, 64);
        sessionStorage.setItem("lc_sid", sid);
      }
      api(`/api/public/landing/${encodeURIComponent(slug)}/events`, {
        method: "POST",
        body: JSON.stringify({
          session_id: sid,
          event,
          path: window.location.pathname,
          referrer: document.referrer || "",
        }),
      }).catch(() => {});
    } catch {
      /* private mode: analytics just isn't recorded */
    }
  };
  const [formStarted, setFormStarted] = useState(false);

  useEffect(() => {
    // A/B arm persistence: the visitor keeps the same arm across reloads via
    // their own localStorage (no cookies). First visit -> server assigns.
    const key = `lc_ab_${slug}`;
    let stored = "";
    try {
      stored = localStorage.getItem(key) || "";
    } catch {
      stored = "";
    }
    const q = stored ? `?variant=${encodeURIComponent(stored)}` : "";
    api(`/api/public/landing/${encodeURIComponent(slug)}${q}`)
      .then((cfg) => {
        setConfig(cfg);
        try {
          localStorage.setItem(key, cfg.ab_variant || "control");
        } catch {
          /* private mode: arm just isn't sticky */
        }
        // First-party impression (no PII, no cookies).
        api(`/api/public/landing/${encodeURIComponent(slug)}/impression`, {
          method: "POST",
          body: JSON.stringify({ variant: cfg.ab_variant || "control" }),
        }).catch(() => {});
        track("page_view");
      })
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
          landing_variant: config.ab_variant || "control",
          company,
          consent,
        }),
      });
      track("submit");
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Submission failed.");
    } finally {
      setBusy(false);
    }
  };

  // P5 #1 booking widget. Slots come from the server (business timezone);
  // the browser only picks a date and one of the returned starts.
  const [mode, setMode] = useState("request");
  const [bookingDate, setBookingDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    return d.toISOString().slice(0, 10);
  });
  const [slots, setSlots] = useState([]);
  const [slotLoading, setSlotLoading] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [bookingForm, setBookingForm] = useState({ name: "", phone: "", email: "", service: "", intent_notes: "" });
  const [bookingConsent, setBookingConsent] = useState(false);
  const [bookingDone, setBookingDone] = useState(null);
  const [bookingError, setBookingError] = useState("");

  useEffect(() => {
    if (mode !== "book" || !config?.booking?.enabled || !bookingDate) return;
    setSlotLoading(true);
    setSelectedSlot(null);
    api(`/api/public/landing/${encodeURIComponent(slug)}/slots?date=${encodeURIComponent(bookingDate)}`)
      .then((b) => setSlots(b.slots || []))
      .catch(() => setSlots([]))
      .finally(() => setSlotLoading(false));
  }, [mode, bookingDate, slug, config]);

  const submitBooking = async (e) => {
    e.preventDefault();
    if (!selectedSlot) {
      setBookingError("Pick an available time slot first.");
      return;
    }
    setBusy(true);
    setBookingError("");
    try {
      const b = await api(`/api/public/landing/${encodeURIComponent(slug)}/book`, {
        method: "POST",
        body: JSON.stringify({
          ...bookingForm,
          starts_at: selectedSlot.starts_at,
          consent: bookingConsent,
          company,
        }),
      });
      track("submit");
      setBookingDone(b);
      setSlots((list) => list.filter((s) => s.starts_at !== selectedSlot.starts_at));
    } catch (err) {
      setBookingError(
        err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Booking failed. Please try another slot."
      );
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

  const brand = displayBrandName(config.brand_name, config.business_name);
  const accent = /^#[0-9a-fA-F]{6}$/.test(config.primary_color || "") ? config.primary_color : "";
  const footer = config.footer_text || (config.hide_platform_brand ? "" : "Powered by LeadCraft AI");

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md rounded-xl border border-slate-800 bg-slate-900 p-6">
        {done ? (
          <div className="text-center space-y-3 py-6">
            <div className="text-4xl">✅</div>
            <h1 className="text-xl font-bold">Thank you, {form.name.split(" ")[0]}!</h1>
            <p className="text-sm text-slate-400">
              {brand} has received your request and will reach out soon.
            </p>
          </div>
        ) : mode === "book" && config.booking?.enabled ? (
          bookingDone ? (
            <div className="text-center space-y-3 py-6">
              <div className="text-4xl">📅</div>
              <h1 className="text-xl font-bold">Appointment requested</h1>
              <p className="text-sm text-slate-200">{bookingDone.appointment.label}</p>
              {bookingDone.appointment.service && (
                <p className="text-xs text-slate-400">{bookingDone.appointment.service}</p>
              )}
              <p className="text-sm text-slate-400">{bookingDone.message}</p>
              <button
                type="button"
                className="text-xs text-slate-400 underline"
                onClick={() => {
                  setBookingDone(null);
                  setSelectedSlot(null);
                  setBookingConsent(false);
                  track("form_start");
                }}
              >
                Book another time
              </button>
            </div>
          ) : (
            <form onSubmit={submitBooking} className="space-y-4">
              <div>
                <button
                  type="button"
                  className="text-xs text-slate-400 underline"
                  onClick={() => setMode("request")}
                >
                  ← Request a callback instead
                </button>
                <h1 className="mt-2 text-2xl font-bold">Book an appointment</h1>
                <p className="text-sm text-slate-400">
                  {config.booking.note || `${brand} · pick a time that suits you`}
                </p>
                <p className="mt-1 text-[10px] text-slate-500">
                  Times are in {config.booking.timezone}; the business confirms your request personally.
                </p>
              </div>
              <label className="block text-sm">
                Date
                <input
                  type="date"
                  className="mt-1 block w-full rounded-lg bg-slate-800 px-3 py-2"
                  value={bookingDate}
                  min={new Date().toISOString().slice(0, 10)}
                  onChange={(e) => setBookingDate(e.target.value)}
                />
              </label>
              <div>
                <p className="text-sm mb-1">Available times</p>
                {slotLoading ? (
                  <p className="text-xs text-slate-500">Loading slots…</p>
                ) : slots.length === 0 ? (
                  <p className="text-xs text-slate-500">No slots on this day — try another date.</p>
                ) : (
                  <div className="grid grid-cols-3 gap-1">
                    {slots.map((s) => {
                      const selected = selectedSlot?.starts_at === s.starts_at;
                      return (
                        <button
                          key={s.starts_at}
                          type="button"
                          className={`rounded px-2 py-1 text-xs ${selected ? "text-white" : "bg-slate-800 text-slate-200"}`}
                          style={selected ? { backgroundColor: accent || "#0284c7" } : undefined}
                          onClick={() => setSelectedSlot(s)}
                        >
                          {s.label}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
              {(config.booking.services || []).length > 0 && (
                <label className="block text-sm">
                  Service
                  <select
                    className="mt-1 block w-full rounded-lg bg-slate-800 px-3 py-2"
                    value={bookingForm.service}
                    onChange={(e) => setBookingForm({ ...bookingForm, service: e.target.value })}
                  >
                    <option value="">—</option>
                    {config.booking.services.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </label>
              )}
              <label className="block text-sm">
                Your name
                <input
                  className="mt-1 block w-full rounded-lg bg-slate-800 px-3 py-2"
                  value={bookingForm.name}
                  onChange={(e) => setBookingForm({ ...bookingForm, name: e.target.value })}
                  required
                />
              </label>
              <label className="block text-sm">
                Phone
                <input
                  className="mt-1 block w-full rounded-lg bg-slate-800 px-3 py-2"
                  value={bookingForm.phone}
                  onChange={(e) => setBookingForm({ ...bookingForm, phone: e.target.value })}
                />
              </label>
              <label className="block text-sm">
                Email (optional)
                <input
                  type="email"
                  className="mt-1 block w-full rounded-lg bg-slate-800 px-3 py-2"
                  value={bookingForm.email}
                  onChange={(e) => setBookingForm({ ...bookingForm, email: e.target.value })}
                />
              </label>
              <label className="block text-sm">
                Anything we should know? (optional)
                <textarea
                  className="mt-1 block w-full rounded-lg bg-slate-800 px-3 py-2"
                  rows={2}
                  value={bookingForm.intent_notes}
                  onChange={(e) => setBookingForm({ ...bookingForm, intent_notes: e.target.value })}
                />
              </label>
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
                  checked={bookingConsent}
                  onChange={(e) => setBookingConsent(e.target.checked)}
                  required
                />
                <span>
                  I agree that {brand} may contact me about this appointment. My consent and the booking time are
                  recorded.
                </span>
              </label>
              {bookingError && <p className="text-xs text-red-400">{bookingError}</p>}
              <button
                className={`w-full rounded-lg py-2 text-sm font-semibold ${accent ? "" : "bg-sky-600 hover:bg-sky-500"} disabled:opacity-50`}
                style={accent ? { backgroundColor: accent } : undefined}
                disabled={busy || !bookingConsent || !selectedSlot}
              >
                {busy ? "Booking…" : "Request this slot"}
              </button>
              <p className="text-[10px] text-slate-500 text-center">
                The platform sends no confirmation or reminder message — the business will contact you.
              </p>
              {footer && <p className="text-[10px] text-slate-500 text-center">{footer}</p>}
            </form>
          )
        ) : (
          <form
            onSubmit={submit}
            className="space-y-4"
            onFocus={() => {
              if (!formStarted) {
                setFormStarted(true);
                track("form_start");
              }
            }}
          >
            <div>
              {config.logo_url && (
                <img src={config.logo_url} alt={brand} className="max-h-12 mb-2 rounded" />
              )}
              <h1 className="text-2xl font-bold">
                {config.variant?.headline || brand}
              </h1>
              <p className="text-sm text-slate-400">
                {config.variant?.subtext ||
                  `${config.niche || "Quality services"}${config.target_area ? ` · ${config.target_area}` : ""}`}
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
            {config.booking?.enabled && (
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-3 space-y-1">
                <p className="text-xs font-semibold text-slate-200">Prefer a fixed time?</p>
                <p className="text-[11px] text-slate-500">
                  Pick an appointment slot instead of a callback.
                </p>
                <button
                  type="button"
                  className="rounded bg-slate-800 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700"
                  onClick={() => {
                    setMode("book");
                    track("form_start");
                  }}
                >
                  Book an appointment
                </button>
              </div>
            )}
            <label className="flex items-start gap-2 text-xs text-slate-300">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
                required
              />
              <span>
                I agree that {brand} may contact me using the details above. My consent and the
                submission time are recorded.
              </span>
            </label>
            {config.support_email && (
              <p className="text-[11px] text-slate-500">
                Questions? <a className="underline" href={`mailto:${config.support_email}`}>{config.support_email}</a>
              </p>
            )}
            {error && <p className="text-xs text-red-400">{error}</p>}
            <button
              className={`w-full rounded-lg py-2 text-sm font-semibold ${accent ? "" : "bg-sky-600 hover:bg-sky-500"} disabled:opacity-50`}
              style={accent ? { backgroundColor: accent } : undefined}
              disabled={busy || !consent}
            >
              {busy ? "Sending…" : (config.variant?.cta_label || "Request a callback")}
            </button>
            {footer && <p className="text-[10px] text-slate-500 text-center">{footer}</p>}
          </form>
        )}
      </div>
    </div>
  );
}

function DuplicateLeadsPanel({ onMerged }) {
  const role = getUser()?.role ?? "owner";
  const canMerge = ["owner", "admin"].includes(role);
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [primaryPick, setPrimaryPick] = useState({}); // group key -> lead id to keep
  const [preview, setPreview] = useState(null); // { groupKey, summary }

  const load = async () => {
    setBusy(true);
    setError("");
    try {
      setData(await api("/api/leads/duplicates"));
    } catch (err) {
      setError(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Scan failed.");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (open) load();
  }, [open]);

  const primaryOf = (group) => primaryPick[group.key] ?? group.leads[0].id;

  const runMerge = async (group, dryRun) => {
    const primary_id = primaryOf(group);
    const duplicate_ids = group.leads.filter((l) => l.id !== primary_id).map((l) => l.id);
    if (!duplicate_ids.length) return;
    if (
      !dryRun &&
      !window.confirm(
        `Merge ${duplicate_ids.length} duplicate lead(s) into #${primary_id}?\n\n` +
          "Their notes, timeline, appointments, conversations and other history move to the kept lead. " +
          "The duplicate lead rows are then deleted. Deal outcomes are never summed."
      )
    ) {
      return;
    }
    setBusy(true);
    setError("");
    setMsg("");
    try {
      const body = await api("/api/leads/merge", {
        method: "POST",
        body: JSON.stringify({ primary_id, duplicate_ids, dry_run: dryRun }),
      });
      if (dryRun) {
        setPreview({ groupKey: group.key, summary: body });
      } else {
        setPreview(null);
        setMsg(`Merged ${duplicate_ids.length} duplicate(s) into lead #${primary_id}.`);
        await load();
        onMerged?.();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Merge failed.");
    } finally {
      setBusy(false);
    }
  };

  const movedLines = (moved) =>
    Object.entries(moved ?? {})
      .filter(([, value]) => Number(value) > 0)
      .map(([key, value]) => `${key.replaceAll("_", " ")}: ${value}`);

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-semibold">Duplicate leads</p>
          <p className="text-xs text-slate-400">
            Exact phone/email matches only - names are never fuzzy-matched and nothing is merged without your confirmation.
          </p>
        </div>
        <button
          className="rounded-lg bg-slate-800 px-3 py-2 text-xs hover:bg-slate-700"
          onClick={() => {
            setOpen(!open);
            setMsg("");
            setPreview(null);
          }}
        >
          {open ? "Hide duplicates" : "Scan for duplicates"}
        </button>
      </div>

      {open && (
        <div className="mt-3 space-y-3">
          {busy && <p className="text-xs text-slate-400">Working…</p>}
          {error && <p className="text-xs text-red-400">{error}</p>}
          {msg && <p className="text-xs text-emerald-300">{msg}</p>}
          {!canMerge && (
            <p className="text-xs text-amber-300">
              You can review matches, but only an owner or admin can merge leads.
            </p>
          )}
          {data && data.groups.length === 0 && (
            <p className="text-xs text-slate-400">
              No duplicates found among {data.scanned} lead(s).{" "}
              {data.truncated ? "Only the first 5,000 leads were scanned." : ""}
            </p>
          )}
          {data?.groups.map((group) => {
            const previewHere = preview?.groupKey === group.key ? preview.summary : null;
            return (
              <div key={group.key} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                <p className="text-xs text-slate-400">
                  Matched on <span className="text-sky-300">{group.matched_on.join(" + ")}</span> · choose the lead to keep:
                </p>
                <ul className="mt-2 space-y-1">
                  {group.leads.map((l) => (
                    <li key={l.id} className="text-xs">
                      <label className="flex flex-wrap items-center gap-2">
                        <input
                          type="radio"
                          name={`dup-primary-${group.key}`}
                          checked={primaryOf(group) === l.id}
                          onChange={() => {
                            setPrimaryPick((s) => ({ ...s, [group.key]: l.id }));
                            setPreview(null);
                          }}
                          disabled={!canMerge}
                        />
                        <span className="font-semibold">#{l.id} {l.name || "(no name)"}</span>
                        <span className="text-slate-400">
                          {[l.phone, l.email, l.status, l.source].filter(Boolean).join(" · ")}
                        </span>
                        {l.created_at && (
                          <span className="text-slate-500">created {new Date(l.created_at).toLocaleDateString()}</span>
                        )}
                      </label>
                    </li>
                  ))}
                </ul>
                {canMerge && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      className="rounded bg-slate-800 px-2 py-1 text-xs hover:bg-slate-700"
                      onClick={() => runMerge(group, true)}
                      disabled={busy}
                    >
                      Preview merge
                    </button>
                    <button
                      className="rounded bg-emerald-900 px-2 py-1 text-xs hover:bg-emerald-800"
                      onClick={() => runMerge(group, false)}
                      disabled={busy}
                    >
                      Merge
                    </button>
                  </div>
                )}
                {previewHere && (
                  <div className="mt-2 rounded border border-slate-800 bg-slate-900 p-2 text-xs space-y-1">
                    <p className="font-semibold text-slate-200">
                      Preview: keep #{previewHere.primary.id}{" "}
                      {previewHere.primary.name ? `(${previewHere.primary.name})` : ""}
                    </p>
                    <p className="text-slate-400">
                      {movedLines(previewHere.moved).length
                        ? movedLines(previewHere.moved).join(" · ")
                        : "No child records to move."}
                    </p>
                    {previewHere.fields_filled.length > 0 && (
                      <p className="text-sky-300">Filled from duplicate: {previewHere.fields_filled.join(", ")}</p>
                    )}
                    {previewHere.conflicts.length > 0 && (
                      <ul className="list-disc pl-4 text-amber-300">
                        {previewHere.conflicts.map((conflict, i) => (
                          <li key={i}>{conflict}</li>
                        ))}
                      </ul>
                    )}
                    {previewHere.notes.map((note, i) => (
                      <p key={i} className="text-slate-500">{note}</p>
                    ))}
                    <button
                      className="rounded bg-emerald-900 px-2 py-1 text-xs hover:bg-emerald-800"
                      onClick={() => runMerge(group, false)}
                      disabled={busy}
                    >
                      Confirm merge
                    </button>
                  </div>
                )}
              </div>
            );
          })}
          {data && data.groups.length > 0 && (
            <p className="text-xs text-slate-500">
              {data.groups_total} group(s) found among {data.scanned} scanned lead(s).
              {data.truncated ? " Only the first 5,000 leads were scanned." : ""}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function LeadsPanel() {
  const [leads, setLeads] = useState([]);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  // P7 #2: per-page lead filter (custom pages only).
  const [pageFilter, setPageFilter] = useState("");
  const [pages, setPages] = useState([]);
  const [openNotes, setOpenNotes] = useState(null); // lead id
  const [notes, setNotes] = useState({});
  const [noteDraft, setNoteDraft] = useState("");
  const [showImport, setShowImport] = useState(false);
  const [importSource, setImportSource] = useState("meta_lead_ad");
  const [importConsent, setImportConsent] = useState(false);
  const [importMsg, setImportMsg] = useState("");
  const [defaultIcpId, setDefaultIcpId] = useState(null);
  const [fits, setFits] = useState({});
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

  // Default ICP for one-click fit checks (silently absent if none exists).
  useEffect(() => {
    api("/api/icp")
      .then((b) => {
        const def = b.profiles.find((p) => p.is_default) ?? b.profiles[0];
        if (def) setDefaultIcpId(def.id);
      })
      .catch(() => {});
    // P7 #2: custom pages for the per-page lead filter.
    api("/api/pages")
      .then((b) => setPages(b.pages || []))
      .catch(() => {});
  }, []);

  // Debounced re-fetch on filter changes
  useEffect(() => {
    const t = setTimeout(() => loadLeads({ q, status: statusFilter, source: sourceFilter, page: pageFilter }), 300);
    return () => clearTimeout(t);
  }, [q, statusFilter, sourceFilter, pageFilter]);

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

  // ICP fit check: uses the default profile (or the first one). Transparent:
  // shows the grade, the score basis, and every factor's explanation.
  const runFit = async (id) => {
    setError("");
    try {
      const b = await api(`/api/icp/${defaultIcpId}/match/${id}`, { method: "POST" });
      setFits((f) => ({ ...f, [id]: b.fit }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fit check failed.");
    }
  };

  // BANT qualification (unknown-first): open = load the lead's current state.
  const [bants, setBants] = useState({});
  const [openBant, setOpenBant] = useState(null);
  const [bantDraft, setBantDraft] = useState(null);

  const toggleBant = async (id) => {
    if (openBant === id) {
      setOpenBant(null);
      return;
    }
    try {
      const b = await api(`/api/leads/${id}/qualification`);
      const dims = b.qualification.dimensions;
      setBants((s) => ({ ...s, [id]: b.qualification }));
      setBantDraft({
        budget: dims.budget.value, authority: dims.authority.value,
        need: dims.need.value, timing: dims.timing.value,
      });
      setOpenBant(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "BANT load failed.");
    }
  };

  const saveBant = async (id) => {
    try {
      const b = await api(`/api/leads/${id}/qualification`, { method: "PATCH", body: JSON.stringify(bantDraft) });
      setBants((s) => ({ ...s, [id]: b.qualification }));
      setBantDraft(null);
      setOpenBant(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "BANT save failed.");
    }
  };

  // Engagement scoring (heuristic, transparent) + ICP grade snapshot.
  const [scores, setScores] = useState({});
  const runScore = async (id) => {
    setError("");
    try {
      const b = await api(`/api/leads/${id}/score`, { method: "POST" });
      setScores((s) => ({ ...s, [id]: b }));
      loadLeads();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scoring failed.");
    }
  };

  // Unified per-lead timeline (notes + stages + status + BANT edits).
  const [timelines, setTimelines] = useState({});
  const [openTimeline, setOpenTimeline] = useState(null);
  const toggleTimeline = async (id) => {
    if (openTimeline === id) {
      setOpenTimeline(null);
      return;
    }
    try {
      const b = await api(`/api/leads/${id}/timeline`);
      setTimelines((t) => ({ ...t, [id]: b.timeline }));
      setOpenTimeline(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Timeline load failed.");
    }
  };

  // Nurture: enroll this lead in a campaign / manage its enrollment.
  const [nurtureCampaigns, setNurtureCampaigns] = useState([]);
  const [openNurture, setOpenNurture] = useState(null); // lead id
  const [nurtureEnrollments, setNurtureEnrollments] = useState({});
  const [nurturePick, setNurturePick] = useState("");
  const [nurtureMsg, setNurtureMsg] = useState("");

  const toggleNurture = async (id) => {
    if (openNurture === id) {
      setOpenNurture(null);
      return;
    }
    setNurtureMsg("");
    setNurturePick("");
    try {
      const camps = await api("/api/nurture/campaigns");
      setNurtureCampaigns(camps.campaigns.filter((c) => c.active));
      const enrolls = await api(`/api/nurture/enrollments`);
      const mine = {};
      for (const e of enrolls.enrollments) {
        if (!mine[e.lead_id] || e.status === "active") mine[e.lead_id] = e;
      }
      setNurtureEnrollments((s) => ({ ...s, ...mine }));
      setOpenNurture(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nurture load failed.");
    }
  };

  const enrollNurture = async (leadId) => {
    if (!nurturePick) return;
    try {
      const b = await api(`/api/nurture/campaigns/${nurturePick}/enroll`, { method: "POST", body: JSON.stringify({ lead_id: leadId }) });
      setNurtureEnrollments((s) => ({ ...s, [leadId]: b.enrollment }));
      setNurtureMsg(b.outcome === "suppressed" ? "Contact is on the suppression list - not enrolled." : "Enrolled.");
    } catch (err) {
      setNurtureMsg(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Enroll failed.");
    }
  };

  const stopNurture = async (leadId) => {
    const e = nurtureEnrollments[leadId];
    if (!e) return;
    try {
      const b = await api(`/api/nurture/enrollments/${e.id}/stop`, { method: "POST" });
      setNurtureEnrollments((s) => ({ ...s, [leadId]: b.enrollment }));
    } catch (err) {
      setNurtureMsg(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Stop failed.");
    }
  };

  // Reviews & referrals (P2 #1): owner-executed, consent-first.
  const [openReview, setOpenReview] = useState(null); // lead id
  const [reviewsByLead, setReviewsByLead] = useState({});
  const [reviewChannel, setReviewChannel] = useState("whatsapp");
  const [reviewMsg, setReviewMsg] = useState("");
  const [referralLinks, setReferralLinks] = useState({});
  const [openReferral, setOpenReferral] = useState(null); // lead id

  const loadReview = async (id) => {
    const b = await api(`/api/reviews?lead_id=${id}`);
    const open = b.reviews.find((r) => r.status === "requested") || b.reviews[0];
    setReviewsByLead((s) => ({ ...s, [id]: open || null }));
    return open;
  };

  const toggleReview = async (id) => {
    if (openReview === id) {
      setOpenReview(null);
      return;
    }
    setReviewMsg(""); setReviewChannel("whatsapp");
    try {
      await loadReview(id);
      setOpenReview(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Review load failed.");
    }
  };

  const requestReview = async (leadId) => {
    setReviewMsg("");
    try {
      const b = await api("/api/reviews", { method: "POST", body: JSON.stringify({ lead_id: leadId, channel: reviewChannel }) });
      setReviewsByLead((s) => ({ ...s, [leadId]: b.review }));
      setReviewMsg("Logged. You send the ask yourself - the platform sends nothing.");
    } catch (err) {
      setReviewMsg(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Request failed.");
    }
  };

  const resolveReview = async (leadId, status) => {
    const r = reviewsByLead[leadId];
    if (!r) return;
    try {
      const b = await api(`/api/reviews/${r.id}`, { method: "PATCH", body: JSON.stringify({ status }) });
      setReviewsByLead((s) => ({ ...s, [leadId]: b.review }));
      setReviewMsg(`Marked ${status}.`);
    } catch (err) {
      setReviewMsg(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Update failed.");
    }
  };

  const toggleReferral = async (id) => {
    if (openReferral === id) {
      setOpenReferral(null);
      return;
    }
    try {
      const b = await api(`/api/referrals/leads/${id}/code`, { method: "POST" });
      setReferralLinks((s) => ({ ...s, [id]: b }));
      const el = document.createElement("textarea");
      el.value = `${window.location.origin}${b.path || ""}`;
      document.body.appendChild(el);
      el.select();
      let copied = false;
      try { copied = document.execCommand("copy"); } catch { copied = false; }
      document.body.removeChild(el);
      if (copied) setReferralLinks((s) => ({ ...s, [id]: { ...b, copied: true } }));
      setOpenReferral(id);
    } catch (err) {
      setError(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Referral link failed.");
    }
  };

  // Revenue & ROI (P5 #3): manual deal outcome. Owner/admin/manager only -
  // agents keep their operational workflow but cannot record money.
  const meRole = getUser()?.role ?? "owner";
  const canRevenue = ["owner", "admin", "manager"].includes(meRole);
  const [openDeal, setOpenDeal] = useState(null);
  const [deals, setDeals] = useState({});
  const [dealDraft, setDealDraft] = useState(null);
  const [dealMsg, setDealMsg] = useState("");

  const toggleDeal = async (id) => {
    if (openDeal === id) {
      setOpenDeal(null);
      return;
    }
    setDealMsg("");
    try {
      const b = await api(`/api/leads/${id}/outcome`);
      const o = b.outcome;
      setDeals((s) => ({ ...s, [id]: o }));
      setDealDraft({
        status: o?.status ?? "open",
        amount: o?.amount ?? "",
        currency: o?.currency ?? "PKR",
        closed_at: o?.closed_at ?? "",
        note: o?.note ?? "",
      });
      setOpenDeal(id);
    } catch (err) {
      setError(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Deal load failed.");
    }
  };

  const saveDeal = async (id) => {
    if (!dealDraft) return;
    setDealMsg("");
    try {
      const b = await api(`/api/leads/${id}/outcome`, {
        method: "PUT",
        body: JSON.stringify({
          status: dealDraft.status,
          amount: Number(dealDraft.amount || 0),
          currency: dealDraft.currency,
          closed_at: dealDraft.status === "open" ? null : (dealDraft.closed_at || null),
          note: dealDraft.note,
        }),
      });
      setDeals((s) => ({ ...s, [id]: b.outcome }));
      setDealMsg("Deal saved and added to the lead timeline.");
    } catch (err) {
      setDealMsg(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Deal save failed.");
    }
  };

  const removeDeal = async (id) => {
    if (!window.confirm("Remove this deal outcome? Revenue for this lead becomes unknown again.")) return;
    setDealMsg("");
    try {
      await api(`/api/leads/${id}/outcome`, { method: "DELETE" });
      setDeals((s) => ({ ...s, [id]: null }));
      setDealDraft({ status: "open", amount: "", currency: "PKR", closed_at: "", note: "" });
      setDealMsg("Deal outcome removed.");
    } catch (err) {
      setDealMsg(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Remove failed.");
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
      <DuplicateLeadsPanel onMerged={() => loadLeads({ q, status: statusFilter, source: sourceFilter, page: pageFilter })} />
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
        <select className="rounded-lg bg-slate-800 px-2 py-2 text-sm" value={pageFilter} onChange={(e) => setPageFilter(e.target.value)}>
          <option value="">All custom pages</option>
          {pages.map((p) => (
            <option key={p.id} value={p.slug}>
              {p.title || p.slug}
            </option>
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
                {l.landing_page_slug && (
                  <span className="rounded bg-indigo-900 px-2 py-0.5 text-xs">/p/{l.landing_page_slug}</span>
                )}
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
              {defaultIcpId && (
                <div className="mt-2">
                  <button className="text-xs text-emerald-400 hover:text-emerald-300" onClick={() => runFit(l.id)}>
                    {fits[l.id] ? "Re-check ICP fit" : "Check ICP fit"}
                  </button>
                  {fits[l.id] && (
                    <div className="mt-1 rounded border border-slate-800 bg-slate-900 p-2 text-xs">
                      <p className="font-semibold">
                        {fits[l.id].grade
                          ? <>Grade {fits[l.id].grade} · fit {fits[l.id].score}% <span className="text-slate-500 font-normal">(heuristic — not a calibrated probability)</span></>
                          : "Not enough information to grade"}
                      </p>
                      <ul className="mt-1 space-y-0.5 text-slate-400">
                        {fits[l.id].factors.map((f) => (
                          <li key={f.factor}>
                            <span className={
                              f.status === "match" ? "text-emerald-400" :
                              f.status === "partial" ? "text-amber-400" :
                              f.status === "no_match" ? "text-red-400" : "text-slate-500"
                            }>{f.status}</span> {f.factor}: {f.detail}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
              <div className="mt-2">
                <button className="text-xs text-violet-300 hover:text-violet-200" onClick={() => toggleBant(l.id)}>
                  {openBant === l.id ? "Hide BANT" : `BANT${bants[l.id] ? ` (${bants[l.id].complete}/4 known)` : ""}`}
                </button>
                {openBant === l.id && bantDraft && bants[l.id] && (
                  <div className="mt-1 rounded border border-slate-800 bg-slate-900 p-2 text-xs space-y-2">
                    <p className="text-slate-400">
                      {bants[l.id].complete}/4 known
                      {bants[l.id].suggestion ? ` · ${bants[l.id].suggestion}` : " · 'Unknown' is a valid answer — never invent values."}
                    </p>
                    {["budget", "authority", "need", "timing"].map((d) => (
                      <label key={d} className="block">
                        <span className={bants[l.id].dimensions[d].confidence === "known" ? "text-emerald-400" : "text-slate-500"}>
                          {d[0].toUpperCase() + d.slice(1)}
                          {bants[l.id].dimensions[d].confidence === "unknown" ? " (unknown)" : ` · ${bants[l.id].dimensions[d].source}`}
                        </span>
                        <input
                          className="mt-0.5 w-full rounded bg-slate-800 px-2 py-1"
                          placeholder="leave blank = unknown"
                          value={bantDraft[d]}
                          onChange={(e) => setBantDraft({ ...bantDraft, [d]: e.target.value })}
                        />
                      </label>
                    ))}
                    <button className="rounded bg-violet-700 px-3 py-1 hover:bg-violet-600" onClick={() => saveBant(l.id)}>
                      Save BANT
                    </button>
                  </div>
                )}
              </div>
              <div className="mt-2">
                <button className="text-xs text-amber-300 hover:text-amber-200" onClick={() => runScore(l.id)}>
                  {scores[l.id] ? "Re-score lead" : `⚡ Score lead${l.score ? ` (last: ${l.score})` : ""}`}
                </button>
                {scores[l.id] && (
                  <div className="mt-1 rounded border border-slate-800 bg-slate-900 p-2 text-xs">
                    <p className="font-semibold">
                      Score {scores[l.id].score} · grade {scores[l.id].grade || "—"}
                      {scores[l.id].history_count ? ` · ${scores[l.id].history_count} snapshots` : ""}
                    </p>
                    <p className="text-slate-500">{scores[l.id].label}</p>
                    <ul className="mt-1 space-y-0.5 text-slate-400">
                      {scores[l.id].factors.map((f) => (
                        <li key={f.signal}>
                          <span className={f.points > 0 ? "text-emerald-400" : "text-slate-500"}>+{f.points}</span> {f.signal}: {f.detail}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
              {l.intent_notes && <p className="mt-1 text-slate-400 whitespace-pre-wrap">{l.intent_notes}</p>}
              <button className="mt-2 text-xs text-sky-300 hover:text-sky-200" onClick={() => toggleTimeline(l.id)}>
                {openTimeline === l.id ? "Hide timeline" : "Timeline"}
              </button>
              <button className="mt-2 ml-3 text-xs text-rose-300 hover:text-rose-200" onClick={() => toggleNurture(l.id)}>
                {openNurture === l.id ? "Hide nurture" : "Nurture"}
              </button>
              {openNurture === l.id && (
                <div className="mt-1 rounded border border-slate-800 bg-slate-900 p-2 text-xs space-y-2">
                  {nurtureEnrollments[l.id] && (
                    <p className="text-slate-300">
                      {nurtureEnrollments[l.id].status === "active"
                        ? `Active · step ${nurtureEnrollments[l.id].current_step}/${nurtureEnrollments[l.id].steps_total}`
                        : `Status: ${nurtureEnrollments[l.id].status}`}
                      {nurtureEnrollments[l.id].next_step_at && nurtureEnrollments[l.id].status === "active" && (
                        <> · next touch {new Date(nurtureEnrollments[l.id].next_step_at).toLocaleDateString()}</>
                      )}
                      {nurtureEnrollments[l.id].status === "active" && (
                        <button className="ml-2 text-rose-300 hover:text-rose-200" onClick={() => stopNurture(l.id)}>Stop sequence</button>
                      )}
                    </p>
                  )}
                  {nurtureCampaigns.length > 0 ? (
                    <div className="flex gap-2 items-center">
                      <select className="rounded bg-slate-800 px-2 py-1" value={nurturePick}
                              onChange={(e) => setNurturePick(e.target.value)}>
                        <option value="">Choose campaign…</option>
                        {nurtureCampaigns.map((c) => (
                          <option key={c.id} value={c.id}>{c.name} ({c.steps.length} steps)</option>
                        ))}
                      </select>
                      <button className="rounded bg-rose-800 px-3 py-1 hover:bg-rose-700" onClick={() => enrollNurture(l.id)}>
                        Enroll
                      </button>
                      <button className="rounded bg-slate-800 px-3 py-1 text-slate-300 hover:bg-slate-700" title="Surface any due nurture touches right now"
                              onClick={async () => {
                                try {
                                  const b = await api("/api/nurture/process-due", { method: "POST" });
                                  setNurtureMsg(`${b.steps_surfaced} touch(es) due right now.`);
                                } catch (err) {
                                  setNurtureMsg(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Run failed.");
                                }
                              }}>
                        Check due
                      </button>
                    </div>
                  ) : (
                    <p className="text-slate-500">No active campaigns — create one in Settings → Nurture campaigns.</p>
                  )}
                  {nurtureMsg && <p className="text-slate-400">{nurtureMsg}</p>}
                </div>
              )}
              <button className="mt-2 ml-3 text-xs text-emerald-300 hover:text-emerald-200" onClick={() => toggleReview(l.id)}>
                {openReview === l.id ? "Hide review" : "Review"}
              </button>
              {openReview === l.id && (
                <div className="mt-1 rounded border border-slate-800 bg-slate-900 p-2 text-xs space-y-2">
                  {reviewsByLead[l.id] ? (
                    <p className="text-slate-300">
                      Review ask: <b>{reviewsByLead[l.id].status}</b> · via {reviewsByLead[l.id].channel}
                      {reviewsByLead[l.id].status === "requested" && (
                        <>
                          <button className="ml-2 text-emerald-300 hover:text-emerald-200" onClick={() => resolveReview(l.id, "completed")}>Mark completed</button>
                          <button className="ml-2 text-rose-300 hover:text-rose-200" onClick={() => resolveReview(l.id, "declined")}>Mark declined</button>
                        </>
                      )}
                    </p>
                  ) : (
                    <div className="flex gap-2 items-center">
                      <select className="rounded bg-slate-800 px-2 py-1" value={reviewChannel} onChange={(e) => setReviewChannel(e.target.value)}>
                        {["whatsapp", "phone", "email", "in_person"].map((c) => (<option key={c} value={c}>{c}</option>))}
                      </select>
                      <button className="rounded bg-emerald-800 px-3 py-1 hover:bg-emerald-700" onClick={() => requestReview(l.id)}>
                        Log review ask
                      </button>
                    </div>
                  )}
                  <p className="text-slate-500">You send the ask yourself; the platform only records it. Converted leads only.</p>
                  {reviewMsg && <p className="text-slate-400">{reviewMsg}</p>}
                </div>
              )}
              <button className="mt-2 ml-3 text-xs text-amber-300 hover:text-amber-200" onClick={() => toggleReferral(l.id)}>
                {openReferral === l.id ? "Hide referral" : "Refer"}
              </button>
              {openReferral === l.id && referralLinks[l.id] && (
                <div className="mt-1 rounded border border-slate-800 bg-slate-900 p-2 text-xs space-y-1">
                  <p className="text-slate-300">
                    Share link: <code className="text-slate-200 break-all">{`${window.location.origin}${referralLinks[l.id].path || ""}`}</code>
                  </p>
                  <p className="text-slate-500">
                    {referralLinks[l.id].copied ? "Copied to clipboard. " : ""}
                    The referred person submits the normal consent form; only link-based referrals are tracked.
                  </p>
                </div>
              )}
              {canRevenue && (
                <>
                  <button className="mt-2 ml-3 text-xs text-teal-300 hover:text-teal-200" onClick={() => toggleDeal(l.id)}>
                    {openDeal === l.id ? "Hide deal" : deals[l.id] ? `Deal: ${deals[l.id].status}` : "Deal"}
                  </button>
                  {openDeal === l.id && dealDraft && (
                    <div className="mt-1 rounded border border-slate-800 bg-slate-900 p-2 text-xs space-y-2">
                      <div className="flex flex-wrap items-end gap-2">
                        <label className="text-slate-400">
                          Status
                          <select
                            className="mt-1 block rounded bg-slate-800 px-2 py-1"
                            value={dealDraft.status}
                            onChange={(e) => setDealDraft({ ...dealDraft, status: e.target.value })}
                          >
                            <option value="open">open</option>
                            <option value="won">won</option>
                            <option value="lost">lost</option>
                          </select>
                        </label>
                        <label className="text-slate-400">
                          Amount
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            className="mt-1 block w-28 rounded bg-slate-800 px-2 py-1"
                            value={dealDraft.amount}
                            onChange={(e) => setDealDraft({ ...dealDraft, amount: e.target.value })}
                          />
                        </label>
                        <label className="text-slate-400">
                          Currency
                          <input
                            className="mt-1 block w-20 rounded bg-slate-800 px-2 py-1 uppercase"
                            maxLength={10}
                            value={dealDraft.currency}
                            onChange={(e) => setDealDraft({ ...dealDraft, currency: e.target.value })}
                          />
                        </label>
                        {dealDraft.status !== "open" && (
                          <label className="text-slate-400">
                            Closed on
                            <input
                              type="date"
                              className="mt-1 block rounded bg-slate-800 px-2 py-1"
                              value={dealDraft.closed_at}
                              onChange={(e) => setDealDraft({ ...dealDraft, closed_at: e.target.value })}
                            />
                          </label>
                        )}
                      </div>
                      <input
                        className="w-full rounded bg-slate-800 px-2 py-1"
                        maxLength={500}
                        placeholder="Note (optional)"
                        value={dealDraft.note}
                        onChange={(e) => setDealDraft({ ...dealDraft, note: e.target.value })}
                      />
                      <div className="flex flex-wrap items-center gap-2">
                        <button className="rounded bg-teal-800 px-3 py-1 hover:bg-teal-700" onClick={() => saveDeal(l.id)}>
                          Save deal
                        </button>
                        {deals[l.id] && (
                          <button className="rounded bg-rose-900 px-3 py-1 hover:bg-rose-800" onClick={() => removeDeal(l.id)}>
                            Remove
                          </button>
                        )}
                      </div>
                      <p className="text-slate-500">
                        Manual revenue only. Currencies are never converted; ROI needs campaign spend in the same
                        currency.
                      </p>
                      {dealMsg && <p className="text-slate-400">{dealMsg}</p>}
                    </div>
                  )}
                </>
              )}
              {openTimeline === l.id && (
                <ul className="mt-1 space-y-1 border-t border-slate-800 pt-2">
                  {(timelines[l.id] ?? []).map((e, i) => (
                    <li key={i} className="text-xs">
                      <span className={
                        e.type === "note" ? "text-sky-300" :
                        e.type === "stage" ? "text-amber-300" :
                        e.type === "status_changed" ? "text-violet-300" : "text-emerald-300"
                      }>{e.type}</span>{" "}
                      <span className="text-slate-300">{e.text}</span>{" "}
                      <span className="text-slate-500">{e.at ? new Date(e.at).toLocaleString() : ""}</span>
                    </li>
                  ))}
                </ul>
              )}
              <button className="mt-2 block text-xs text-slate-400 hover:text-slate-200" onClick={() => toggleNotes(l.id)}>
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

function InboxPanel() {
  const [conversations, setConversations] = useState([]);
  const [activeConv, setActiveConv] = useState(null); // conversation object
  const [thread, setThread] = useState([]);
  const [reply, setReply] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [leads, setLeads] = useState([]);
  const [newLead, setNewLead] = useState("");
  const [newChannel, setNewChannel] = useState("whatsapp_inbound");
  const CHANNELS = ["whatsapp_inbound", "website_chat", "direct_message"];

  const loadConvs = () =>
    api("/api/inbox/conversations").then((b) => setConversations(b.conversations)).catch((e) => setError(e.message));
  useEffect(() => {
    loadConvs();
  }, []);

  const openConv = async (c) => {
    setActiveConv(c);
    setMsg("");
    try {
      const b = await api(`/api/inbox/conversations/${c.id}/messages`);
      setThread(b.messages);
      if (b.conversation) setActiveConv(b.conversation);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Thread load failed.");
    }
  };

  const send = async (direction) => {
    if (!activeConv || !reply.trim()) return;
    setMsg("");
    try {
      const b = await api(`/api/inbox/conversations/${activeConv.id}/messages`, {
        method: "POST",
        body: JSON.stringify({ direction, body: reply }),
      });
      setThread((t) => [...t, b.message]);
      setReply("");
      if (direction === "in") {
        // The consent gate opens the moment the lead speaks: refresh the active
        // conversation so the reply button enables without reopening.
        setActiveConv((c) => (c ? { ...c, has_inbound: true } : c));
      }
      loadConvs();
    } catch (err) {
      setMsg(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Send failed.");
    }
  };

  const startNew = async () => {
    setError(""); setMsg("");
    try {
      const b = await api("/api/inbox/conversations", {
        method: "POST",
        body: JSON.stringify({ lead_id: Number(newLead), channel: newChannel }),
      });
      setShowNew(false);
      setNewLead("");
      await loadConvs();
      openConv(b.conversation);
    } catch (err) {
      setMsg(err instanceof Error ? err.message.replace(/^API \d+: /, "") : "Create failed.");
    }
  };

  const openNewForm = () => {
    setShowNew((s) => !s);
    api("/api/leads").then((b) => setLeads(b.leads)).catch(() => {});
  };

  return (
    <div className="grid grid-cols-[320px_1fr] gap-4">
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-sm">Conversations</h3>
          <button className="text-xs text-sky-400 hover:text-sky-300" onClick={openNewForm}>+ New</button>
        </div>
        {showNew && (
          <div className="space-y-2 rounded-lg border border-slate-800 bg-slate-950 p-3 text-xs">
            <select className="w-full rounded bg-slate-800 px-2 py-1" value={newLead} onChange={(e) => setNewLead(e.target.value)}>
              <option value="">Choose lead…</option>
              {leads.map((l) => (
                <option key={l.id} value={l.id}>{l.name} ({l.phone})</option>
              ))}
            </select>
            <select className="w-full rounded bg-slate-800 px-2 py-1" value={newChannel} onChange={(e) => setNewChannel(e.target.value)}>
              {CHANNELS.map((c) => (<option key={c} value={c}>{c}</option>))}
            </select>
            <button className="rounded bg-sky-700 px-3 py-1 hover:bg-sky-600" onClick={startNew}>Open conversation</button>
          </div>
        )}
        {error && <p className="text-xs text-red-400">{error}</p>}
        <ul className="space-y-2">
          {conversations.map((c) => (
            <li key={c.id}>
              <button className={`w-full text-left rounded-lg border p-3 text-xs ${activeConv?.id === c.id ? "border-sky-600 bg-slate-950" : "border-slate-800 bg-slate-950 hover:border-slate-700"}`} onClick={() => openConv(c)}>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-sm">{c.lead_name}</span>
                  <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px]">{c.channel}</span>
                </div>
                <p className="mt-1 text-slate-400 truncate">
                  {c.last_direction === "out" ? "→ " : c.last_direction === "in" ? "← " : ""}{c.last_message_preview || "No messages yet"}
                </p>
              </button>
            </li>
          ))}
          {conversations.length === 0 && <li className="text-xs text-slate-500">No conversations yet — open one from a lead.</li>}
        </ul>
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
        {!activeConv ? (
          <p className="text-sm text-slate-400">Select a conversation to view the thread.</p>
        ) : (
          <div className="space-y-3">
            <div>
              <h3 className="font-semibold">{activeConv.lead_name}</h3>
              <p className="text-xs text-slate-500">
                {activeConv.channel} · {activeConv.lead_phone}
                {!activeConv.has_inbound && " · consent rule: the lead must speak first"}
              </p>
            </div>
            <ul className="space-y-2 max-h-96 overflow-y-auto">
              {thread.map((m) => (
                <li key={m.id} className={`max-w-[80%] rounded-lg p-2 text-sm ${m.direction === "out" ? "ml-auto bg-sky-900/60" : "bg-slate-950 border border-slate-800"}`}>
                  <p className="text-[10px] text-slate-500">{m.direction === "out" ? "You" : "Lead"} · {m.sent_at ? new Date(m.sent_at).toLocaleString() : ""}</p>
                  <p className="text-slate-200 whitespace-pre-wrap">{m.body}</p>
                </li>
              ))}
              {thread.length === 0 && <li className="text-xs text-slate-500">No messages yet — record the lead's inbound message first.</li>}
            </ul>
            {msg && <p className="text-xs text-red-400">{msg}</p>}
            <div className="flex gap-2">
              <input
                className="flex-1 rounded-lg bg-slate-800 px-3 py-2 text-sm"
                placeholder="Write the message… (platform records it — you send it from your own WhatsApp/phone)"
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") send(activeConv.has_inbound ? "out" : "in"); }}
              />
              <button className="rounded bg-slate-800 px-3 py-2 text-xs hover:bg-slate-700" onClick={() => send("in")}>
                ← Log inbound
              </button>
              <button className="rounded bg-sky-700 px-3 py-2 text-xs font-semibold hover:bg-sky-600 disabled:opacity-40"
                      disabled={!activeConv.has_inbound} title={activeConv.has_inbound ? "" : "Outbound-first is not allowed — the lead must message first"}
                      onClick={() => send("out")}>
                Reply →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// P5 #2: owner/admin data portability, workspace audit log, telemetry retention
// and honest usage counts. No external metering provider is involved.
const OPS_COUNT_LABELS = [
  ["leads", "Leads"],
  ["appointments", "Appointments"],
  ["content_posts", "Content posts"],
  ["lead_notes", "Lead notes"],
  ["conversations", "Conversations"],
  ["messages", "Messages"],
  ["review_requests", "Review asks"],
  ["webhook_events", "Webhook deliveries"],
  ["landing_events", "A/B impressions"],
  ["analytics_events", "Analytics events"],
  ["team_members_active", "Active team members"],
];

function OpsCard() {
  const [usage, setUsage] = useState(null);
  const [logs, setLogs] = useState([]);
  const [actions, setActions] = useState([]);
  const [preview, setPreview] = useState(null);
  const [days, setDays] = useState(90);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [denied, setDenied] = useState(false);
  const [busy, setBusy] = useState(false);

  const clean = (e, fallback) =>
    e instanceof Error ? e.message.replace(/^API \d+: /, "") : fallback;

  const load = async () => {
    setError("");
    try {
      const [u, a] = await Promise.all([api("/api/ops/usage"), api("/api/ops/audit?limit=50")]);
      setUsage(u);
      setLogs(a.entries || []);
      setActions(a.actions || []);
      setDenied(false);
    } catch (e) {
      if (e && e.status === 403) {
        setDenied(true);
        return;
      }
      setError(clean(e, "Ops data load failed."));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const runPreview = async () => {
    setError("");
    setNote("");
    try {
      const p = await api(`/api/ops/retention/preview?days=${Number(days)}`);
      setPreview(p);
    } catch (e) {
      setError(clean(e, "Retention preview failed."));
    }
  };

  const downloadExport = async () => {
    setBusy(true);
    setError("");
    setNote("");
    try {
      const res = await fetch(`${apiBaseUrl()}/api/ops/export`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) {
        let detail = await res.text();
        try {
          const parsed = JSON.parse(detail);
          detail = typeof parsed.detail === "string" ? parsed.detail : detail;
        } catch {
          /* keep raw */
        }
        throw new Error(`API ${res.status}: ${detail}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `leadcraft-workspace-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setNote("Workspace export downloaded (JSON).");
      load();
    } catch (e) {
      setError(clean(e, "Export failed."));
    } finally {
      setBusy(false);
    }
  };

  const purgeTelemetry = async () => {
    if (
      !window.confirm(
        `Delete anonymous telemetry older than ${days} days? Leads, notes, appointments and the audit log are never touched. This cannot be undone.`
      )
    ) {
      return;
    }
    setBusy(true);
    setError("");
    setNote("");
    try {
      const b = await api("/api/ops/retention/purge", {
        method: "POST",
        body: JSON.stringify({ days: Number(days), confirm: true }),
      });
      setNote(`${b.total_deleted} telemetry row(s) deleted. Business records were not touched.`);
      await runPreview();
      load();
    } catch (e) {
      setError(clean(e, "Retention purge failed."));
    } finally {
      setBusy(false);
    }
  };

  const fmt = (iso) => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  };

  if (denied) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-2">
        <h3 className="font-semibold">Data, audit &amp; ops</h3>
        <p className="text-xs text-amber-400">
          Owner or admin role required. Exports contain customer contact data and the audit log contains team actions.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-5">
      <div>
        <h3 className="font-semibold">Data, audit &amp; ops</h3>
        <p className="text-xs text-slate-500">
          Export your workspace, review admin actions, and remove anonymous telemetry. Counts are database rows for this
          workspace only — not storage bytes.
        </p>
      </div>

      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="rounded bg-sky-700 px-3 py-1.5 text-sm hover:bg-sky-600 disabled:opacity-50"
            onClick={downloadExport}
            disabled={busy}
          >
            {busy ? "Working…" : "Download workspace JSON"}
          </button>
          <span className="text-[11px] text-slate-500">
            Includes leads, notes, timeline, appointments, settings, billing and team members. Excludes anonymous
            telemetry and secrets.
          </span>
        </div>
      </div>

      {usage && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-slate-300">Usage</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            {OPS_COUNT_LABELS.map(([key, label]) => (
              <div key={key} className="rounded bg-slate-950 px-2 py-1.5">
                <span className="block text-slate-500">{label}</span>
                <span className="text-slate-200">{usage.counts[key] ?? 0}</span>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-slate-500">
            Last lead: {fmt(usage.last.lead_at)} · Last appointment: {fmt(usage.last.appointment_at)} · Last webhook:{" "}
            {fmt(usage.last.webhook_at)}
          </p>
        </div>
      )}

      <div className="space-y-2">
        <p className="text-xs font-semibold text-slate-300">Telemetry retention</p>
        <div className="flex flex-wrap items-end gap-2 text-xs">
          <label className="text-slate-400">
            Older than (days, 30–3650)
            <input
              type="number"
              min={30}
              max={3650}
              className="mt-1 block w-28 rounded bg-slate-800 px-2 py-1"
              value={days}
              onChange={(e) => setDays(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="rounded bg-slate-800 px-3 py-1.5 text-sm hover:bg-slate-700"
            onClick={runPreview}
          >
            Preview
          </button>
          <button
            type="button"
            className="rounded bg-rose-900 px-3 py-1.5 text-sm hover:bg-rose-800 disabled:opacity-50"
            onClick={purgeTelemetry}
            disabled={busy}
          >
            Delete telemetry
          </button>
        </div>
        {preview && (
          <div className="text-[11px] text-slate-400 space-y-1">
            <p>
              Would remove: {preview.counts.landing_events} A/B impressions, {preview.counts.analytics_events} analytics
              events, {preview.counts.webhook_events} processed webhook deliveries (total {preview.total}).
            </p>
            <p className="text-slate-500">Kept: {preview.kept.join(", ")}.</p>
            <p className="text-slate-500">{preview.notes.join(" ")}</p>
          </div>
        )}
      </div>

      <div className="space-y-2">
        <p className="text-xs font-semibold text-slate-300">Audit log (workspace actions)</p>
        {logs.length === 0 ? (
          <p className="text-xs text-slate-500">No admin actions recorded yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-slate-500">
                <tr>
                  <th className="text-left font-normal pb-1">When</th>
                  <th className="text-left font-normal pb-1 pl-2">Actor</th>
                  <th className="text-left font-normal pb-1 pl-2">Action</th>
                  <th className="text-left font-normal pb-1 pl-2">Target</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((row) => (
                  <tr key={row.id} className="border-t border-slate-800 align-top">
                    <td className="py-1.5 text-slate-400 whitespace-nowrap">{fmt(row.created_at)}</td>
                    <td className="py-1.5 pl-2 text-slate-300">{row.actor_email || "—"}</td>
                    <td className="py-1.5 pl-2 text-slate-200">{row.action}</td>
                    <td className="py-1.5 pl-2 text-slate-500">
                      {row.target_type || "—"}
                      {row.target_id ? ` #${row.target_id}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="text-[11px] text-slate-500">
          Append-only. Lead edits live in each lead's timeline, not here. Actions: {actions.join(", ") || "none yet"}.
        </p>
      </div>

      {note && <p className="text-xs text-emerald-400">{note}</p>}
      {error && <p className="text-xs text-rose-400">{error}</p>}
    </div>
  );
}

function AppointmentsPanel() {
  const [availability, setAvailability] = useState(null);
  const [canEdit, setCanEdit] = useState(true);
  const [rows, setRows] = useState([]);
  const [tz, setTz] = useState("Asia/Karachi");
  const [statuses, setStatuses] = useState([]);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    enabled: false, days: [], start: "10:00", end: "18:00",
    slot_minutes: 30, lead_minutes: 60, timezone: "Asia/Karachi", services: "", note: "",
  });
  const [manual, setManual] = useState({
    name: "", phone: "", email: "", starts_at: "", service: "", notes: "", consent: false,
  });

  const clean = (e, fallback) =>
    e instanceof Error ? e.message.replace(/^API \d+: /, "") : fallback;

  const load = async () => {
    setError("");
    try {
      const a = await api("/api/appointments/availability");
      setAvailability(a.availability);
      setCanEdit(a.can_edit);
      setTz(a.availability.timezone);
      setForm({
        enabled: a.availability.enabled,
        days: a.availability.days,
        start: a.availability.start,
        end: a.availability.end,
        slot_minutes: a.availability.slot_minutes,
        lead_minutes: a.availability.lead_minutes,
        timezone: a.availability.timezone,
        services: (a.availability.services || []).join(", "),
        note: a.availability.note || "",
      });
      const b = await api("/api/appointments?limit=200");
      setRows(b.appointments || []);
      setStatuses(b.statuses || []);
      setTz(b.timezone || a.availability.timezone);
    } catch (e) {
      setError(clean(e, "Appointments load failed."));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const saveAvailability = async () => {
    setBusy(true);
    setNote("");
    setError("");
    try {
      const services = form.services.split(",").map((s) => s.trim()).filter(Boolean);
      const b = await api("/api/appointments/availability", {
        method: "PATCH",
        body: JSON.stringify({
          enabled: form.enabled,
          days: form.days,
          start: form.start,
          end: form.end,
          slot_minutes: Number(form.slot_minutes),
          lead_minutes: Number(form.lead_minutes),
          timezone: form.timezone,
          services,
          note: form.note,
        }),
      });
      setAvailability(b.availability);
      setTz(b.availability.timezone);
      setNote("Booking settings saved.");
    } catch (e) {
      setError(clean(e, "Could not save booking settings."));
    } finally {
      setBusy(false);
    }
  };

  const setStatus = async (row, status) => {
    setError("");
    try {
      const b = await api(`/api/appointments/${row.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      setRows((list) => list.map((r) => (r.id === row.id ? b.appointment : r)));
    } catch (e) {
      setError(clean(e, "Status update failed."));
    }
  };

  const markReminded = async (row) => {
    setError("");
    try {
      const b = await api(`/api/appointments/${row.id}`, {
        method: "PATCH",
        body: JSON.stringify({ reminded: !row.reminded_at }),
      });
      setRows((list) => list.map((r) => (r.id === row.id ? b.appointment : r)));
    } catch (e) {
      setError(clean(e, "Reminder marker failed."));
    }
  };

  const addManual = async () => {
    setBusy(true);
    setNote("");
    setError("");
    try {
      const startsAt = manual.starts_at ? new Date(manual.starts_at).toISOString() : "";
      const b = await api("/api/appointments", {
        method: "POST",
        body: JSON.stringify({
          starts_at: startsAt,
          name: manual.name,
          phone: manual.phone,
          email: manual.email,
          service: manual.service,
          notes: manual.notes,
          consent: manual.consent,
        }),
      });
      setNote(b.note);
      setManual({ name: "", phone: "", email: "", starts_at: "", service: "", notes: "", consent: false });
      load();
    } catch (e) {
      setError(clean(e, "Could not add the appointment."));
    } finally {
      setBusy(false);
    }
  };

  const fmt = (iso) => {
    if (!iso) return "";
    try {
      return new Intl.DateTimeFormat("en-GB", {
        timeZone: tz,
        weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
      }).format(new Date(iso));
    } catch {
      return iso;
    }
  };

  const toggleDay = (day) =>
    setForm((f) => ({
      ...f,
      days: f.days.includes(day) ? f.days.filter((d) => d !== day) : [...f.days, day].sort((a, b) => a - b),
    }));

  if (!availability && !error) {
    return <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm text-slate-400">Loading…</div>;
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
        <h3 className="font-semibold">Booking availability</h3>
        <p className="text-xs text-slate-500">
          Slots are generated server-side from these hours (timezone: {tz}). The platform sends no SMS, email or
          WhatsApp confirmations or reminders — the deadline reminder below is a manual marker only.
        </p>

        {!canEdit && (
          <p className="text-xs text-amber-400">Your role can view appointments but not change booking settings.</p>
        )}

        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.enabled}
            disabled={!canEdit}
            onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
          />
          Enable booking on the landing page
        </label>

        <div className="flex flex-wrap gap-2">
          {DAY_LABELS.map((label, idx) => (
            <button
              key={label}
              type="button"
              disabled={!canEdit}
              onClick={() => toggleDay(idx)}
              className={`rounded px-2 py-1 text-xs ${
                form.days.includes(idx) ? "bg-sky-700 text-white" : "bg-slate-800 text-slate-300"
              } disabled:opacity-50`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <label className="text-slate-400">
            Opens
            <input type="time" disabled={!canEdit} className="mt-1 block w-full rounded bg-slate-800 px-2 py-1"
              value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} />
          </label>
          <label className="text-slate-400">
            Closes
            <input type="time" disabled={!canEdit} className="mt-1 block w-full rounded bg-slate-800 px-2 py-1"
              value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} />
          </label>
          <label className="text-slate-400">
            Slot length
            <select disabled={!canEdit} className="mt-1 block w-full rounded bg-slate-800 px-2 py-1"
              value={form.slot_minutes} onChange={(e) => setForm({ ...form, slot_minutes: e.target.value })}>
              {[15, 30, 45, 60, 90, 120].map((m) => <option key={m} value={m}>{m} min</option>)}
            </select>
          </label>
          <label className="text-slate-400">
            Minimum notice
            <select disabled={!canEdit} className="mt-1 block w-full rounded bg-slate-800 px-2 py-1"
              value={form.lead_minutes} onChange={(e) => setForm({ ...form, lead_minutes: e.target.value })}>
              <option value={0}>None</option>
              <option value={30}>30 min</option>
              <option value={60}>1 hour</option>
              <option value={240}>4 hours</option>
              <option value={1440}>1 day</option>
            </select>
          </label>
          <label className="text-slate-400 md:col-span-2">
            Timezone (IANA)
            <input disabled={!canEdit} className="mt-1 block w-full rounded bg-slate-800 px-2 py-1"
              value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} />
          </label>
          <label className="text-slate-400 md:col-span-2">
            Services (comma separated, max 10)
            <input disabled={!canEdit} className="mt-1 block w-full rounded bg-slate-800 px-2 py-1"
              value={form.services} onChange={(e) => setForm({ ...form, services: e.target.value })} />
          </label>
          <label className="text-slate-400 md:col-span-4">
            Booking note shown to visitors
            <input disabled={!canEdit} className="mt-1 block w-full rounded bg-slate-800 px-2 py-1"
              value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
          </label>
        </div>

        {canEdit && (
          <button
            className="rounded bg-slate-800 px-3 py-1.5 text-sm hover:bg-slate-700 disabled:opacity-50"
            onClick={saveAvailability}
            disabled={busy}
          >
            Save booking settings
          </button>
        )}
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-3">
        <h3 className="font-semibold">Appointments</h3>
        <p className="text-xs text-slate-500">
          Times shown in {tz}. {availability?.disclaimer}
        </p>
        {rows.length === 0 ? (
          <p className="text-xs text-slate-500">No appointments yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-slate-500">
                <tr>
                  <th className="text-left font-normal pb-1">When</th>
                  <th className="text-left font-normal pb-1 pl-2">Customer</th>
                  <th className="text-left font-normal pb-1 pl-2">Service</th>
                  <th className="text-left font-normal pb-1 pl-2">Status</th>
                  <th className="text-left font-normal pb-1 pl-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-slate-800 align-top">
                    <td className="py-2 text-slate-300">
                      {fmt(r.starts_at)}
                      {r.source === "manual" && <span className="block text-[10px] text-slate-500">team entered</span>}
                    </td>
                    <td className="py-2 pl-2">
                      <span className="block text-slate-200">{r.lead_name}</span>
                      <span className="block text-slate-500">{r.lead_phone || r.lead_email}</span>
                    </td>
                    <td className="py-2 pl-2 text-slate-400">{r.service || "—"}</td>
                    <td className="py-2 pl-2">
                      <span className="text-slate-300">{r.status}</span>
                      {r.reminded_at && <span className="block text-[10px] text-emerald-400">reminder sent (manual)</span>}
                    </td>
                    <td className="py-2 pl-2">
                      <div className="flex flex-wrap gap-2">
                        {statuses.filter((s) => s !== r.status).map((s) => (
                          <button key={s} className="text-sky-300 hover:text-sky-200" onClick={() => setStatus(r, s)}>
                            {s.replace("_", " ")}
                          </button>
                        ))}
                        <button className="text-slate-400 hover:text-slate-200" onClick={() => markReminded(r)}>
                          {r.reminded_at ? "reminder ✓" : "mark reminder"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-3">
        <h3 className="font-semibold">Add an appointment (phone / walk-in)</h3>
        <p className="text-xs text-slate-500">
          For customers who booked through a call or in person. Consent must be attested; the lead is created or reused.
          Time is entered in your device timezone and stored in UTC.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
          <label className="text-slate-400">
            Name
            <input className="mt-1 block w-full rounded bg-slate-800 px-2 py-1" value={manual.name}
              onChange={(e) => setManual({ ...manual, name: e.target.value })} />
          </label>
          <label className="text-slate-400">
            Phone
            <input className="mt-1 block w-full rounded bg-slate-800 px-2 py-1" value={manual.phone}
              onChange={(e) => setManual({ ...manual, phone: e.target.value })} />
          </label>
          <label className="text-slate-400">
            Email
            <input className="mt-1 block w-full rounded bg-slate-800 px-2 py-1" value={manual.email}
              onChange={(e) => setManual({ ...manual, email: e.target.value })} />
          </label>
          <label className="text-slate-400">
            Date &amp; time
            <input type="datetime-local" className="mt-1 block w-full rounded bg-slate-800 px-2 py-1" value={manual.starts_at}
              onChange={(e) => setManual({ ...manual, starts_at: e.target.value })} />
          </label>
          <label className="text-slate-400">
            Service
            <select className="mt-1 block w-full rounded bg-slate-800 px-2 py-1" value={manual.service}
              onChange={(e) => setManual({ ...manual, service: e.target.value })}>
              <option value="">—</option>
              {(availability?.services || []).map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="text-slate-400">
            Notes
            <input className="mt-1 block w-full rounded bg-slate-800 px-2 py-1" value={manual.notes}
              onChange={(e) => setManual({ ...manual, notes: e.target.value })} />
          </label>
        </div>
        <label className="flex items-start gap-2 text-xs text-slate-300">
          <input type="checkbox" className="mt-0.5" checked={manual.consent}
            onChange={(e) => setManual({ ...manual, consent: e.target.checked })} />
          <span>The customer agreed to be contacted and booked through this business.</span>
        </label>
        <button className="rounded bg-emerald-800 px-3 py-1.5 text-sm hover:bg-emerald-700 disabled:opacity-50"
          onClick={addManual} disabled={busy}>
          Add appointment
        </button>
      </div>

      {note && <p className="text-xs text-emerald-400">{note}</p>}
      {error && <p className="text-xs text-rose-400">{error}</p>}
    </div>
  );
}

function ReportsPanel() {
  const [data, setData] = useState(null);
  const [reviews, setReviews] = useState(null);
  const [referrals, setReferrals] = useState(null);
  const [attr, setAttr] = useState(null);
  const [revenue, setRevenue] = useState(null);
  const [revenueDenied, setRevenueDenied] = useState(false);
  const [spendEdits, setSpendEdits] = useState({});
  const [spendMsg, setSpendMsg] = useState("");
  const [days, setDays] = useState(30);
  const [error, setError] = useState("");

  const loadAttr = () => api(`/api/attribution/report?days=${days}`).then(setAttr).catch(() => {});

  useEffect(() => {
    api(`/api/reports/funnel?days=${days}`)
      .then(setData)
      .catch((e) => setError(e.message));
    api("/api/reviews").then((b) => setReviews(b.summary)).catch(() => {});
    api(`/api/referrals/report?days=365`).then(setReferrals).catch(() => {});
    api(`/api/reports/revenue?days=${days}`)
      .then((b) => {
        setRevenue(b);
        setRevenueDenied(false);
      })
      .catch((e) => {
        if (e && e.status === 403) setRevenueDenied(true);
      });
    loadAttr();
  }, [days]);

  const saveSpend = async (campaign) => {
    const raw = spendEdits[campaign];
    if (raw === undefined || raw === "") return;
    setSpendMsg("");
    try {
      await api("/api/campaign-spend", { method: "PUT", body: JSON.stringify({ campaign, spend: Number(raw) }) });
      setSpendMsg(`Spend saved for "${campaign}".`);
      setSpendEdits((s) => ({ ...s, [campaign]: "" }));
      loadAttr();
    } catch (e) {
      setSpendMsg(e instanceof Error ? e.message.replace(/^API \d+: /, "") : "Save failed.");
    }
  };

  if (error) return <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm text-red-400">Reports: {error}</div>;
  if (!data) return <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm text-slate-400">Loading report…</div>;

  const pct = (v) => (v === null || v === undefined ? "unknown" : `${v}%`);
  const maxReached = Math.max(1, ...data.funnel.map((f) => f.reached));
  const table = (title, rows, keyLabel) => (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <h3 className="font-semibold text-sm mb-2">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-xs text-slate-500">No data in this window.</p>
      ) : (
        <table className="w-full text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="text-left font-normal pb-1">{keyLabel}</th>
              <th className="text-right font-normal pb-1">Leads</th>
              <th className="text-right font-normal pb-1">Qualified</th>
              <th className="text-right font-normal pb-1">Converted</th>
              <th className="text-right font-normal pb-1">Qual. rate</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-t border-slate-800">
                <td className="py-1 text-slate-300">{r.key}</td>
                <td className="py-1 text-right">{r.total}</td>
                <td className="py-1 text-right">{r.qualified}</td>
                <td className="py-1 text-right">{r.converted}</td>
                <td className="py-1 text-right text-slate-400">{pct(r.qualified_rate_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <h3 className="font-semibold">Lead funnel</h3>
          <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] text-slate-300">from stage history</span>
          <select className="ml-auto rounded bg-slate-800 px-2 py-1 text-xs" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
            <p className="text-xs text-slate-500">Leads</p>
            <p className="text-xl font-semibold">{data.total_leads}</p>
          </div>
          <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
            <p className="text-xs text-slate-500">Qualified</p>
            <p className="text-xl font-semibold">{data.qualified_leads}</p>
            <p className="text-[10px] text-slate-500">{pct(data.qualified_rate_pct)}</p>
          </div>
          <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
            <p className="text-xs text-slate-500">Converted</p>
            <p className="text-xl font-semibold">{data.converted_leads}</p>
            <p className="text-[10px] text-slate-500">{pct(data.converted_rate_pct)}</p>
          </div>
          <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
            <p className="text-xs text-slate-500">Rates</p>
            <p className="text-sm font-semibold">{data.rates_known ? "usable" : "too early"}</p>
            <p className="text-[10px] text-slate-500">needs 10+ leads</p>
          </div>
        </div>
        <div className="space-y-2">
          {data.funnel.map((f) => (
            <div key={f.stage} className="flex items-center gap-2 text-xs">
              <span className="w-24 text-slate-400 capitalize">{f.stage}</span>
              <div className="flex-1 h-2 rounded bg-slate-800 overflow-hidden">
                <div className="h-2 bg-emerald-600" style={{ width: `${Math.max(2, Math.round((f.reached / maxReached) * 100))}%` }} />
              </div>
              <span className="w-28 text-right text-slate-300">
                reached {f.reached} · now {f.current}
              </span>
            </div>
          ))}
        </div>
        <ul className="list-disc list-inside text-[11px] text-slate-500 space-y-0.5">
          {data.notes.map((n) => (<li key={n}>{n}</li>))}
        </ul>
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        {table("By source", data.sources, "Source")}
        {table("By campaign", data.campaigns, "Campaign")}
      </div>
      {table("By UTM source", data.utm_sources, "UTM source")}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <h3 className="font-semibold text-sm mb-1">Reviews</h3>
          {!reviews ? (
            <p className="text-xs text-slate-500">No data.</p>
          ) : (
            <>
              <p className="text-xs text-slate-400">
                Requested {reviews.total} · completed {reviews.completed} · declined {reviews.declined} · open {reviews.requested}
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Completion rate: <b>{reviews.completion_rate_pct === null ? "unknown" : `${reviews.completion_rate_pct}%`}</b>
              </p>
              <p className="text-[11px] text-slate-500 mt-2">{reviews.note}</p>
              {reviews.sample_note && <p className="text-[11px] text-amber-500/80 mt-1">{reviews.sample_note}</p>}
            </>
          )}
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <h3 className="font-semibold text-sm mb-1">Referrals</h3>
          {!referrals ? (
            <p className="text-xs text-slate-500">No data.</p>
          ) : (
            <>
              <p className="text-xs text-slate-400">
                Referred {referrals.referrals_total} · qualified {referrals.qualified_total} · converted {referrals.converted_total}
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Conversion rate: <b>{referrals.converted_rate_pct === null ? "unknown" : `${referrals.converted_rate_pct}%`}</b>
                {!referrals.rates_known && referrals.referrals_total > 0 && " (10+ referrals needed)"}
              </p>
              {referrals.referrers.length > 0 && (
                <ul className="mt-2 space-y-1 text-xs text-slate-300">
                  {referrals.referrers.slice(0, 5).map((r) => (
                    <li key={r.lead_id} className="flex justify-between">
                      <span>{r.name}</span>
                      <span className="text-slate-400">{r.referrals} referred · {r.converted} converted</span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-[11px] text-slate-500 mt-2">
                Only link-based referrals are measured; manual word-of-mouth is outside these numbers.
              </p>
            </>
          )}
        </div>
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-semibold">Revenue &amp; ROI</h3>
          <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] text-slate-300">
            manual entries · no currency conversion
          </span>
        </div>
        {revenueDenied ? (
          <p className="text-xs text-amber-400">Owner, admin or manager role required to see revenue.</p>
        ) : !revenue ? (
          <p className="text-xs text-slate-500">No revenue data in this window.</p>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
                <p className="text-slate-500">Won deals</p>
                <p className="text-lg font-semibold">{revenue.outcomes.won_deals}</p>
              </div>
              <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
                <p className="text-slate-500">Lost deals</p>
                <p className="text-lg font-semibold">{revenue.outcomes.lost_deals}</p>
              </div>
              <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
                <p className="text-slate-500">Open pipeline</p>
                <p className="text-lg font-semibold">{revenue.outcomes.open_deals}</p>
              </div>
              <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
                <p className="text-slate-500">Win rate</p>
                <p className="text-lg font-semibold">{pct(revenue.outcomes.win_rate_pct)}</p>
              </div>
            </div>
            <p className="text-[11px] text-slate-500">
              Deals with an outcome: {revenue.coverage.leads_with_outcome}/{revenue.coverage.leads_total} (
              {pct(revenue.coverage.coverage_pct)}). Win rate stays unknown below {revenue.outcomes.rate_gate} closed
              deals in the window — never guessed.
            </p>
            {revenue.totals_by_currency.length === 0 ? (
              <p className="text-xs text-slate-500">
                No deal outcomes recorded yet — revenue is unknown, not zero.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="text-slate-500">
                    <tr>
                      <th className="text-left font-normal pb-1">Currency</th>
                      <th className="text-right font-normal pb-1 pl-2">Revenue</th>
                      <th className="text-right font-normal pb-1 pl-2">Won</th>
                      <th className="text-right font-normal pb-1 pl-2">Avg deal</th>
                      <th className="text-right font-normal pb-1 pl-2">Open value</th>
                      <th className="text-right font-normal pb-1 pl-2">Lost value</th>
                      <th className="text-right font-normal pb-1 pl-2">Spend</th>
                      <th className="text-right font-normal pb-1 pl-2">ROI</th>
                      <th className="text-right font-normal pb-1 pl-2">Cost / won</th>
                    </tr>
                  </thead>
                  <tbody>
                    {revenue.totals_by_currency.map((row) => (
                      <tr key={row.currency} className="border-t border-slate-800">
                        <td className="py-1.5 text-slate-200">{row.currency}</td>
                        <td className="py-1.5 pl-2 text-right text-slate-200">
                          {row.revenue.toLocaleString()} {row.currency}
                        </td>
                        <td className="py-1.5 pl-2 text-right text-slate-300">{row.won_deals}</td>
                        <td className="py-1.5 pl-2 text-right text-slate-400">
                          {row.avg_deal === null ? "unknown" : `${row.avg_deal.toLocaleString()} ${row.currency}`}
                        </td>
                        <td className="py-1.5 pl-2 text-right text-slate-400">
                          {row.open_value.toLocaleString()} {row.currency}
                        </td>
                        <td className="py-1.5 pl-2 text-right text-slate-400">
                          {row.lost_value.toLocaleString()} {row.currency}
                        </td>
                        <td className="py-1.5 pl-2 text-right text-slate-400">
                          {row.spend.toLocaleString()} {row.currency}
                        </td>
                        <td className="py-1.5 pl-2 text-right">
                          {row.roi_pct === null ? (
                            <span className="text-slate-500">unknown</span>
                          ) : (
                            <span className={row.roi_pct >= 0 ? "text-emerald-400" : "text-rose-400"}>
                              {row.roi_pct}%
                            </span>
                          )}
                        </td>
                        <td className="py-1.5 pl-2 text-right text-slate-400">
                          {row.cost_per_won === null
                            ? "unknown"
                            : `${row.cost_per_won.toLocaleString()} ${row.currency}`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {revenue.campaigns.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-300 mb-1">By campaign</p>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="text-slate-500">
                      <tr>
                        <th className="text-left font-normal pb-1">Campaign</th>
                        <th className="text-left font-normal pb-1 pl-2">Currency</th>
                        <th className="text-right font-normal pb-1 pl-2">Won</th>
                        <th className="text-right font-normal pb-1 pl-2">Revenue</th>
                        <th className="text-right font-normal pb-1 pl-2">Spend</th>
                        <th className="text-right font-normal pb-1 pl-2">ROI</th>
                      </tr>
                    </thead>
                    <tbody>
                      {revenue.campaigns.map((row) => (
                        <tr key={`${row.campaign}-${row.currency}`} className="border-t border-slate-800">
                          <td className="py-1.5 text-slate-200">{row.campaign}</td>
                          <td className="py-1.5 pl-2 text-slate-400">{row.currency}</td>
                          <td className="py-1.5 pl-2 text-right text-slate-300">{row.won_deals}</td>
                          <td className="py-1.5 pl-2 text-right text-slate-300">
                            {row.revenue.toLocaleString()} {row.currency}
                          </td>
                          <td className="py-1.5 pl-2 text-right text-slate-400">
                            {row.spend.toLocaleString()} {row.currency}
                          </td>
                          <td className="py-1.5 pl-2 text-right">
                            {row.roi_pct === null ? (
                              <span className="text-slate-500">unknown</span>
                            ) : (
                              <span className={row.roi_pct >= 0 ? "text-emerald-400" : "text-rose-400"}>
                                {row.roi_pct}%
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            <ul className="list-disc list-inside text-[11px] text-slate-500 space-y-0.5">
              {revenue.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </>
        )}
      </div>
      {attr && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold">Attribution &amp; spend</h3>
            <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] text-slate-300">capture-time only · no multi-touch</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
              <p className="text-slate-500">Leads</p>
              <p className="text-lg font-semibold">{attr.coverage.leads}</p>
            </div>
            <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
              <p className="text-slate-500">Campaign tagged</p>
              <p className="text-lg font-semibold">{attr.coverage.campaign_coverage_pct === null ? "unknown" : `${attr.coverage.campaign_coverage_pct}%`}</p>
            </div>
            <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
              <p className="text-slate-500">UTM tagged</p>
              <p className="text-lg font-semibold">{attr.coverage.utm_coverage_pct === null ? "unknown" : `${attr.coverage.utm_coverage_pct}%`}</p>
            </div>
            <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
              <p className="text-slate-500">Median time-to-stage</p>
              <p className="text-sm font-semibold">
                qualify {attr.median_time_to_qualify_days === null ? "unknown" : `${attr.median_time_to_qualify_days}d`}
                {" · "}convert {attr.median_time_to_convert_days === null ? "unknown" : `${attr.median_time_to_convert_days}d`}
              </p>
            </div>
          </div>
          <table className="w-full text-xs">
            <thead className="text-slate-500">
              <tr>
                <th className="text-left font-normal pb-1">Campaign</th>
                <th className="text-right font-normal pb-1">Leads</th>
                <th className="text-right font-normal pb-1">Qualified</th>
                <th className="text-right font-normal pb-1">Converted</th>
                <th className="text-right font-normal pb-1">Spend (PKR)</th>
                <th className="text-right font-normal pb-1">Cost/lead</th>
                <th className="text-right font-normal pb-1">Cost/qual.</th>
                <th className="text-right font-normal pb-1">Cost/conv.</th>
              </tr>
            </thead>
            <tbody>
              {attr.campaigns.map((c) => (
                <tr key={c.campaign} className="border-t border-slate-800">
                  <td className="py-1 text-slate-300">{c.campaign}</td>
                  <td className="py-1 text-right">{c.leads}</td>
                  <td className="py-1 text-right">{c.qualified}</td>
                  <td className="py-1 text-right">{c.converted}</td>
                  <td className="py-1 text-right">
                    {c.campaign === "(unattributed)" ? (
                      <span className="text-slate-500">—</span>
                    ) : (
                      <span className="flex items-center justify-end gap-1">
                        <input
                          className="w-20 rounded bg-slate-800 px-2 py-0.5 text-right"
                          type="number" min="0" placeholder={c.spend === null ? "not set" : String(c.spend)}
                          value={spendEdits[c.campaign] ?? ""}
                          onChange={(e) => setSpendEdits((s) => ({ ...s, [c.campaign]: e.target.value }))}
                        />
                        <button className="text-[10px] text-sky-400 hover:text-sky-300" onClick={() => saveSpend(c.campaign)}>Save</button>
                      </span>
                    )}
                  </td>
                  <td className="py-1 text-right text-slate-400">{c.cost_per_lead === null ? "unknown" : c.cost_per_lead}</td>
                  <td className="py-1 text-right text-slate-400">{c.cost_per_qualified === null ? "unknown" : c.cost_per_qualified}</td>
                  <td className="py-1 text-right text-slate-400">{c.cost_per_conversion === null ? "unknown" : c.cost_per_conversion}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {spendMsg && <p className="text-xs text-emerald-400">{spendMsg}</p>}
          <ul className="list-disc list-inside text-[11px] text-slate-500 space-y-0.5">
            {attr.notes.map((n) => (<li key={n}>{n}</li>))}
          </ul>
        </div>
      )}
    </div>
  );
}

function AnalyticsCard() {
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);
  const [error, setError] = useState("");

  useEffect(() => {
    api(`/api/analytics/summary?days=${days}`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [days]);

  if (error) return <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-xs text-red-400">Analytics: {error}</div>;
  if (!data) return <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm text-slate-400">Loading analytics…</div>;

  const f = data.funnel;
  const bar = (value, max) => (max > 0 ? `${Math.max(2, Math.round((value / max) * 100))}%` : "0%");
  const rate = (v) => (v === null || v === undefined ? "unknown" : `${v}%`);

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="font-semibold">Website analytics</h3>
        <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] text-slate-300">cookie-free · first-party</span>
        <select className="ml-auto rounded bg-slate-800 px-2 py-1 text-xs" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
          <p className="text-xs text-slate-500">Sessions</p>
          <p className="text-xl font-semibold">{data.sessions_total}</p>
        </div>
        <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
          <p className="text-xs text-slate-500">Page views</p>
          <p className="text-xl font-semibold">{data.event_counts.page_view}</p>
        </div>
        <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
          <p className="text-xs text-slate-500">Form starts</p>
          <p className="text-xl font-semibold">{f.form_start_sessions}</p>
        </div>
        <div className="rounded-lg bg-slate-950 border border-slate-800 p-3">
          <p className="text-xs text-slate-500">Leads captured</p>
          <p className="text-xl font-semibold">{data.leads_captured}</p>
        </div>
      </div>
      <div className="space-y-2">
        <p className="text-xs text-slate-500">Funnel (unique sessions)</p>
        {[
          ["Visited page", f.page_view_sessions],
          ["Started the form", f.form_start_sessions],
          ["Submitted", f.submit_sessions],
        ].map(([label, value]) => (
          <div key={label} className="flex items-center gap-2 text-xs">
            <span className="w-32 text-slate-400">{label}</span>
            <div className="flex-1 h-2 rounded bg-slate-800 overflow-hidden">
              <div className="h-2 bg-sky-600" style={{ width: bar(value, f.page_view_sessions) }} />
            </div>
            <span className="w-10 text-right text-slate-300">{value}</span>
          </div>
        ))}
      </div>
      <p className="text-xs text-slate-400">
        Form-start rate: <b>{rate(data.form_start_rate_pct)}</b> · Submit rate: <b>{rate(data.submit_rate_pct)}</b>
        {!data.rates_known && data.sessions_total > 0 && " (need 30+ sessions before rates mean anything)"}
      </p>
      {data.notes.length > 0 && (
        <ul className="list-disc list-inside text-[11px] text-slate-500 space-y-0.5">
          {data.notes.map((n) => (<li key={n}>{n}</li>))}
        </ul>
      )}
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
  // P7 #1: custom block pages live at /p/<slug>, also public and auth-free.
  const pageMatch = /^\/p\/([a-z0-9-]+)\/?$/.exec(window.location.pathname);
  if (pageMatch) return <BlockPage slug={pageMatch[1]} />;
  // Public landing pages live at /l/<slug> — render them with no dashboard,
  // no auth state, and no dashboard data in the bundle path.
  const landingMatch = /^\/l\/([a-z0-9-]+)\/?$/.exec(window.location.pathname);
  if (landingMatch) return <LandingPage slug={landingMatch[1]} />;
  return <DashboardApp />;
}

function DashboardApp() {
  const [user, setUser] = useState(getUser());
  const [active, setActive] = useState("Dashboard");
  // One-time welcome tour: only a successful registration opens it. The flag is
  // remembered per account so a refresh can never replay it.
  const [showIntro, setShowIntro] = useState(false);
  const handleAuthed = (nextUser, opts = {}) => {
    setUser(nextUser);
    if (!opts.isNew) return;
    let alreadySeen = false;
    try {
      const key = `lc_intro_seen_${nextUser.id}`;
      alreadySeen = Boolean(localStorage.getItem(key));
      if (!alreadySeen) localStorage.setItem(key, "1");
    } catch {
      /* private mode: show it once for this session */
    }
    if (!alreadySeen) setShowIntro(true);
  };
  // White-label (P3 #2): the header follows the workspace's branding. Read
  // errors are ignored — the default platform name is the honest fallback.
  const [brand, setBrand] = useState(null);
  useEffect(() => {
    if (!user) return;
    api("/api/settings")
      .then((b) => setBrand(b.settings))
      .catch(() => {});
  }, [user]);

  if (!user) return <AuthScreen onAuthed={handleAuthed} />;

  if (showIntro) {
    return (
      <WelcomeIntro
        user={user}
        onDone={() => setShowIntro(false)}
        onGo={(tab) => {
          setShowIntro(false);
          setActive(tab);
        }}
      />
    );
  }

  const brandText = displayBrandName(brand?.brand_name, "");
  const brandName = brandText || (brand?.hide_platform_brand ? user.business_name : "LeadCraft AI");
  const tagline = brand?.hide_platform_brand ? user.business_name : "AI content · compliant leads · CRM";

  const navItems = user.is_admin ? [...NAV_ITEMS, "Admin"] : NAV_ITEMS;
  const logout = () => {
    clearSession();
    setUser(null);
  };

  return (
    <div className="min-h-screen flex">
      <aside className="w-56 shrink-0 border-r border-slate-800 p-4">
        {brand?.logo_url ? (
          <img src={brand.logo_url} alt={brandName} className="max-h-8 mb-1" />
        ) : (
          <h1 className="text-lg font-bold mb-1">{brandName}</h1>
        )}
        <p className="text-xs text-slate-400 mb-2">{tagline}</p>
        {user.is_workspace_member && (
          <p className="text-[11px] text-slate-500 mb-4">
            {user.business_name} team · <span className="text-slate-300">{user.role}</span>
          </p>
        )}
        {!user.is_workspace_member && <div className="mb-2" />}
        <nav className="space-y-1">
          {navItems.map((item) => (
            <button
              key={item}
              onClick={() => setActive(item)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm ${
                active === item ? "bg-sky-600 text-white" : "text-slate-300 hover:bg-slate-800"
              }`}
              style={active === item && brand?.primary_color && /^#[0-9a-fA-F]{6}$/.test(brand.primary_color)
                ? { backgroundColor: brand.primary_color }
                : undefined}
            >
              {item}
            </button>
          ))}
        </nav>
      </aside>
      <main className="flex-1 p-8">
        <h2 className="text-2xl font-bold mb-4">{active}</h2>
        {active === "Dashboard" && (
          <div className="space-y-4">
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm">
              <p className="text-emerald-400 font-semibold">Connected</p>
              <p className="mt-2 text-slate-300">
                Welcome back, {user.business_name}. Use <b>Settings</b> to define your niche and brand voice, then{" "}
                <b>Content</b> to generate and schedule posts.
              </p>
              <p className="mt-2 text-xs text-slate-500">Tip: use <b>Inbox</b> (Conversations) to track consented chats, and <b>Leads</b> for stages, BANT, scoring and timelines.</p>
              {user.role === "viewer" && (
                <p className="mt-2 text-xs text-amber-400">
                  Read-only role: you can view this workspace, but every write is blocked by the server.
                </p>
              )}
            </div>
            <AnalyticsCard />
          </div>
        )}
        {active === "Content" && <ContentPanel />}
        {active === "Leads" && <LeadsPanel />}
        {active === "Appointments" && <AppointmentsPanel />}
        {active === "Reports" && <ReportsPanel />}
        {active === "Settings" && <SettingsPanel user={user} onLogout={logout} />}
        {active === "Admin" && <AdminPanel />}
        {active === "Conversations" && <InboxPanel />}
      </main>
    </div>
  );
}
