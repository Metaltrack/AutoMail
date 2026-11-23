/* AutoMail web UI - plain JavaScript, no build step.
   Views: compose, outbox, contacts, dashboard, settings. Routing uses the URL hash.
   Every view is a two-column "work" area: the main task on the left and a
   working side column (preview, details, groups, quota) on the right. */
(() => {
  "use strict";

  // ======================================================================
  // Helpers
  // ======================================================================

  /** h("div", {class: "x", onclick: fn}, child, ...) - builds DOM without innerHTML. */
  function h(tag, props, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "icon") el.insertAdjacentHTML("afterbegin", ICONS[v] || "");
      else if (k === "style") el.style.cssText = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k in el && typeof v !== "string") el[k] = v;
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat(Infinity)) {
      if (c === null || c === undefined || c === false) continue;
      el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return el;
  }
  /** replaceChildren that skips null/false (the native one would print "null"). */
  const put = (el, ...kids) => el.replaceChildren(...kids.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false));
  const $ = (sel, root = document) => root.querySelector(sel);
  const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/;
  const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + "s")}`;
  const lowerFirst = (s) => s.charAt(0).toLowerCase() + s.slice(1);
  const fmtSize = (b) => (b < 1024 ? b + " B" : b < 1048576 ? (b / 1024).toFixed(0) + " KB" : (b / 1048576).toFixed(1) + " MB");
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { v === null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } },
  };

  const ICONS = {
    compose: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4z"/><path d="M13.5 6.5l4 4"/></svg>',
    outbox: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>',
    contacts: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7"/><path d="M18.5 14.5A6.5 6.5 0 0 1 21.5 20"/></svg>',
    dashboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/></svg>',
    settings: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>',
    file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/></svg>',
    x: '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    logout: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg>',
    info: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v5h1"/></svg>',
    table: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18M9 4v16"/></svg>',
    envelope: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="1.5"/><path d="M3 7l9 6 9-6"/></svg>',
  };
  const BRAND = '<svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="5" fill="#f2b705"/><path d="M7 11l9 6.5 9-6.5M7 11v11h18V11" fill="none" stroke="#1b2a4a" stroke-width="2.2" stroke-linejoin="round"/></svg>';

  let toastTimer;
  function toast(msg, isError) {
    const t = $("#toast");
    t.textContent = msg;
    t.className = "toast show" + (isError ? " err" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (t.className = "toast"), isError ? 4500 : 2800);
  }

  function fmtWhen(ts) {
    if (!ts) return "";
    const d = new Date(ts * 1000), now = new Date();
    const diffMin = Math.round((d - now) / 60000);
    const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    if (Math.abs(diffMin) < 1) return "Just now";
    if (diffMin < 0 && diffMin > -60) return `${-diffMin} min ago`;
    if (diffMin > 0 && diffMin < 60) return `In ${diffMin} min`;
    const dayDiff = Math.round((new Date(d).setHours(0, 0, 0, 0) - new Date(now).setHours(0, 0, 0, 0)) / 86400000);
    if (dayDiff === 0) return `Today, ${time}`;
    if (dayDiff === 1) return `Tomorrow, ${time}`;
    if (dayDiff === -1) return `Yesterday, ${time}`;
    return d.toLocaleDateString([], { day: "numeric", month: "short" }) + ", " + time;
  }

  /** Same mail-merge rules as the server: {Name}, { name }, {first_name} ... */
  function fill(text, vars, escapeHtml) {
    const norm = (k) => k.replace(/[\s_]+/g, "").toLowerCase();
    const lookup = {};
    for (const [k, v] of Object.entries(vars || {})) lookup[norm(k)] = String(v);
    return text.replace(/\{\s*([A-Za-z0-9_ .-]+?)\s*\}/g, (m, k) => {
      const v = lookup[norm(k)];
      if (v === undefined) return m;
      return escapeHtml ? v.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])) : v;
    });
  }

  /** A titled panel ("form sheet"): panel("Title", actions, ...body) */
  function panel(title, actions, ...body) {
    return h("section", { class: "panel" },
      h("div", { class: "panel-title" }, typeof title === "string" ? h("h2", {}, title) : title, actions || null),
      ...body);
  }
  const pbody = (...kids) => h("div", { class: "panel-body" }, ...kids);

  // ======================================================================
  // API
  // ======================================================================

  const session = { token: store.get("automail-token"), me: null, health: null };

  async function api(path, opts = {}) {
    const headers = { "Content-Type": "application/json" };
    if (session.token) headers.Authorization = "Bearer " + session.token;
    let res;
    try {
      res = await fetch(path, { method: opts.method || (opts.body ? "POST" : "GET"), headers,
        body: opts.body ? JSON.stringify(opts.body) : undefined });
    } catch {
      throw new Error("Can't reach the AutoMail server. Check that AutoMailAPI.py is running.");
    }
    const data = await res.json().catch(() => null);
    if (res.status === 401 && path !== "/api/login") {
      logout(true);
      throw new Error("Your session ended. Please sign in again.");
    }
    if (!res.ok) {
      let msg = data && data.detail;
      if (Array.isArray(msg)) msg = msg.map((d) => (d.msg || "").replace(/^Value error, /, "")).join("; ");
      throw Object.assign(new Error(msg || `Request failed (HTTP ${res.status})`), { status: res.status });
    }
    return data;
  }

  function logout(silent) {
    if (session.token && !silent) api("/api/logout", { method: "POST" }).catch(() => {});
    session.token = null;
    session.me = null;
    store.set("automail-token", null);
    stopPolling();
    renderLogin();
  }

  // ======================================================================
  // Login
  // ======================================================================

  /** Sign-in, sign-up, forgot password, email confirmation and reset all share one shell.
      view: signin | signup | forgot | sent | verify | reset.  ctx carries a token, a notice, an email... */
  async function renderLogin(view = "signin", ctx = {}) {
    if (!session.config) {
      try { session.config = await api("/api/config"); } catch { session.config = { signup: false, password_min: 8 }; }
    }
    const cfg = session.config;
    const note = h("div", { class: "alert ok", hidden: !ctx.notice, role: "status" }, ctx.notice || "");
    const err = h("div", { class: "alert", hidden: true, role: "alert" });
    const fail = (ex) => { err.textContent = ex.message; err.hidden = false; };
    const go = (v, c) => renderLogin(v, c);
    const linkBtn = (text, fn) => h("button", { class: "link-btn", type: "button", onclick: fn }, text);
    const field = (id, label, props, hint) => {
      const input = h("input", { class: "input", id, ...props });
      return [h("div", {}, h("label", { class: "label", for: id }, label, hint ? h("small", {}, hint) : null), input), input];
    };
    /** A form that disables its button while the request runs and shows errors in `err`. */
    const form = (btnText, run, ...kids) => {
      const btn = h("button", { class: "btn primary lg block", type: "submit" }, btnText);
      return h("form", { class: "stack", novalidate: true, onsubmit: async (e) => {
        e.preventDefault();
        err.hidden = true;
        btn.disabled = true;
        try { await run(); } catch (ex) { fail(ex); } finally { btn.disabled = false; }
      } }, note, err, ...kids, btn);
    };
    const dryNote = (r) => (r && r.dry_run
      ? h("p", { class: "hint" }, "Practice mode is on, so no real email is sent. The link is printed in the server window.") : null);

    let body;
    if (view === "signin") {
      const [uBox, user] = field("u", "Username or email", { autocomplete: "username", required: true });
      const [pBox, pass] = field("p", "Password", { type: "password", autocomplete: "current-password", required: true });
      const resend = h("div", { hidden: true }, linkBtn("Resend the confirmation email", async () => {
        try { const r = await api("/api/resend-verification", { body: { identifier: user.value.trim() } });
          toast("If that account is waiting for confirmation, a new email is on its way."); if (r.dry_run) toast("Practice mode: check the server window for the link."); }
        catch (ex) { fail(ex); }
      }));
      body = [form("Sign in", async () => {
        resend.hidden = true;
        try {
          const r = await api("/api/login", { body: { username: user.value.trim(), password: pass.value } });
          session.token = r.token;
          store.set("automail-token", r.token);
          await boot();
        } catch (ex) {
          if (ex.status === 403) resend.hidden = false;
          pass.select();
          throw ex;
        }
      }, h("div", {}, h("h2", {}, "Sign in"), h("p", { class: "muted small" }, "Welcome back.")),
        uBox, pBox, resend),
        h("div", { class: "auth-links" }, linkBtn("Forgot password?", () => go("forgot")),
          cfg.signup ? linkBtn("Create an account", () => go("signup")) : null)];
      setTimeout(() => user.focus());
    } else if (view === "signup") {
      const [uBox, user] = field("su", "Username", { autocomplete: "username", required: true, maxlength: 40 }, "letters, numbers, . _ -");
      const [eBox, email] = field("se", "Email", { type: "email", autocomplete: "email", required: true },
        cfg.email_domains && cfg.email_domains.length ? cfg.email_domains.map((d) => "@" + d).join(", ") : null);
      const [pBox, pass] = field("sp", "Password", { type: "password", autocomplete: "new-password", required: true }, `at least ${cfg.password_min} characters`);
      body = [form("Create account", async () => {
        if (!EMAIL_RE.test(email.value.trim())) throw new Error("Enter a valid email address.");
        if (pass.value.length < cfg.password_min) throw new Error(`The password needs at least ${cfg.password_min} characters.`);
        const r = await api("/api/signup", { body: { username: user.value.trim(), email: email.value.trim(), password: pass.value } });
        go("sent", { email: email.value.trim(), dry: r });
      }, h("div", {}, h("h2", {}, "Create your account"), h("p", { class: "muted small" }, "We'll email a link to confirm your address.")),
        uBox, eBox, pBox),
        h("div", { class: "auth-links" }, linkBtn("I already have an account", () => go("signin")))];
      setTimeout(() => user.focus());
    } else if (view === "forgot") {
      const [eBox, email] = field("fe", "Email", { type: "email", autocomplete: "email", required: true });
      body = [form("Send reset link", async () => {
        if (!EMAIL_RE.test(email.value.trim())) throw new Error("Enter a valid email address.");
        const r = await api("/api/forgot-password", { body: { email: email.value.trim() } });
        go("sent", { email: email.value.trim(), dry: r, reset: true });
      }, h("div", {}, h("h2", {}, "Forgot your password?"), h("p", { class: "muted small" }, "Enter your email and we'll send a link to choose a new one.")), eBox),
        h("div", { class: "auth-links" }, linkBtn("Back to sign in", () => go("signin")))];
      setTimeout(() => email.focus());
    } else if (view === "sent") {
      body = [h("div", { class: "stack" },
        h("h2", {}, "Check your inbox"),
        h("p", {}, ctx.reset ? "If an account uses " : "We sent a confirmation link to ", h("b", {}, ctx.email),
          ctx.reset ? ", a reset link is on its way." : "."),
        h("p", { class: "muted small" }, "It can take a minute. Look in spam too. The link works once."),
        dryNote(ctx.dry)),
        h("div", { class: "auth-links" }, linkBtn("Back to sign in", () => go("signin")))];
    } else if (view === "verify") {
      const status = h("p", {}, "Confirming your email...");
      body = [h("div", { class: "stack" }, h("h2", {}, "Email confirmation"), status, err),
        h("div", { class: "auth-links" }, linkBtn("Go to sign in", () => go("signin")))];
      api("/api/verify-email", { body: { token: ctx.token } }).then(
        (r) => go("signin", { notice: `Email confirmed, ${r.username}. You can sign in now.` }),
        (ex) => { status.textContent = ""; fail(ex); });
    } else if (view === "reset") {
      const [pBox, pass] = field("rp1", "New password", { type: "password", autocomplete: "new-password", required: true }, `at least ${cfg.password_min} characters`);
      const [cBox, again] = field("rp2", "Repeat it", { type: "password", autocomplete: "new-password", required: true });
      body = [form("Set new password", async () => {
        if (pass.value.length < cfg.password_min) throw new Error(`The password needs at least ${cfg.password_min} characters.`);
        if (pass.value !== again.value) throw new Error("The two passwords don't match.");
        await api("/api/reset-password", { body: { token: ctx.token, password: pass.value } });
        go("signin", { notice: "Password changed. Sign in with the new one." });
      }, h("div", {}, h("h2", {}, "Choose a new password")), pBox, cBox),
        h("div", { class: "auth-links" }, linkBtn("Request a new link", () => go("forgot")))];
      setTimeout(() => pass.focus());
    }
    const formPane = h("div", { class: "auth-pane" }, ...body);

    const brand = h("div", { class: "brand" });
    brand.innerHTML = BRAND;
    brand.append(h("b", {}, "AutoMail"));
    put($("#app"), h("main", { class: "login" },
      h("section", { class: "login-art" },
        h("div", {}, brand,
          h("h1", {}, "Notices that post themselves."),
          h("p", {}, "Write once, then send to a whole class, schedule it for tomorrow morning, or let another app trigger it."),
          h("ul", {},
            h("li", {}, "Schedule and repeat reminders"),
            h("li", {}, "Mail merge marks and names from a CSV"),
            h("li", {}, "Retries and daily limits handled for you"))),
        h("p", { class: "small" }, "Dr. Post is on duty.")),
      h("section", { class: "login-form" }, formPane)));
  }

  // ======================================================================
  // Shell
  // ======================================================================

  const ROUTES = {
    compose: { label: "Compose", render: viewCompose },
    outbox: { label: "Outbox", render: viewOutbox },
    contacts: { label: "Contacts", render: viewContacts },
    dashboard: { label: "Dashboard", render: viewDashboard },
    settings: { label: "Settings", render: viewSettings },
  };
  const currentRoute = () => {
    const r = location.hash.replace(/^#\/?/, "").split("/")[0];
    return ROUTES[r] ? r : "compose";
  };

  /** Postmark ring: share of today's sending limit already used. */
  function postmark(usage, dark) {
    const used = usage ? usage.sent_24h : 0, limit = usage ? usage.daily_limit : 450;
    const frac = Math.min(1, used / Math.max(1, limit));
    const r = 24, c = 2 * Math.PI * r;
    const ring = frac > 0.85 ? "#c8312b" : (dark ? "#f2b705" : "#2f55d4");
    const track = dark ? "rgba(255,255,255,.15)" : "#e8ecf2";
    const text = dark ? "#ffffff" : "#172238";
    return `<svg viewBox="0 0 64 64" role="img" aria-label="${used} of ${limit} mails used in the last 24 hours">
      <circle cx="32" cy="32" r="30" fill="none" stroke="${dark ? "rgba(255,255,255,.35)" : "#c3ccd9"}" stroke-width="1.5" stroke-dasharray="3 3"/>
      <circle cx="32" cy="32" r="${r}" fill="none" stroke="${track}" stroke-width="5"/>
      <circle cx="32" cy="32" r="${r}" fill="none" stroke="${ring}" stroke-width="5" stroke-linecap="round"
        stroke-dasharray="${(c * frac).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 32 32)"/>
      <text x="32" y="37" text-anchor="middle" font-family="Plus Jakarta Sans, sans-serif" font-weight="800" font-size="15" fill="${text}">${used}</text>
    </svg>`;
  }

  function renderShell() {
    const me = session.me;
    const brand = h("a", { class: "brand", href: "#/compose" });
    brand.innerHTML = BRAND;
    brand.append(h("b", {}, "AutoMail"));
    const tabs = h("nav", { class: "tabs", "aria-label": "Main" },
      Object.entries(ROUTES).map(([key, r]) =>
        h("a", { href: "#/" + key, "data-route": key, icon: key },
          h("span", { class: "label-text" }, r.label),
          key === "outbox" ? h("span", { class: "count", id: "nav-active", hidden: true }) : null)));
    put($("#app"),
      h("header", { class: "topbar" },
        h("div", { class: "topbar-inner" }, brand, tabs,
          h("div", { class: "top-right" },
            h("div", { class: "quota-chip", id: "quota-chip", title: "Mails sent in the last 24 hours" }),
            h("div", { class: "who" },
              h("div", { class: "avatar", "aria-hidden": "true" }, me.username[0].toUpperCase()),
              h("div", { class: "name" }, me.username, h("small", {}, me.role === "admin" ? "Admin" : "Sender")),
              h("button", { class: "btn ghost icon", title: "Sign out", "aria-label": "Sign out", icon: "logout", onclick: () => logout() }))))),
      h("div", { class: "stripe", "aria-hidden": "true" }),
      h("main", { class: "main", id: "main" }));
    refreshHealth();
  }

  async function refreshHealth() {
    try {
      const hl = await api("/health");
      session.health = hl;
      const chip = $("#quota-chip");
      if (chip) {
        chip.innerHTML = postmark(hl, true);
        chip.append(h("div", { class: "qt" }, h("b", {}, `${hl.sent_24h} / ${hl.daily_limit}`), "sent today"));
      }
      const badge = $("#nav-active");
      if (badge) { badge.hidden = !hl.pending; badge.textContent = hl.pending; }
    } catch { /* offline: keep old values */ }
  }

  let currentPage = null;
  function navigate() {
    if (!session.me) return;
    stopPolling();
    if (currentPage && currentPage.cleanup) currentPage.cleanup();
    const route = currentRoute();
    document.querySelectorAll(".tabs a").forEach((a) =>
      a.dataset.route === route ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
    const main = $("#main");
    put(main,
      session.me.dry_run ? h("div", { class: "dry-banner", icon: "info" },
        h("span", {}, h("b", {}, "Practice mode. "),
          "Mail is logged on the server but not delivered. Addresses ending in @fail.test fail on purpose so you can see retries. Set DRY_RUN=false in .env to send for real.")) : null);
    const page = h("div", { class: "page" });
    currentPage = page;
    main.append(page);
    document.title = ROUTES[route].label + " · AutoMail";
    ROUTES[route].render(page);
    refreshHealth();
    window.scrollTo(0, 0);
  }

  let pollTimer = null;
  function poll(fn, ms) { stopPolling(); pollTimer = setInterval(fn, ms); }
  function stopPolling() { clearInterval(pollTimer); clearInterval(detailTimer); pollTimer = null; }

  const STATUS_TEXT = { scheduled: "Scheduled", queued: "Queued", sending: "Sending", done: "Delivered", partial: "Partly failed",
    failed: "Failed", cancelled: "Cancelled", sent: "Sent", pending: "Waiting" };
  const badge = (status) => h("span", { class: "badge " + (status === "queued" ? "sending" : status) }, STATUS_TEXT[status] || status);
  /** A "scheduled" job whose time has come is just waiting for the next queue tick. */
  const shownStatus = (j) => (j.status === "scheduled" && j.scheduled_at <= Date.now() / 1000 + 5 ? "queued" : j.status);
  function progress(j) {
    const t = Math.max(1, j.total);
    return h("div", { class: "progress", role: "img", "aria-label": `${j.sent} sent, ${j.failed} failed of ${j.total}` },
      j.sent ? h("i", { class: "s", style: `width:${(j.sent / t) * 100}%` }) : null,
      j.failed ? h("i", { class: "f", style: `width:${(j.failed / t) * 100}%` }) : null);
  }

  /** Side-panel list of the next scheduled mails (used on several pages). */
  function upcomingPanel() {
    const list = h("ul", { class: "mini" });
    api("/api/jobs?limit=100").then((jobs) => {
      const next = jobs.filter((j) => j.status === "scheduled").sort((a, b) => a.scheduled_at - b.scheduled_at).slice(0, 5);
      put(list, next.length ? next.map((j) => h("li", { class: "link", tabindex: "0", onclick: () => (location.hash = "#/outbox/" + j.id) },
        h("div", { class: "grow" }, h("div", { class: "t" }, j.subject),
          h("div", { class: "s" }, fmtWhen(j.scheduled_at) + (j.repeat !== "none" ? ` · repeats ${j.repeat}` : ""))),
        h("span", { class: "small muted" }, j.total)))
        : h("li", { class: "mini-empty" }, "Nothing scheduled. Pick “Schedule” when composing to send later."));
    }).catch(() => {});
    return panel("Coming up", h("a", { class: "small", href: "#/outbox" }, "Outbox"), h("div", { class: "panel-body tight" }, list));
  }

  // ======================================================================
  // Compose
  // ======================================================================

  const TEMPLATES = {
    "Event reminder": {
      subject: "Reminder: {event} tomorrow",
      plain: "Hello {name},\n\nThis is a reminder that {event} is tomorrow at {time} in {place}.\n\nSee you there!",
      html: "<p>Hello {name},</p>\n<p>This is a reminder that <b>{event}</b> is tomorrow at <b>{time}</b> in <b>{place}</b>.</p>\n<p>See you there!</p>",
    },
    "Assignment deadline": {
      subject: "Due {date}: {assignment}",
      plain: "Hi {name},\n\n{assignment} is due on {date}. Please submit it before the deadline.\n\nThank you.",
      html: "<p>Hi {name},</p>\n<p><b>{assignment}</b> is due on <b>{date}</b>. Please submit it before the deadline.</p>",
    },
    "Result notice": {
      subject: "Your {exam} result",
      plain: "Dear {name},\n\nYou scored {marks} in {exam}.\n\nRegards,\nExam cell",
      html: "<p>Dear {name},</p>\n<p>You scored <b>{marks}</b> in {exam}.</p>\n<p>Regards,<br>Exam cell</p>",
    },
    "Meeting invite": {
      subject: "Meeting: {topic}",
      plain: "Hello {name},\n\nLet's meet on {date} at {time} to discuss {topic}. Reply if you can't make it.",
      html: "<p>Hello {name},</p>\n<p>Let's meet on <b>{date}</b> at <b>{time}</b> to discuss {topic}. Reply if you can't make it.</p>",
    },
  };

  function tomorrowAtNine() {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T09:00`;
  }
  const newDraft = () => ({ to: [], groups: [], csv: null, subject: "", body: "", format: "plain", replyTo: "",
    attachments: [], delivery: "now", sendAt: tomorrowAtNine(), repeat: "none", previewAs: 0 });
  let draft = newDraft();
  let groupCache = [];
  let presetGroup = null; // set by "Write to this group" on the Contacts page

  function viewCompose(page) {
    let lastField = null; // where a clicked {placeholder} goes
    if (presetGroup && !draft.groups.includes(presetGroup)) draft.groups.push(presetGroup);
    presetGroup = null;

    // ----- recipients -----
    const toInput = h("input", { type: "email", id: "to", autocomplete: "off", placeholder: "Type an email and press Enter",
      "aria-describedby": "to-hint" });
    const chips = h("div", { class: "chips", onclick: () => toInput.focus() });
    const toHint = h("div", { class: "hint", id: "to-hint" });
    const groupSelect = h("select", { class: "select", "aria-label": "Add a contact group", style: "width:auto;padding:5px 8px;font-size:13px" });

    function addAddresses(text) {
      for (const p of text.split(/[,;\s]+/).map((s) => s.trim()).filter(Boolean)) {
        if (!draft.to.some((a) => a.toLowerCase() === p.toLowerCase())) draft.to.push(p);
      }
      update();
    }
    const chip = (cls, label, title, onRemove) => h("span", { class: "chip " + cls, title },
      h("span", {}, label),
      h("button", { type: "button", "aria-label": "Remove " + title, icon: "x", onclick: (e) => { e.stopPropagation(); onRemove(); } }));
    function drawChips() {
      put(chips,
        draft.groups.map((g) => {
          const info = groupCache.find((x) => x.name === g);
          return chip("group", `${g} (${info ? info.members : "?"})`, "group " + g, () => { draft.groups = draft.groups.filter((x) => x !== g); update(); });
        }),
        draft.csv && chip("csv", `${draft.csv.name}: ${plural(draft.csv.rows.length, "row")}`, "CSV " + draft.csv.name, () => { draft.csv = null; update(); }),
        draft.to.map((a, i) => chip(EMAIL_RE.test(a) ? "" : "bad", a, a, () => { draft.to.splice(i, 1); update(); })),
        toInput);
      const bad = draft.to.filter((a) => !EMAIL_RE.test(a)).length;
      toHint.className = "hint" + (bad ? " err" : "");
      toHint.textContent = bad
        ? `${plural(bad, "address")} in red ${bad === 1 ? "looks" : "look"} wrong. Fix or remove ${bad === 1 ? "it" : "them"}.`
        : "Separate addresses with Enter or commas. You can paste a whole list.";
    }

    toInput.addEventListener("keydown", (e) => {
      if (["Enter", ",", ";"].includes(e.key) && toInput.value.trim()) { e.preventDefault(); addAddresses(toInput.value); toInput.value = ""; }
      else if (e.key === "Backspace" && !toInput.value && draft.to.length) { draft.to.pop(); update(); }
    });
    toInput.addEventListener("input", () => {
      const v = toInput.value, cut = Math.max(v.lastIndexOf(","), v.lastIndexOf(";"));
      if (cut >= 0) { addAddresses(v.slice(0, cut)); toInput.value = v.slice(cut + 1).trimStart(); }
    });
    toInput.addEventListener("paste", (e) => {
      const text = e.clipboardData.getData("text");
      if (/[,;\s]/.test(text.trim())) { e.preventDefault(); addAddresses(text); }
    });
    toInput.addEventListener("blur", () => { if (toInput.value.trim()) { addAddresses(toInput.value); toInput.value = ""; } });

    groupSelect.addEventListener("change", () => {
      const g = groupSelect.value;
      if (g && !draft.groups.includes(g)) draft.groups.push(g);
      groupSelect.value = "";
      update();
    });
    api("/api/groups").then((groups) => {
      groupCache = groups;
      put(groupSelect, h("option", { value: "" }, groups.length ? "Add a group" : "No groups yet"),
        groups.map((g) => h("option", { value: g.name }, `${g.name} (${g.members})`)));
      groupSelect.disabled = !groups.length;
      update();
    }).catch(() => {});

    const csvInput = h("input", { type: "file", accept: ".csv,text/csv", hidden: true, onchange: async () => {
      const file = csvInput.files[0];
      csvInput.value = "";
      if (!file) return;
      try {
        const parsed = await api("/api/csv/parse", { body: { csv: await file.text() } });
        draft.csv = { name: file.name, ...parsed };
        draft.previewAs = 0;
        update();
        toast(`Loaded ${plural(parsed.rows.length, "recipient")} from ${file.name}` +
          (parsed.skipped.length ? `. Skipped ${parsed.skipped.length} row(s) with a bad email.` : ""));
      } catch (ex) { toast(ex.message, true); }
    } });

    // ----- message -----
    const subCount = h("small", {}, `${draft.subject.length} / 200`);
    const subject = h("input", { class: "input", id: "subject", maxlength: 200, value: draft.subject,
      placeholder: "What is this mail about?",
      oninput: () => { draft.subject = subject.value; subCount.textContent = `${subject.value.length} / 200`; update(); },
      onfocus: () => (lastField = subject) });
    const body = h("textarea", { class: "textarea" + (draft.format === "html" ? " code" : ""), id: "body",
      placeholder: "Write your message. Use {name} or any CSV column to personalise it.",
      oninput: () => { draft.body = body.value; update(); }, onfocus: () => (lastField = body) });
    body.value = draft.body;

    const tokens = h("div", { class: "row", style: "gap:6px;margin-top:8px" });
    function drawTokens() {
      const keys = new Set(["name", "email"]);
      if (draft.csv) draft.csv.columns.filter((c) => c !== draft.csv.email_column).forEach((c) => keys.add(c));
      put(tokens, h("span", { class: "small muted" }, "Insert:"),
        [...keys].map((k) => h("button", { type: "button", class: "token", onclick: () => insertToken(`{${k}}`) }, `{${k}}`)));
    }
    function insertToken(tok) {
      const el = lastField || body;
      const s = el.selectionStart ?? el.value.length, e = el.selectionEnd ?? el.value.length;
      el.value = el.value.slice(0, s) + tok + el.value.slice(e);
      el.focus();
      el.setSelectionRange(s + tok.length, s + tok.length);
      el.dispatchEvent(new Event("input"));
    }

    const templateSelect = h("select", { class: "select", style: "width:auto;padding:5px 8px;font-size:13px", "aria-label": "Start from a template",
      onchange: () => {
        const t = TEMPLATES[templateSelect.value];
        templateSelect.value = "";
        if (!t) return;
        if ((draft.subject || draft.body) && !confirm("Replace the current subject and message with this template?")) return;
        draft.subject = subject.value = t.subject;
        draft.body = body.value = draft.format === "html" ? t.html : t.plain;
        subCount.textContent = `${draft.subject.length} / 200`;
        update();
      } },
      h("option", { value: "" }, "Use a template"),
      Object.keys(TEMPLATES).map((n) => h("option", { value: n }, n)));

    const formatSeg = h("div", { class: "seg", role: "group", "aria-label": "Message format" },
      ["plain", "html"].map((f) => h("button", { type: "button", "aria-pressed": String(draft.format === f), onclick: () => {
        draft.format = f;
        formatSeg.querySelectorAll("button").forEach((b, i) => b.setAttribute("aria-pressed", String(["plain", "html"][i] === f)));
        body.classList.toggle("code", f === "html");
        update();
      } }, f === "plain" ? "Plain text" : "HTML")));

    const replyTo = h("input", { class: "input", type: "email", id: "reply", value: draft.replyTo,
      placeholder: "Optional. Where replies should go", oninput: () => { draft.replyTo = replyTo.value.trim(); update(); } });

    // ----- attachments -----
    const files = h("div", { class: "files" });
    const fileInput = h("input", { type: "file", multiple: true, hidden: true, onchange: () => { upload([...fileInput.files]); fileInput.value = ""; } });
    const drop = h("div", { class: "dropzone", tabindex: "0", role: "button",
      onclick: () => fileInput.click(),
      onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } },
      ondragover: (e) => { e.preventDefault(); drop.classList.add("over"); },
      ondragleave: () => drop.classList.remove("over"),
      ondrop: (e) => { e.preventDefault(); drop.classList.remove("over"); upload([...e.dataTransfer.files]); } },
      "Drop PDFs or other files here, or click to choose");
    function drawFiles() {
      put(files, draft.attachments.map((a, i) => h("div", { class: "file", icon: "file" },
        h("span", { class: "name", title: a.filename }, a.filename),
        h("span", { class: "muted" }, a.uploading ? "Uploading…" : fmtSize(a.size)),
        h("button", { type: "button", class: "btn ghost icon", "aria-label": "Remove " + a.filename, icon: "x",
          disabled: a.uploading, onclick: () => { draft.attachments.splice(i, 1); update(); } }))));
    }
    async function upload(list) {
      const maxMb = session.me.max_attachment_mb;
      for (const file of list) {
        if (file.size > maxMb * 1048576) { toast(`${file.name} is larger than ${maxMb} MB.`, true); continue; }
        const entry = { filename: file.name, size: file.size, uploading: true };
        draft.attachments.push(entry);
        update();
        try {
          const b64 = await new Promise((ok, bad) => {
            const fr = new FileReader();
            fr.onload = () => ok(String(fr.result).split(",")[1] || "");
            fr.onerror = bad;
            fr.readAsDataURL(file);
          });
          const r = await api("/api/attachments", { body: { filename: file.name, content_type: file.type || "application/octet-stream", data_base64: b64 } });
          Object.assign(entry, { id: r.id, filename: r.filename, size: r.size, uploading: false });
        } catch (ex) {
          draft.attachments = draft.attachments.filter((x) => x !== entry);
          toast(`Couldn't attach ${file.name}: ${ex.message}`, true);
        }
        update();
      }
    }

    // ----- delivery -----
    const sendAt = h("input", { class: "input", type: "datetime-local", value: draft.sendAt, "aria-label": "Send date and time",
      oninput: () => { draft.sendAt = sendAt.value; update(); } });
    const repeat = h("select", { class: "select", "aria-label": "Repeat", onchange: () => { draft.repeat = repeat.value; update(); } },
      h("option", { value: "none" }, "Send once"), h("option", { value: "daily" }, "Repeat every day"),
      h("option", { value: "weekly" }, "Repeat every week"));
    repeat.value = draft.repeat;
    const laterFields = h("div", { class: "cols-2", style: "margin-top:10px" }, sendAt, repeat);
    laterFields.hidden = draft.delivery !== "later";
    const choice = (value, title, sub) => h("label", { class: "choice" },
      h("input", { type: "radio", name: "delivery", value, checked: draft.delivery === value,
        onchange: () => { draft.delivery = value; laterFields.hidden = value !== "later"; update(); } }),
      h("span", {}, h("b", {}, title), h("small", {}, sub)));

    // ----- side column: live letter, checklist, send -----
    const letterHead = h("dl", {});
    const letterBody = h("div", {});
    const previewPicker = h("div", { class: "letter-foot" });
    const stamp = h("div", { class: "stamp", "aria-hidden": "true", icon: "envelope" });
    const letter = h("section", { class: "letter", "aria-label": "Live preview" },
      h("div", { class: "stripe", "aria-hidden": "true" }),
      h("div", { class: "letter-head" }, stamp, letterHead),
      letterBody, previewPicker);
    const checklist = h("ul", { class: "checklist" });
    const summary = h("p", { class: "summary", "aria-live": "polite" });
    const sendBtn = h("button", { type: "submit", class: "btn primary lg block" });

    /** Who the preview shows: one sample per source, so you can flip between them. */
    function samples() {
      const out = [];
      if (draft.csv) draft.csv.rows.slice(0, 20).forEach((r) => out.push({ label: `${r.vars.name || r.email} (CSV)`, vars: { email: r.email, ...r.vars } }));
      draft.groups.forEach((g) => out.push({ label: `A member of ${g}`, vars: { email: `member of ${g}`, name: "(their name)" } }));
      draft.to.filter((a) => EMAIL_RE.test(a)).slice(0, 10).forEach((a) => out.push({ label: a, vars: { email: a, name: a.split("@")[0] } }));
      return out.length ? out : [{ label: "Example student", vars: { email: "student@example.com", name: "Student" } }];
    }
    function drawLetter() {
      const list = samples();
      if (draft.previewAs >= list.length) draft.previewAs = 0;
      const s = list[draft.previewAs];
      put(letterHead,
        h("dt", {}, "From"), h("dd", {}, session.me.sender || "Dr. Post"),
        h("dt", {}, "To"), h("dd", {}, s.vars.email),
        h("dt", {}, "Subject"), h("dd", { class: "subj" }, fill(draft.subject, s.vars, false) || "No subject yet"),
        draft.attachments.length ? [h("dt", {}, "Files"), h("dd", {}, draft.attachments.map((a) => a.filename).join(", "))] : null);
      if (draft.format === "html" && draft.body.trim()) {
        // sandbox="" blocks scripts, so previewing pasted HTML is safe
        put(letterBody, h("iframe", { sandbox: "", title: "HTML preview", srcdoc: fill(draft.body, s.vars, true) }));
        letterBody.className = "";
      } else {
        letterBody.className = "letter-body" + (draft.body.trim() ? "" : " empty");
        letterBody.textContent = draft.body.trim() ? fill(draft.body, s.vars, false) : "Your message will appear here as the recipient sees it.";
      }
      if (list.length > 1) {
        const sel = h("select", { "aria-label": "Preview as", onchange: () => { draft.previewAs = Number(sel.value); drawLetter(); } },
          list.map((x, i) => h("option", { value: i }, x.label)));
        sel.value = String(draft.previewAs);
        put(previewPicker, "Preview as ", sel);
      } else {
        put(previewPicker, "Live preview. Placeholders fill in per person.");
      }
    }

    function recipientCount() {
      const groupN = draft.groups.reduce((n, g) => n + ((groupCache.find((x) => x.name === g) || {}).members || 0), 0);
      return draft.to.filter((a) => EMAIL_RE.test(a)).length + (draft.csv ? draft.csv.rows.length : 0) + groupN;
    }
    function unknownPlaceholders() {
      const known = new Set(["name", "email", ...(draft.csv ? draft.csv.columns.map((c) => c.toLowerCase().replace(/[\s_]+/g, "")) : [])]);
      return [...new Set([...(draft.subject + draft.body).matchAll(/\{\s*([A-Za-z0-9_ .-]+?)\s*\}/g)]
        .map((m) => m[1]).filter((k) => !known.has(k.toLowerCase().replace(/[\s_]+/g, ""))))];
    }
    function drawChecklist() {
      const n = recipientCount();
      const bad = draft.to.some((a) => !EMAIL_RE.test(a));
      const unknown = unknownPlaceholders();
      const past = draft.delivery === "later" && draft.sendAt && new Date(draft.sendAt) < new Date();
      const items = [
        [n && !bad ? "ok" : "", bad ? "Fix the addresses in red" : n ? `${plural(n, "recipient")}` : "Add recipients, a group or a CSV"],
        [draft.subject.trim() ? "ok" : "", draft.subject.trim() ? "Subject written" : "Write a subject"],
        [draft.body.trim() ? "ok" : "", draft.body.trim() ? `Message written (${draft.format === "html" ? "HTML" : "plain text"})` : "Write the message"],
        [unknown.length ? "warn" : "ok", unknown.length ? `No data for {${unknown.join("}, {")}}` : "Placeholders all have data"],
        [past ? "warn" : "ok", draft.delivery === "later" ? (past ? "That time has passed" : "Send time set") : "Sends right away"],
      ];
      put(checklist, items.map(([cls, text]) => h("li", { class: cls }, h("span", { class: "tick", icon: cls === "warn" ? "info" : "check" }), h("span", {}, text))));
    }
    function drawSummary() {
      const n = recipientCount();
      const atts = draft.attachments.length;
      let when = "right away";
      if (draft.delivery === "later" && draft.sendAt) {
        when = lowerFirst(fmtWhen(new Date(draft.sendAt).getTime() / 1000));
        if (draft.repeat !== "none") when += draft.repeat === "daily" ? ", then every day" : ", then every week";
      }
      put(summary, n ? ["Goes to about ", h("b", {}, plural(n, "person", "people")), atts ? ` with ${plural(atts, "attachment")}` : "", `, ${when}.`]
        : "Add someone to send to.");
      sendBtn.textContent = draft.delivery === "later" ? "Schedule mail" : "Send now";
    }
    function update() { drawChips(); drawTokens(); drawFiles(); drawLetter(); drawChecklist(); drawSummary(); }

    // ----- submit -----
    async function submit(e) {
      e.preventDefault();
      if (toInput.value.trim()) { addAddresses(toInput.value); toInput.value = ""; }
      const fail = (msg, el) => { toast(msg, true); if (el) el.focus(); };
      if (!draft.to.length && !draft.groups.length && !draft.csv) return fail("Add at least one recipient, group or CSV.", toInput);
      if (draft.to.some((a) => !EMAIL_RE.test(a))) return fail("Fix the addresses marked in red first.", toInput);
      if (!draft.subject.trim()) return fail("Add a subject.", subject);
      if (!draft.body.trim()) return fail("Write a message.", body);
      if (draft.replyTo && !EMAIL_RE.test(draft.replyTo)) return fail("The Reply-To address looks wrong.", replyTo);
      if (draft.attachments.some((a) => a.uploading)) return fail("Wait for the attachments to finish uploading.");
      if (draft.delivery === "later") {
        if (!draft.sendAt) return fail("Pick a date and time.", sendAt);
        if (new Date(draft.sendAt) < new Date()) return fail("That time has already passed. Pick a later time.", sendAt);
      }
      const unknown = unknownPlaceholders();
      if (unknown.length && !confirm(`These placeholders have no data and will be sent as-is: {${unknown.join("}, {")}}.\n\nSend anyway?`)) return;

      const payload = {
        to: draft.to, groups: draft.groups, recipients: draft.csv ? draft.csv.rows : [],
        subject: draft.subject.trim(), body: draft.body, html: draft.format === "html",
        reply_to: draft.replyTo || null, attachment_ids: draft.attachments.map((a) => a.id),
        send_at: draft.delivery === "later" ? new Date(draft.sendAt).toISOString() : null,
        repeat: draft.delivery === "later" ? draft.repeat : "none",
      };
      sendBtn.disabled = true;
      put(sendBtn, h("span", { class: "spinner" }), draft.delivery === "later" ? "Scheduling…" : "Sending…");
      try {
        const r = await api("/api/send", { body: payload });
        toast(r.status === "scheduled" ? `Scheduled for ${lowerFirst(fmtWhen(r.scheduled_at))}` : `Sending to ${plural(r.recipients, "person", "people")}`);
        draft = newDraft();
        location.hash = "#/outbox/" + r.job_id;
      } catch (ex) {
        toast(ex.message, true);
        sendBtn.disabled = false;
        drawSummary();
      }
    }

    const form = h("form", { class: "work", novalidate: true, onsubmit: submit },
      h("div", { class: "sheet" },
        panel("Recipients", h("div", { class: "row", style: "gap:8px" }, groupSelect,
          h("button", { type: "button", class: "btn sm", onclick: () => csvInput.click(),
            title: "CSV with an email column. Other columns become placeholders." }, "Import CSV for mail merge"), csvInput),
          pbody(chips, toHint)),
        panel("Message", templateSelect,
          pbody(h("div", { class: "stack" },
            h("div", {}, h("label", { class: "label", for: "subject" }, "Subject", subCount), subject),
            h("div", {},
              h("div", { class: "row between", style: "margin-bottom:8px" }, h("span", { class: "label", style: "margin:0" }, "Message"), formatSeg),
              body, tokens),
            h("div", {}, h("label", { class: "label", for: "reply" }, "Reply-To"), replyTo)))),
        h("div", { class: "pair" },
          panel("Attachments", h("p", {}, `Up to ${session.me.max_attachment_mb} MB each`),
            pbody(h("div", { class: "stack" }, files, drop), fileInput)),
          panel("Delivery", null,
            pbody(h("div", { class: "delivery" },
              choice("now", "Send now", "Queued and sent within seconds"),
              choice("later", "Schedule", "Pick a time, optionally repeat")),
            laterFields)))),
      h("aside", { class: "side" },
        letter,
        panel("Before you send", null, pbody(checklist)),
        h("section", { class: "panel" }, pbody(h("div", { class: "sendbar" }, summary, sendBtn,
          h("button", { type: "button", class: "btn ghost sm", onclick: () => {
            if (confirm("Clear this draft?")) { draft = newDraft(); navigate(); }
          } }, "Clear draft"),
          h("p", { class: "hint", style: "margin:0;text-align:center" }, "Tip: Ctrl + Enter sends from anywhere on this page.")))),
        upcomingPanel()));

    page.append(
      h("div", { class: "page-head" },
        h("div", {}, h("h1", {}, "New mail"),
          h("p", {}, session.me.sender ? `Sent from ${session.me.sender}` : "Write once, send to one person or a whole class."))),
      form);
    update();
    form.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") form.requestSubmit(); });
  }

  // ======================================================================
  // Outbox (list + docked detail pane)
  // ======================================================================

  let outboxFilter = "all";
  let detailTimer = null;

  function viewOutbox(page) {
    const FILTERS = { all: "All", scheduled: "Scheduled", sending: "Sending", done: "Delivered", problems: "Problems" };
    const filters = h("div", { class: "filters", role: "group", "aria-label": "Filter by status" });
    const listBox = h("div", {});
    const side = h("aside", { class: "side" });
    let jobs = [];
    let selected = Number(location.hash.split("/")[2]) || null;

    const matches = (j, k = outboxFilter) =>
      k === "all" ? true : k === "problems" ? j.status === "failed" || j.status === "partial" : j.status === k;

    function drawList() {
      put(filters, Object.entries(FILTERS).map(([k, label]) =>
        h("button", { class: "filter", "aria-pressed": String(k === outboxFilter), onclick: () => { outboxFilter = k; drawList(); } },
          label, h("span", { class: "n" }, jobs.filter((j) => matches(j, k)).length))));
      const list = jobs.filter((j) => matches(j));
      if (!list.length) {
        put(listBox, h("div", { class: "empty-state" },
          h("h3", {}, jobs.length ? "Nothing here" : "Your outbox is empty"),
          h("p", {}, jobs.length ? "No mail matches this filter." : "Mail you send or schedule shows up here with live progress."),
          jobs.length ? null : h("a", { class: "btn primary", href: "#/compose" }, "Write a mail")));
        return;
      }
      put(listBox, h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", {}, "Mail"), h("th", {}, "Status"), h("th", { class: "hide-sm" }, "Progress"), h("th", {}, "When"))),
        h("tbody", {}, list.map((j) => h("tr", { class: "clickable" + (j.id === selected ? " selected" : ""), tabindex: "0",
          onclick: () => select(j.id), onkeydown: (e) => { if (e.key === "Enter") select(j.id); } },
          h("td", {}, h("div", { class: "cell-main", title: j.subject }, j.subject),
            h("div", { class: "cell-sub" }, `${plural(j.total, "recipient")}${j.attachments ? `, ${plural(j.attachments, "file")}` : ""}${j.created_by ? ` · ${j.created_by}` : ""}`)),
          h("td", {}, badge(shownStatus(j))),
          h("td", { class: "hide-sm" }, h("div", { class: "row", style: "flex-wrap:nowrap" }, progress(j), h("span", { class: "small muted" }, `${j.sent}/${j.total}`))),
          h("td", { class: "small" }, fmtWhen(j.status === "scheduled" ? j.scheduled_at : (j.finished_at || j.scheduled_at)),
            j.repeat !== "none" ? h("div", { class: "cell-sub" }, j.repeat === "daily" ? "Repeats daily" : "Repeats weekly") : null)))))));
    }

    function select(id) {
      selected = id;
      history.replaceState(null, "", id ? "#/outbox/" + id : "#/outbox");
      drawList();
      drawSide();
    }

    /** Side column: the selected mail's details, or a summary of the queue. */
    async function drawSide() {
      clearInterval(detailTimer);
      side.classList.toggle("has-detail", !!selected);
      if (!selected) {
        const waiting = jobs.reduce((n, j) => n + j.pending, 0);
        const sending = jobs.filter((j) => j.status === "sending").length;
        const sentToday = jobs.filter((j) => (j.finished_at || 0) > Date.now() / 1000 - 86400).reduce((n, j) => n + j.sent, 0);
        const problems = jobs.filter((j) => matches(j, "problems")).length;
        put(side,
          panel("Queue right now", null, pbody(h("dl", { class: "kv" },
            h("dt", {}, "Mails being sent"), h("dd", {}, sending),
            h("dt", {}, "Copies waiting"), h("dd", {}, waiting),
            h("dt", {}, "Delivered in 24 h"), h("dd", {}, sentToday),
            h("dt", {}, "Mails with problems"), h("dd", { style: problems ? "color:var(--fail)" : "" }, problems)),
          h("p", { class: "hint", style: "margin-top:12px" }, "Select a mail on the left to see who got it, retry failures or cancel it."))),
          upcomingPanel());
        return;
      }
      const id = selected;
      async function load() {
        let j;
        try { j = await api("/api/jobs/" + id); } catch (ex) { toast(ex.message, true); select(null); return; }
        if (selected !== id) return;
        const facts = [
          ["Recipients", `${j.total} (${j.sent} sent, ${j.failed} failed${j.pending ? `, ${j.pending} waiting` : ""})`],
          [j.status === "scheduled" ? "Sends" : "Sent", fmtWhen(j.status === "scheduled" ? j.scheduled_at : (j.finished_at || j.scheduled_at))],
          ["Repeats", j.repeat === "none" ? "No" : j.repeat === "daily" ? "Every day" : "Every week"],
          ["Created by", j.created_by || "Unknown"],
          ["Format", j.html ? "HTML" : "Plain text"],
          ["Attachments", j.attachments || "None"],
          j.reply_to ? ["Reply-To", j.reply_to] : null,
        ].filter(Boolean);
        put(side, h("section", { class: "panel detail", role: "region", "aria-label": "Mail details" },
          h("div", { class: "detail-head" },
            h("div", { class: "grow" }, h("h2", {}, j.subject), h("div", { style: "margin-top:6px" }, badge(shownStatus(j)))),
            h("button", { class: "btn ghost icon", "aria-label": "Close details", icon: "x", onclick: () => select(null) })),
          h("div", { class: "detail-body" },
            j.total ? h("div", { style: "margin-bottom:14px" }, progress(j)) : null,
            h("dl", { class: "facts" }, facts.map(([k, v]) => [h("dt", {}, k), h("dd", {}, String(v))])),
            h("h3", { style: "margin-bottom:8px" }, "Message"),
            h("div", { class: "body-preview" }, j.body),
            h("h3", { style: "margin:18px 0 4px" }, "Recipients"),
            h("ul", { class: "msg-list" }, j.messages.map((m) => h("li", {},
              h("div", { class: "grow" }, m.email,
                m.last_error ? h("div", { class: "err" }, m.last_error) : null,
                m.status === "pending" && m.attempts ? h("div", { class: "cell-sub" }, `Retry ${m.attempts + 1} ${lowerFirst(fmtWhen(m.next_attempt_at))}`) : null),
              badge(m.status === "scheduled" ? shownStatus(j) : m.status))))),
          h("div", { class: "detail-foot" },
            j.failed ? h("button", { class: "btn", onclick: async () => {
              try { const r = await api(`/api/jobs/${id}/retry`, { method: "POST" }); toast(`Retrying ${plural(r.retrying, "address", "addresses")}`); refresh(); }
              catch (ex) { toast(ex.message, true); }
            } }, "Retry failed") : null,
            ["scheduled", "sending"].includes(j.status) ? h("button", { class: "btn danger", onclick: async () => {
              if (!confirm(j.repeat !== "none" ? "Cancel this mail? Future repeats are cancelled too." : "Cancel this mail? Unsent copies won't go out.")) return;
              try { await api(`/api/jobs/${id}/cancel`, { method: "POST" }); toast("Mail cancelled"); refresh(); }
              catch (ex) { toast(ex.message, true); }
            } }, j.status === "scheduled" ? "Cancel mail" : "Stop sending") : null,
            h("button", { class: "btn detail-close", onclick: () => select(null) }, "Close"))));
        if (!["scheduled", "sending"].includes(j.status)) clearInterval(detailTimer);
      }
      detailTimer = setInterval(load, 2500);
      await load();
    }

    async function refresh() {
      try {
        jobs = await api("/api/jobs?limit=100");
        drawList();
        if (!selected) drawSide();
      } catch (ex) { put(listBox, h("div", { class: "empty-state" }, ex.message)); }
    }

    page.append(
      h("div", { class: "page-head" },
        h("div", {}, h("h1", {}, "Outbox"), h("p", {}, "Everything sent, sending and scheduled.")),
        h("a", { class: "btn primary", href: "#/compose" }, "New mail")),
      h("div", { class: "work" },
        panel(filters, null, h("div", { class: "panel-body tight" }, listBox)),
        side));
    refresh().then(() => { if (selected) drawSide(); });
    poll(refresh, 3000);
    const onKey = (e) => { if (e.key === "Escape" && selected) select(null); };
    document.addEventListener("keydown", onKey);
    page.cleanup = () => document.removeEventListener("keydown", onKey);
  }

  // ======================================================================
  // Contacts (table + groups column)
  // ======================================================================

  let contactGroup = "";
  function viewContacts(page) {
    const search = h("input", { class: "input", type: "search", placeholder: "Search by name or email", "aria-label": "Search contacts",
      style: "max-width:260px;padding:6px 10px", oninput: () => { clearTimeout(search.t); search.t = setTimeout(load, 200); } });
    const listBox = h("div", {});
    const groupsBox = h("ul", { class: "mini" });
    const titleEl = h("h2", {}, "Everyone");

    async function load() {
      try {
        const [groups, contacts] = await Promise.all([api("/api/groups"),
          api(`/api/contacts?q=${encodeURIComponent(search.value.trim())}&group=${encodeURIComponent(contactGroup)}`)]);
        groupCache = groups;
        if (contactGroup && !groups.some((g) => g.name === contactGroup)) contactGroup = "";
        titleEl.textContent = contactGroup ? `Group ${contactGroup}` : "Everyone";
        const total = groups.length ? null : contacts.length;
        put(groupsBox,
          h("li", { class: "link" + (contactGroup ? "" : " on"), style: contactGroup ? "" : "background:var(--blue-soft)", onclick: () => { contactGroup = ""; load(); } },
            h("div", { class: "grow" }, h("div", { class: "t" }, "Everyone")), total !== null ? h("span", { class: "small muted" }, total) : null),
          groups.map((g) => h("li", { class: "link", style: contactGroup === g.name ? "background:var(--blue-soft)" : "",
            onclick: () => { contactGroup = g.name; load(); } },
            h("div", { class: "grow" }, h("div", { class: "t" }, g.name), h("div", { class: "s" }, plural(g.members, "person", "people"))),
            h("button", { class: "btn sm", type: "button", title: `Write a mail to ${g.name}`, onclick: (e) => {
              e.stopPropagation(); presetGroup = g.name; location.hash = "#/compose";
            } }, "Write"))),
          groups.length ? null : h("li", { class: "mini-empty" }, "No groups yet. Add a group name when importing or editing contacts."));

        if (!contacts.length) {
          put(listBox, h("div", { class: "empty-state" },
            h("h3", {}, search.value || contactGroup ? "No matches" : "No contacts yet"),
            h("p", {}, search.value || contactGroup ? "Try another search or group." :
              "Import a class list from CSV, or add people one by one."),
            search.value || contactGroup ? null : h("button", { class: "btn primary", onclick: importDialog }, "Import CSV")));
          return;
        }
        put(listBox, h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, h("th", {}, "Name"), h("th", {}, "Email"), h("th", { class: "hide-sm" }, "Groups"), h("th", { class: "num" }, ""))),
          h("tbody", {}, contacts.map((c) => h("tr", {},
            h("td", {}, h("div", { class: "cell-main" }, c.name || "No name"),
              Object.keys(c.extra).length ? h("div", { class: "cell-sub" }, Object.entries(c.extra).slice(0, 3).map(([k, v]) => `${k}: ${v}`).join(", ")) : null),
            h("td", { class: "small", style: "overflow-wrap:anywhere" }, c.email),
            h("td", { class: "hide-sm" }, h("div", { class: "row", style: "gap:4px" }, c.groups.map((g) => h("span", { class: "chip group plain" }, g)))),
            h("td", { class: "num", style: "white-space:nowrap" },
              h("button", { class: "btn ghost sm", onclick: () => contactDialog(c) }, "Edit"),
              h("button", { class: "btn ghost sm danger", onclick: async () => {
                if (!confirm(`Delete ${c.name || c.email} from contacts?`)) return;
                try { await api("/api/contacts/" + c.id, { method: "DELETE" }); toast("Contact deleted"); load(); }
                catch (ex) { toast(ex.message, true); }
              } }, "Delete"))))))));
      } catch (ex) { put(listBox, h("div", { class: "empty-state" }, ex.message)); }
    }

    function contactDialog(c) {
      const name = h("input", { class: "input", id: "cn", value: c ? c.name : "" });
      const email = h("input", { class: "input", id: "ce", type: "email", value: c ? c.email : "" });
      const groups = h("input", { class: "input", id: "cg", value: c ? c.groups.join(", ") : contactGroup, placeholder: "e.g. CSE-A, Final year" });
      modal(c ? "Edit contact" : "Add contact", [
        h("div", {}, h("label", { class: "label", for: "cn" }, "Name"), name),
        h("div", {}, h("label", { class: "label", for: "ce" }, "Email"), email),
        h("div", {}, h("label", { class: "label", for: "cg" }, "Groups", h("small", {}, "comma separated")), groups),
      ], c ? "Save contact" : "Add contact", async () => {
        const body = { name: name.value.trim(), email: email.value.trim(), extra: c ? c.extra : {},
          groups: groups.value.split(",").map((s) => s.trim()).filter(Boolean) };
        await api(c ? "/api/contacts/" + c.id : "/api/contacts", { method: c ? "PUT" : "POST", body });
        toast(c ? "Contact saved" : "Contact added");
        load();
      });
      name.focus();
    }

    function importDialog() {
      const file = h("input", { class: "input", id: "if", type: "file", accept: ".csv,text/csv" });
      const group = h("input", { class: "input", id: "ig", value: contactGroup, placeholder: "e.g. CSE-A" });
      modal("Import contacts from CSV", [
        h("p", { class: "small muted" }, "The file needs an email column. A name column fills {name}; other columns (roll, marks…) are saved for mail merge."),
        h("div", {}, h("label", { class: "label", for: "if" }, "CSV file"), file),
        h("div", {}, h("label", { class: "label", for: "ig" }, "Add everyone to group", h("small", {}, "optional")), group),
      ], "Import contacts", async () => {
        if (!file.files[0]) throw new Error("Choose a CSV file first.");
        const r = await api("/api/contacts/import", { body: { csv: await file.files[0].text(), group: group.value.trim() || null } });
        toast(`Added ${r.added}, updated ${r.updated}` + (r.skipped.length ? `, skipped ${r.skipped.length} bad row(s)` : ""));
        if (group.value.trim()) contactGroup = group.value.trim();
        load();
      });
    }

    page.append(
      h("div", { class: "page-head" },
        h("div", {}, h("h1", {}, "Contacts"), h("p", {}, "People and groups you mail often.")),
        h("div", { class: "row" },
          h("button", { class: "btn", onclick: importDialog }, "Import CSV"),
          h("button", { class: "btn primary", onclick: () => contactDialog(null) }, "Add contact"))),
      h("div", { class: "work" },
        panel(titleEl, search, h("div", { class: "panel-body tight" }, listBox)),
        h("aside", { class: "side" },
          panel("Groups", null, h("div", { class: "panel-body tight" }, groupsBox)),
          panel("CSV format", null, pbody(
            h("pre", { class: "code" }, "name,email,roll\nAsha Rao,asha@example.com,21\nRavi K,ravi@example.com,22"),
            h("p", { class: "hint" }, "Extra columns like roll or marks become placeholders, e.g. {roll}. Importing the same email again updates that contact."))))));
    load();
  }

  /** Small reusable dialog. onOk may throw to show an error and keep the dialog open. */
  function modal(title, fields, okLabel, onOk) {
    const err = h("div", { class: "alert", hidden: true, role: "alert" });
    const ok = h("button", { class: "btn primary", type: "submit" }, okLabel);
    const dlg = h("dialog", { class: "modal" },
      h("form", { method: "dialog", onsubmit: async (e) => {
        e.preventDefault();
        if (!okLabel) { shut(); return; }
        ok.disabled = true; err.hidden = true;
        try { await onOk(); shut(); }
        catch (ex) { err.textContent = ex.message; err.hidden = false; }
        finally { ok.disabled = false; }
      } },
        h("div", { class: "modal-title" }, h("h2", {}, title)),
        h("div", { class: "modal-body stack" }, err, fields),
        h("div", { class: "modal-foot" },
          h("button", { class: "btn", type: "button", onclick: () => shut() }, okLabel ? "Cancel" : "Done"),
          okLabel ? ok : null)));
    function shut() { if (dlg.open) dlg.close(); dlg.remove(); }
    dlg.addEventListener("close", shut); // Escape key
    document.body.append(dlg);
    dlg.showModal();
    return dlg;
  }

  // ======================================================================
  // Dashboard
  // ======================================================================

  let dashDays = 14;
  const SERIES = [{ key: "sent", label: "Sent", color: "#2f55d4" }, { key: "failed", label: "Failed", color: "#d4434c" }];

  function viewDashboard(page) {
    const stats = h("div", { class: "panel stats" });
    const chartBox = h("div", { class: "chart" });
    const tableBox = h("div", { hidden: true });
    const quotaBody = pbody();
    const problemsList = h("ul", { class: "mini" });
    const rangeSeg = h("div", { class: "seg", role: "group", "aria-label": "Time range" },
      [7, 14, 30].map((d) => h("button", { type: "button", "aria-pressed": String(d === dashDays),
        onclick: () => { dashDays = d; rangeSeg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.textContent === d + " days"))); load(); } },
        d + " days")));
    const tableBtn = h("button", { class: "btn sm", icon: "table", onclick: () => {
      tableBox.hidden = !tableBox.hidden;
      chartBox.hidden = !tableBox.hidden;
      tableBtn.lastChild.textContent = tableBox.hidden ? "Table" : "Chart";
    } }, h("span", {}, "Table"));

    async function load() {
      let s, jobs;
      try {
        [s, jobs] = await Promise.all([api(`/api/stats?days=${dashDays}&tz_offset_minutes=${-new Date().getTimezoneOffset()}`), api("/api/jobs?limit=100")]);
      } catch (ex) { put(stats, h("div", { class: "empty-state" }, ex.message)); return; }
      const stat = (v, k, cls) => h("div", { class: "stat " + (cls || "") }, h("div", { class: "v" }, v.toLocaleString()), h("div", { class: "k" }, k));
      put(stats,
        stat(s.total_sent, "mails delivered"),
        stat(s.total_failed, "mails failed", s.total_failed ? "bad" : ""),
        stat(s.pending + s.scheduled_jobs, "waiting or scheduled"),
        stat(s.contacts, "contacts saved"));
      drawChart(s.days);
      drawTable(s.days);

      const u = s.usage;
      const frac = Math.min(1, u.sent_24h / Math.max(1, u.daily_limit));
      const ring = h("div", { class: "big-stamp" });
      ring.innerHTML = postmark(u, false);
      ring.append(h("div", {}, h("div", { style: "font:750 22px/1.1 var(--display)" }, `${u.sent_24h} of ${u.daily_limit}`),
        h("div", { class: "small muted" }, "sent in the last 24 hours")));
      put(quotaBody, ring,
        h("div", { class: "meter" + (frac > 0.85 ? " high" : ""), style: "margin-top:14px", role: "meter", "aria-valuemin": 0,
          "aria-valuemax": u.daily_limit, "aria-valuenow": u.sent_24h, "aria-label": "Daily limit used" }, h("i", { style: `width:${frac * 100}%` })),
        h("dl", { class: "kv", style: "margin-top:14px" },
          h("dt", {}, "Per minute"), h("dd", {}, `${u.sent_last_minute} / ${u.per_minute_limit}`),
          h("dt", {}, "Copies waiting"), h("dd", {}, u.pending)),
        h("p", { class: "hint" }, frac >= 1
          ? "Limit reached. Waiting mail goes out automatically as the 24-hour window frees up."
          : "Gmail blocks accounts that send too much. AutoMail pauses before the limit and resumes on its own."));

      const problems = jobs.filter((j) => j.status === "failed" || j.status === "partial").slice(0, 5);
      put(problemsList, problems.length ? problems.map((j) => h("li", { class: "link", onclick: () => (location.hash = "#/outbox/" + j.id) },
        h("div", { class: "grow" }, h("div", { class: "t" }, j.subject), h("div", { class: "s" }, `${j.failed} of ${j.total} failed · ${fmtWhen(j.finished_at || j.scheduled_at)}`)),
        badge(j.status)))
        : h("li", { class: "mini-empty" }, "No failed mail. Everything that was sent arrived."));
    }

    function drawChart(days) {
      lastDays = days;
      // drawn at the box's real width, so wide screens get a wider chart, not a taller one
      const W = Math.max(420, Math.round(chartBox.clientWidth || 760)), H = 280, padL = 34, padB = 26, padT = 12;
      const max = Math.max(4, ...days.map((d) => d.sent + d.failed));
      const step = niceStep(max), top = Math.ceil(max / step) * step;
      const y = (v) => padT + (H - padT - padB) * (1 - v / top);
      const slot = (W - padL) / days.length;
      const bw = Math.max(4, Math.min(30, slot * 0.6));
      const NS = "http://www.w3.org/2000/svg";
      const svg = document.createElementNS(NS, "svg");
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
      svg.setAttribute("role", "img");
      svg.setAttribute("aria-label", `Mails sent and failed per day, last ${days.length} days`);
      const el = (tag, attrs, text) => {
        const n = document.createElementNS(NS, tag);
        for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
        if (text !== undefined) n.textContent = text;
        svg.append(n);
        return n;
      };
      for (let v = 0; v <= top; v += step) {
        el("line", { class: "grid", x1: padL, x2: W, y1: y(v), y2: y(v) });
        el("text", { class: "axis-label", x: padL - 8, y: y(v) + 4, "text-anchor": "end" }, v);
      }
      const labelEvery = Math.ceil(days.length / 8);
      const tip = h("div", { class: "tooltip", hidden: true });
      days.forEach((d, i) => {
        const cx = padL + slot * i + slot / 2;
        let base = y(0);
        const parts = SERIES.map((s) => ({ ...s, v: d[s.key] })).filter((p) => p.v > 0);
        parts.forEach((p, pi) => {
          const segTop = base - (y(0) - y(p.v));
          const hgt = base - segTop - (pi > 0 ? 2 : 0); // 2px gap between stacked segments
          el("path", { d: barPath(cx - bw / 2, segTop, bw, Math.max(1, hgt), pi === parts.length - 1 ? 3 : 0), fill: p.color });
          base = segTop;
        });
        if (i % labelEvery === 0 || i === days.length - 1) {
          el("text", { class: "axis-label", x: cx, y: H - 6, "text-anchor": "middle" },
            new Date(d.date + "T00:00:00").toLocaleDateString([], { day: "numeric", month: "short" }));
        }
        const hit = el("rect", { class: "hit", x: cx - slot / 2, y: padT, width: slot, height: H - padT - padB, rx: 3 });
        hit.addEventListener("mouseenter", () => {
          hit.classList.add("on");
          put(tip, h("b", {}, new Date(d.date + "T00:00:00").toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" })),
            SERIES.map((s) => h("div", {}, h("i", { style: `background:${s.color}` }), `${s.label}: ${d[s.key]}`)));
          tip.hidden = false;
          const box = chartBox.getBoundingClientRect(), r = hit.getBoundingClientRect();
          tip.style.left = Math.min(Math.max(r.left - box.left + r.width / 2, 60), box.width - 60) + "px";
          tip.style.top = (y(d.sent + d.failed) / H) * box.height - 6 + "px";
        });
        hit.addEventListener("mouseleave", () => { hit.classList.remove("on"); tip.hidden = true; });
      });
      put(chartBox, svg, tip);
    }
    function barPath(x, yTop, w, hgt, r) {
      r = Math.min(r, w / 2, hgt);
      return `M${x},${yTop + hgt}V${yTop + r}Q${x},${yTop} ${x + r},${yTop}H${x + w - r}Q${x + w},${yTop} ${x + w},${yTop + r}V${yTop + hgt}Z`;
    }
    function niceStep(max) {
      const raw = max / 4, pow = 10 ** Math.floor(Math.log10(raw)), n = raw / pow;
      return Math.max(1, (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * pow);
    }
    function drawTable(days) {
      put(tableBox, h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", {}, "Day"), h("th", { class: "num" }, "Sent"), h("th", { class: "num" }, "Failed"))),
        h("tbody", {}, [...days].reverse().map((d) => h("tr", {},
          h("td", {}, new Date(d.date + "T00:00:00").toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" })),
          h("td", { class: "num" }, d.sent), h("td", { class: "num" }, d.failed)))))));
    }

    page.append(
      h("div", { class: "page-head" },
        h("div", {}, h("h1", {}, "Dashboard"), h("p", {}, "How much mail went out, and how much bounced."))),
      h("div", { class: "work" },
        h("div", { class: "sheet" },
          stats,
          panel(h("div", { class: "row", style: "gap:16px" }, h("h2", {}, "Sent and failed per day"),
            h("div", { class: "legend" }, SERIES.map((s) => h("span", {}, h("i", { style: `background:${s.color}` }), s.label)))),
            h("div", { class: "row" }, rangeSeg, tableBtn),
            pbody(chartBox, tableBox))),
        h("aside", { class: "side" },
          panel("Daily sending limit", null, quotaBody),
          panel("Needs attention", null, h("div", { class: "panel-body tight" }, problemsList)),
          upcomingPanel())));
    load();
    poll(load, 10000);
    let lastDays = null, resizeT;
    const onResize = () => { clearTimeout(resizeT); resizeT = setTimeout(() => { if (lastDays && !chartBox.hidden) drawChart(lastDays); }, 150); };
    window.addEventListener("resize", onResize);
    page.cleanup = () => window.removeEventListener("resize", onResize);
  }

  // ======================================================================
  // Settings
  // ======================================================================

  function viewSettings(page) {
    const isAdmin = session.me.role === "admin";
    page.append(h("div", { class: "page-head" },
      h("div", {}, h("h1", {}, "Settings"), h("p", {}, isAdmin ? "Team accounts, connected apps and your password." : "Your account."))));

    const pw = h("input", { class: "input", type: "password", id: "npw", autocomplete: "new-password", minlength: 8 });
    const passwordPanel = panel("Your password", h("p", {}, "At least 8 characters"),
      pbody(h("form", { class: "stack", onsubmit: async (e) => {
        e.preventDefault();
        try { await api("/api/me/password", { body: { password: pw.value } }); pw.value = ""; toast("Password changed"); }
        catch (ex) { toast(ex.message, true); }
      } }, h("div", {}, h("label", { class: "label", for: "npw" }, "New password"), pw),
        h("button", { class: "btn", type: "submit" }, "Change password"))));
    const accountPanel = panel("Signed in as", null, pbody(h("dl", { class: "kv" },
      h("dt", {}, "Username"), h("dd", {}, session.me.username),
      session.me.email ? h("dt", {}, "Email") : null, session.me.email ? h("dd", {}, session.me.email) : null,
      h("dt", {}, "Role"), h("dd", {}, isAdmin ? "Admin" : "Sender"),
      h("dt", {}, "Sending from"), h("dd", {}, session.me.sender || "Not set"),
      h("dt", {}, "Mode"), h("dd", {}, session.me.dry_run ? "Practice (dry run)" : "Live"))));

    if (!isAdmin) {
      page.append(h("div", { class: "work" }, h("div", { class: "sheet" }, passwordPanel), h("aside", { class: "side" }, accountPanel)));
      return;
    }

    const users = h("div", {});
    async function loadUsers() {
      const list = await api("/api/users");
      put(users, h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", {}, "Username"), h("th", {}, "Role"), h("th", { class: "num" }, ""))),
        h("tbody", {}, list.map((u) => h("tr", {},
          h("td", {}, h("span", { class: "cell-main" }, u.username), u.id === session.me.id ? h("span", { class: "muted small" }, " (you)") : null),
          h("td", { class: "small" }, u.role === "admin" ? "Admin: everything" : "Sender: compose, contacts, own outbox"),
          h("td", { class: "num", style: "white-space:nowrap" },
            h("button", { class: "btn ghost sm", onclick: () => {
              const p = h("input", { class: "input", type: "password", id: "rp", minlength: 8 });
              modal(`New password for ${u.username}`, [h("div", {}, h("label", { class: "label", for: "rp" }, "Password"), p)],
                "Set password", async () => { await api(`/api/users/${u.id}/password`, { body: { password: p.value } }); toast("Password set"); });
              p.focus();
            } }, "Reset password"),
            u.id === session.me.id ? null : h("button", { class: "btn ghost sm danger", onclick: async () => {
              if (!confirm(`Delete the account ${u.username}? Their sent mail stays in the outbox.`)) return;
              try { await api("/api/users/" + u.id, { method: "DELETE" }); toast("Account deleted"); loadUsers(); }
              catch (ex) { toast(ex.message, true); }
            } }, "Delete"))))))));
    }
    const addAccount = h("button", { class: "btn sm", onclick: () => {
      const u = h("input", { class: "input", id: "nu", autocomplete: "off" });
      const p = h("input", { class: "input", id: "np", type: "password", autocomplete: "new-password" });
      const r = h("select", { class: "select", id: "nr" }, h("option", { value: "sender" }, "Sender"), h("option", { value: "admin" }, "Admin"));
      modal("Add an account", [
        h("div", {}, h("label", { class: "label", for: "nu" }, "Username"), u),
        h("div", {}, h("label", { class: "label", for: "np" }, "Password", h("small", {}, "at least 8 characters")), p),
        h("div", {}, h("label", { class: "label", for: "nr" }, "Role"), r,
          h("p", { class: "hint" }, "Senders write mail, manage contacts and see their own outbox. Admins also manage accounts and app keys.")),
      ], "Add account", async () => {
        await api("/api/users", { body: { username: u.value.trim(), password: p.value, role: r.value } });
        toast("Account added"); loadUsers();
      });
      u.focus();
    } }, "Add account");

    const keys = h("div", {});
    async function loadKeys() {
      const list = await api("/api/keys");
      put(keys, list.length ? h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", {}, "App"), h("th", {}, "Key starts with"), h("th", {}, "Last used"), h("th", { class: "num" }, ""))),
        h("tbody", {}, list.map((k) => h("tr", {},
          h("td", { class: "cell-main" }, k.name),
          h("td", { class: "small", style: "font-family:var(--mono)" }, k.prefix + "…"),
          h("td", { class: "small" }, k.last_used_at ? fmtWhen(k.last_used_at) : "Never"),
          h("td", { class: "num" }, h("button", { class: "btn ghost sm danger", onclick: async () => {
            if (!confirm(`Revoke the key for ${k.name}? That app will stop being able to send mail.`)) return;
            try { await api("/api/keys/" + k.id, { method: "DELETE" }); toast("Key revoked"); loadKeys(); }
            catch (ex) { toast(ex.message, true); }
          } }, "Revoke")))))))
        : h("div", { class: "empty-state" }, "No apps connected yet."));
    }
    const connect = h("button", { class: "btn sm", onclick: () => {
      const n = h("input", { class: "input", id: "kn", placeholder: "e.g. Agile tracker" });
      modal("Connect an app", [h("div", {}, h("label", { class: "label", for: "kn" }, "App name"), n)], "Create key", async () => {
        const k = await api("/api/keys", { body: { name: n.value.trim() } });
        loadKeys();
        setTimeout(() => modal("Copy this key now", [
          h("p", { class: "small muted" }, "It won't be shown again. Store it in the other app's settings."),
          h("div", { class: "secret" }, k.key),
          h("button", { class: "btn sm", type: "button", onclick: () => navigator.clipboard.writeText(k.key).then(() => toast("Key copied"), () => toast("Copy it by hand", true)) }, "Copy key"),
        ], null), 0);
      });
      n.focus();
    } }, "Connect an app");

    const example = `curl -X POST ${location.origin}/api/send \\
  -H "X-API-Key: am_your_key" \\
  -H "Content-Type: application/json" \\
  -d '{"to": "team@example.com",
       "subject": "Sprint 4 is done",
       "body": "All stories are closed."}'`;

    page.append(h("div", { class: "work" },
      h("div", { class: "sheet" },
        panel("Team accounts", addAccount, h("div", { class: "panel-body tight" }, users)),
        panel(h("div", {}, h("h2", {}, "Connected apps"), h("p", {}, "Programs that send notifications through AutoMail with a key")),
          connect, h("div", { class: "panel-body tight" }, keys))),
      h("aside", { class: "side" },
        accountPanel,
        passwordPanel,
        panel("How another app sends mail", null, pbody(h("pre", { class: "code" }, example),
          h("p", { class: "hint" }, "Add \"send_at\" to schedule it, or \"groups\": [\"CSE-A\"] to mail a group. Full reference: ",
            h("a", { href: "/docs", target: "_blank", rel: "noopener" }, "API docs"), "."))))));
    loadUsers().catch((ex) => put(users, h("p", { class: "hint err", style: "padding:16px" }, ex.message)));
    loadKeys().catch((ex) => put(keys, h("p", { class: "hint err", style: "padding:16px" }, ex.message)));
  }

  // ======================================================================
  // Boot
  // ======================================================================

  async function boot() {
    // Links from emails: #/verify/<token> and #/reset/<token>. The token is removed
    // from the address bar straight away so it doesn't linger in history or screenshots.
    const link = /^#\/(verify|reset)\/([\w-]+)$/.exec(location.hash);
    if (link) {
      history.replaceState(null, "", location.pathname + location.search);
      return renderLogin(link[1], { token: link[2] });
    }
    if (!session.token) return renderLogin();
    try { session.me = await api("/api/me"); } catch { return renderLogin(); }
    renderShell();
    navigate();
  }

  window.addEventListener("hashchange", () => {
    if (/^#\/(verify|reset)\//.test(location.hash)) boot();
    else if (session.me) navigate();
  });
  setInterval(() => { if (session.me && !document.hidden) refreshHealth(); }, 15000);
  boot();
})();
