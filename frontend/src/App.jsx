import { useEffect, useState } from "react";
import { api, clearSession, getToken, getUser, setSession } from "./api/client";

const PLATFORMS = ["facebook", "instagram", "tiktok", "whatsapp_status", "other"];
const NAV_ITEMS = ["Dashboard", "Content", "Leads", "Conversations", "Reports", "Settings"];

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
      <IcpEditor />
      <AbEditor />
      <NurtureEditor />
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
              <h1 className="text-2xl font-bold">
                {config.variant?.headline || config.business_name}
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
              {busy ? "Sending…" : (config.variant?.cta_label || "Request a callback")}
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

function ReportsPanel() {
  const [data, setData] = useState(null);
  const [reviews, setReviews] = useState(null);
  const [referrals, setReferrals] = useState(null);
  const [days, setDays] = useState(30);
  const [error, setError] = useState("");

  useEffect(() => {
    api(`/api/reports/funnel?days=${days}`)
      .then(setData)
      .catch((e) => setError(e.message));
    api("/api/reviews").then((b) => setReviews(b.summary)).catch(() => {});
    api(`/api/referrals/report?days=365`).then(setReferrals).catch(() => {});
  }, [days]);

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
          <div className="space-y-4">
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-sm">
              <p className="text-emerald-400 font-semibold">Connected</p>
              <p className="mt-2 text-slate-300">
                Welcome back, {user.business_name}. Use <b>Settings</b> to define your niche and brand voice, then{" "}
                <b>Content</b> to generate and schedule posts.
              </p>
              <p className="mt-2 text-xs text-slate-500">Tip: use <b>Inbox</b> (Conversations) to track consented chats, and <b>Leads</b> for stages, BANT, scoring and timelines.</p>
            </div>
            <AnalyticsCard />
          </div>
        )}
        {active === "Content" && <ContentPanel />}
        {active === "Leads" && <LeadsPanel />}
        {active === "Reports" && <ReportsPanel />}
        {active === "Settings" && <SettingsPanel user={user} onLogout={logout} />}
        {active === "Admin" && <AdminPanel />}
        {active === "Conversations" && <InboxPanel />}
      </main>
    </div>
  );
}
