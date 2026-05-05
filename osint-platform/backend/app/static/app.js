/* OSINT Platform — frontend controller (v1.1, with SSE + structured Findings) */
(() => {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const state = {
    kind: "name",
    currentRecord: null,
    findings: new Map(),     // key -> finding
    network: null,
    sse: null,
    filters: { type: "", conf: 50, verified: false, showSignals: true },
  };

  const placeholders = {
    name: "e.g. Jane Doe",
    email: "e.g. jane.doe@example.com",
    phone: "e.g. +14155551212",
    username: "e.g. janedoe",
  };

  // --- Tabs ---
  $$(".kind-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".kind-tab").forEach((b) => b.classList.remove("tab-active"));
      btn.classList.add("tab-active");
      state.kind = btn.dataset.kind;
      $("#query-input").placeholder = placeholders[state.kind];
      $("#query-input").focus();
    });
  });

  // --- Filters ---
  $("#filter-type").addEventListener("change", (e) => { state.filters.type = e.target.value; renderFindings(); });
  $("#filter-conf").addEventListener("change", (e) => { state.filters.conf = parseInt(e.target.value, 10); renderFindings(); });
  $("#filter-verified").addEventListener("change", (e) => { state.filters.verified = e.target.checked; renderFindings(); });
  $("#show-signals").addEventListener("change", (e) => { state.filters.showSignals = e.target.checked; renderFindings(); });

  // --- Status pill ---
  function setStatus(text, color) {
    $("#status-text").textContent = text;
    const pill = $("#status-pill .w-2");
    if (pill) pill.className = `w-2 h-2 rounded-full ${color || "bg-ok"} animate-pulse`;
  }

  // --- Scan log ---
  function logLine(level, msg) {
    const log = $("#scan-log");
    log.classList.remove("hidden");
    const div = document.createElement("div");
    div.className = "log-line";
    div.innerHTML = `<span class="lvl">[${level}]</span>${escapeHTML(msg)}`;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }
  function clearLog() { $("#scan-log").innerHTML = ""; $("#scan-log").classList.add("hidden"); }

  // --- Form submit ---
  $("#search-form").addEventListener("submit", (e) => e.preventDefault());
  $("#run-btn").addEventListener("click", runSearch);
  $("#query-input").addEventListener("keydown", (e) => { if (e.key === "Enter") runSearch(); });

  function resetSearch() {
    state.findings.clear();
    state.currentRecord = null;
    $("#dashboard").classList.add("hidden");
    // Reset the local DB pill so it never carries the "idle" state across
    // a fresh search — the moment a search starts it should read
    // "querying…" until the first ES result arrives.
    const pill = $("#es-status-pill");
    if (pill) {
      pill.textContent = "querying…";
      pill.className = "text-xs font-mono px-2 py-0.5 rounded-full border border-accent/40 text-accent animate-pulse";
    }
    const meta = $("#es-meta");
    if (meta) meta.textContent = "";
    const body = $("#es-results");
    if (body) body.innerHTML = '<div class="text-slate-500 text-sm font-mono">querying tc_index…</div>';
  }

  async function runSearch() {
    const value = $("#query-input").value.trim();
    if (!value) { $("#query-input").focus(); return; }
    const dorksOnly = $("#dorks-only").checked;
    const live = $("#live-stream").checked && !dorksOnly;
    const shortCircuit = $("#short-circuit") && $("#short-circuit").checked;

    resetSearch();
    setRunning(true);
    clearLog();
    logLine("init", `kind=${state.kind} value="${value}"`);
    setStatus("scanning", "bg-accent");

    try {
      if (dorksOnly) {
        const r = await fetch("/api/dorks", {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ kind: state.kind, value }),
        });
        if (!r.ok) throw new Error(await r.text());
        const j = await r.json();
        const synth = synthFromDorks(state.kind, value, j);
        state.currentRecord = synth;
        renderDashboard(synth);
      } else if (live) {
        await runStream(state.kind, value, shortCircuit);
      } else {
        const url = "/api/search" + (shortCircuit ? "?short_circuit_on_db_hit=true" : "");
        const r = await fetch(url, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ kind: state.kind, value }),
        });
        if (!r.ok) throw new Error(await r.text());
        const payload = await r.json();
        state.currentRecord = payload;
        ingestFindings(payload.findings || []);
        renderDashboard(payload);
      }
      setStatus("complete", "bg-ok");
      refreshHistory();
    } catch (err) {
      console.error(err);
      logLine("error", err.message || String(err));
      setStatus("error", "bg-danger");
    } finally {
      setRunning(false);
    }
  }

  function runStream(kind, value, shortCircuit) {
    return new Promise((resolve, reject) => {
      if (state.sse) { try { state.sse.close(); } catch {} }
      $("#dashboard").classList.remove("hidden"); // show shell so streaming items have a home
      let url = `/api/search/stream?kind=${encodeURIComponent(kind)}&value=${encodeURIComponent(value)}`;
      if (shortCircuit) url += "&short_circuit_on_db_hit=true";
      const sse = new EventSource(url);
      state.sse = sse;
      sse.addEventListener("stage", (e) => {
        const d = JSON.parse(e.data);
        logLine(d.stage, d.detail);
        // Update the local DB pill the instant the engine reports the
        // ES query result — the user should never see "idle" stick once
        // the search actually started.
        if (d.stage === "elasticsearch") {
          const pill = $("#es-status-pill");
          const body = $("#es-results");
          if (/no hits/i.test(d.detail || "")) {
            if (pill) {
              pill.textContent = "no hits";
              pill.className = "text-xs font-mono px-2 py-0.5 rounded-full border border-line text-slate-500";
            }
            if (body) body.innerHTML = '<div class="text-slate-400 font-mono text-sm">❌ No data found in local database</div>';
          }
        }
      });
      sse.addEventListener("finding", (e) => {
        const d = JSON.parse(e.data);
        ingestFindings([d.finding]);
        renderFindings();
        renderMetrics();
      });
      sse.addEventListener("snapshot", (e) => {
        const d = JSON.parse(e.data);
        appendSnapshot(d.snapshot);
      });
      sse.addEventListener("elasticsearch_hit", (e) => {
        const d = JSON.parse(e.data);
        appendEsHit(d.hit);
      });
      sse.addEventListener("result", (e) => {
        const d = JSON.parse(e.data);
        // partial result emitted by engine before persist; full payload in 'complete'
        ingestFindings(d.payload.findings || []);
      });
      sse.addEventListener("complete", (e) => {
        const d = JSON.parse(e.data);
        state.currentRecord = d.payload;
        ingestFindings(d.payload.findings || []);
        renderDashboard(d.payload);
        sse.close(); state.sse = null;
        resolve();
      });
      sse.addEventListener("error", (e) => {
        sse.close(); state.sse = null;
        reject(new Error("stream error or disconnected"));
      });
    });
  }

  function ingestFindings(list) {
    for (const f of list) state.findings.set(f.key, f);
  }

  function synthFromDorks(kind, value, j) {
    return {
      query_kind: kind, query_value: value,
      started_at: new Date().toISOString(), finished_at: new Date().toISOString(),
      summary: { dorks_only: true, dork_count: j.count },
      findings: [], related_usernames: [], related_emails: [], related_phones: [],
      related_websites: [], related_domains: [],
      social_profiles: [], websites: [], whois_records: [], profile_snapshots: [],
      dorks: j.dorks, metadata_snippets: [],
      elasticsearch_results: [], elasticsearch_summary: {},
      local_db: { source: "local_db (elasticsearch tc_index)",
                  trust_level: "HIGH (AUTHORITATIVE)", found: false,
                  count: 0, records: [] },
      external_osint: { source: "web_osint (dorks + crawling + social)",
                        trust_level: "unverified / evidence-based",
                        confidence: 0, confidence_label: "weak",
                        results: { social_profiles: [], emails_found: [], phones_found: [],
                                   usernames_found: [], domains_found: [],
                                   dork_sources: j.dorks, profile_snapshots: [],
                                   image_clusters: [], whois_records: [],
                                   metadata_snippets: [] }},
      final_summary: { local_db_match: false, external_match: false,
                       key_note: "Local DB is authoritative. External OSINT is supplementary.",
                       confidence_logic: { local_db: 0, external_osint: 0,
                                           final_decision: "based on external OSINT (no local DB match)",
                                           merge_policy: "no_merge — sources kept separate" }},
      timeline: [{ timestamp: new Date().toISOString(), stage: "dorks", detail: `${j.count} dorks generated` }],
      confidence_score: 0, confidence_label: "weak",
      graph: { nodes: [], edges: [] },
    };
  }

  function setRunning(on) {
    $("#run-btn").disabled = on;
    $("#run-spinner").classList.toggle("hidden", !on);
    $("#run-label").textContent = on ? "Scanning…" : "Run search";
  }

  // --- Render dashboard ---
  function renderDashboard(p) {
    $("#dashboard").classList.remove("hidden");
    renderMetrics();
    renderSummary(p);
    renderTimeline(p.timeline || []);
    renderGraph(p.graph || { nodes: [], edges: [] });
    renderFindings();
    renderDorks(p.dorks || []);
    renderWhois(p.whois_records || []);
    renderSnapshots(p.profile_snapshots || []);
    // Dual-layer: local DB (authoritative) and external OSINT (unverified)
    // are rendered into separate, clearly-labeled sections — NEVER merged.
    // Accept three response shapes, in priority order:
    //   1. `p.local_db` — current backend (records + found + count)
    //   2. `p.local_database` — older-naming back-compat
    //   3. `p.results` — flat top-level shape per the user's spec contract
    const localBlock = p.local_db
      || p.local_database
      || (Array.isArray(p.results)
            ? { records: p.results,
                count: typeof p.count === "number" ? p.count : p.results.length,
                found: typeof p.found === "boolean" ? p.found : p.results.length > 0,
                source: "local_db (elasticsearch tc_index)",
                trust_level: "100% TRUST (AUTHORITATIVE)" }
            : null);
    renderLocalDatabase(localBlock, p.elasticsearch_results || [], p.elasticsearch_summary || {});
    renderOsintBanner(p);
    renderFinalSummary(p.final_summary || null);
    renderTextReport(p.text_report || "");

    $("#btn-export-csv").onclick = () => { if (p.id) window.open(`/api/export/${p.id}/csv`, "_blank"); };
    $("#btn-export-pdf").onclick = () => { if (p.id) window.open(`/api/export/${p.id}/pdf`, "_blank"); };
    $("#btn-export-csv").disabled = !p.id;
    $("#btn-export-pdf").disabled = !p.id;
    // "Download Report" — works whether or not the search has been persisted.
    // If we have a DB id, hand off to the server PDF endpoint (best fidelity).
    // Otherwise build a self-contained text report from the in-memory result.
    const dlBtn = $("#btn-download-report");
    if (dlBtn) {
      dlBtn.disabled = false;
      dlBtn.onclick = () => downloadReport(p);
    }

    document.getElementById("dashboard").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderMetrics() {
    const p = state.currentRecord;
    const fs = Array.from(state.findings.values());
    if (p) {
      $("#m-conf").textContent = `${p.confidence_score} (${p.confidence_label})`;
      $("#m-conf").className = `metric-value text-${confColor(p.confidence_label)}`;
    }
    $("#m-verified").textContent = fs.filter(f => f.verified).length;
    $("#m-findings").textContent = fs.length;
    $("#m-users").textContent = fs.filter(f => f.type === "username").length;
    $("#m-emails").textContent = fs.filter(f => f.type === "email").length;
    $("#m-profiles").textContent = fs.filter(f => f.type === "social_profile").length;
  }

  function renderFindings() {
    const el = $("#findings-list");
    el.innerHTML = "";
    let items = Array.from(state.findings.values());
    if (state.filters.type) items = items.filter(f => f.type === state.filters.type);
    if (state.filters.conf) items = items.filter(f => f.confidence >= state.filters.conf);
    if (state.filters.verified) items = items.filter(f => f.verified);
    items.sort((a, b) => b.confidence - a.confidence);

    if (!items.length) {
      el.innerHTML = '<div class="text-slate-500 text-sm md:col-span-2">No findings match the current filters.</div>';
      return;
    }
    for (const f of items) el.appendChild(renderFindingCard(f));
  }

  function renderFindingCard(f) {
    const div = document.createElement("div");
    div.className = "finding-card";
    const sources = (f.sources || []).map(s => {
      if (!s.url || s.url.startsWith("urn:")) {
        return `<span class="source-link" title="internal">${escapeHTML(s.source_type)}</span>`;
      }
      return `<a class="source-link" href="${s.url}" target="_blank" rel="noopener" title="${escapeHTML(s.title || s.url)}">${escapeHTML(s.source_type)} · ${escapeHTML(shortHost(s.url))}</a>`;
    }).join("");

    const badge = f.verified
      ? `<span class="verified-badge">✓ verified</span>`
      : `<span class="unverified-badge">${f.label}</span>`;

    // Signal trail (the +15 / -30 / etc breakdown)
    let signalsHTML = "";
    if (state.filters.showSignals && (f.signals || []).length) {
      const rows = f.signals.map(s => {
        const cls = s.delta >= 0 ? "signal-pos" : "signal-neg";
        const sign = s.delta >= 0 ? "+" : "−";
        return `<div class="signal-row">
          <span class="signal-delta ${cls}">${sign}${Math.abs(s.delta)}</span>
          <span class="signal-kind">${escapeHTML(s.kind)}</span>
          <span class="signal-text">${escapeHTML(s.reason)}</span>
        </div>`;
      }).join("");
      const sum = f.signals.reduce((a, s) => a + s.delta, 0);
      signalsHTML = `<div class="signals">${rows}<div class="tier-row">Σ = ${sum} → clamp(0,100) = ${f.confidence}</div></div>`;
    } else {
      const reasons = (f.match_reasons || []).map(r => `<li>${escapeHTML(r)}</li>`).join("");
      if (reasons) signalsHTML = `<ul class="reasons">${reasons}</ul>`;
    }

    div.innerHTML = `
      <div class="head">
        <div class="flex items-center gap-2">
          <span class="type">${escapeHTML(f.type)}</span>
          ${badge}
        </div>
        <span class="conf-badge conf-${f.label}">${f.confidence} · ${f.label}</span>
      </div>
      <div class="value">${linkify(f)}</div>
      ${signalsHTML}
      ${sources ? `<div class="sources">${sources}</div>` : ""}
    `;
    return div;
  }

  function linkify(f) {
    const v = escapeHTML(f.value);
    if (f.type === "email") return `<a href="mailto:${v}" class="hover:text-accent">${v}</a>`;
    if (f.type === "social_profile" || f.type === "website") return `<a href="${f.value}" target="_blank" rel="noopener" class="hover:text-accent">${v}</a>`;
    if (f.type === "domain") return `<a href="https://${f.value}" target="_blank" rel="noopener" class="hover:text-accent">${v}</a>`;
    if (f.type === "phone") return `<a href="tel:${f.value}" class="hover:text-accent">${v}</a>`;
    return v;
  }

  function renderSummary(p) {
    const el = $("#identity-summary");
    el.innerHTML = "";
    const rows = [
      ["Query", `<span class="font-mono text-accent">${escapeHTML(p.query_kind)}</span> = <span class="font-mono">${escapeHTML(p.query_value)}</span>`],
      ["Confidence", `<span class="conf-badge conf-${p.confidence_label}">${p.confidence_score} / 100 — ${p.confidence_label}</span>`],
      ["Findings", `${(p.findings || []).length} (${(p.findings || []).filter(f => f.verified).length} verified)`],
      ["Started", `<span class="font-mono text-xs text-slate-400">${escapeHTML(p.started_at)}</span>`],
      ["Finished", `<span class="font-mono text-xs text-slate-400">${escapeHTML(p.finished_at || '—')}</span>`],
    ];
    if (p.email_report) {
      const r = p.email_report;
      rows.push(["Email valid", r.is_valid ? "✅" : "❌"]);
      if (r.gravatar_exists) rows.push(["Gravatar", `<a class="text-accent" target="_blank" href="${r.gravatar_url}">found</a>`]);
      if (r.breach_count != null) rows.push(["Breaches", `<span class="text-danger">${r.breach_count}</span>`]);
    }
    if (p.phone_report) {
      const r = p.phone_report;
      rows.push(["Phone valid", r.is_valid ? "✅" : "❌"]);
      if (r.e164) rows.push(["E.164", `<span class="font-mono">${escapeHTML(r.e164)}</span>`]);
      if (r.region) rows.push(["Region", escapeHTML(r.region)]);
      if (r.carrier) rows.push(["Carrier", escapeHTML(r.carrier)]);
    }
    for (const [k, v] of rows) {
      const r = document.createElement("div");
      r.className = "flex justify-between gap-3 border-b border-line/40 py-1.5";
      r.innerHTML = `<span class="text-slate-500 text-xs uppercase tracking-wider">${escapeHTML(k)}</span><span class="text-right">${v}</span>`;
      el.appendChild(r);
    }
  }

  function renderTimeline(tl) {
    const el = $("#timeline");
    el.innerHTML = "";
    for (const t of tl) {
      const r = document.createElement("div");
      r.className = "timeline-row";
      r.innerHTML = `<span class="ts">${escapeHTML((t.timestamp || '').replace('T', ' ').replace('+00:00','Z'))}</span><span class="stage">${escapeHTML(t.stage)}</span><span class="detail">${escapeHTML(t.detail)}</span>`;
      el.appendChild(r);
    }
  }

  function renderGraph(g) {
    if (state.network) { state.network.destroy(); state.network = null; }
    if (!g || !g.nodes || !g.nodes.length) {
      $("#graph").innerHTML = '<div class="text-slate-500 text-sm p-6 font-mono">// no graph data</div>';
      return;
    }
    const groupColor = {
      name: "#22d3ee", username: "#a78bfa", email: "#34d399",
      phone: "#fbbf24", social_profile: "#f43f5e",
      website: "#94a3b8", domain: "#60a5fa", person: "#22d3ee",
    };
    const nodes = g.nodes.map((n) => ({
      id: n.id,
      label: truncate(n.label || "", 22),
      title: `${n.label}\nconfidence: ${n.confidence}${n.verified ? " (verified)" : ""}`,
      color: {
        background: n.verified ? "#0f1d18" : "#0b0f17",
        border: groupColor[n.group] || "#22d3ee",
        highlight: { background: "#111826", border: "#22d3ee" },
      },
      borderWidth: n.verified ? 3 : 1,
      font: { color: "#e2e8f0", face: "JetBrains Mono", size: 12 },
      shape: n.id === g.seed ? "diamond" : "dot",
      size: n.id === g.seed ? 22 : Math.max(8, Math.min(22, 8 + n.confidence / 10)),
    }));
    const edges = (g.edges || []).map((e) => ({
      from: e.from, to: e.to,
      color: { color: "#1f2a3a", highlight: "#22d3ee" },
      smooth: { type: "dynamic" },
    }));
    state.network = new vis.Network($("#graph"), { nodes, edges }, {
      physics: { stabilization: { iterations: 220 }, barnesHut: { gravitationalConstant: -16000, springLength: 130 } },
      interaction: { hover: true, zoomView: true },
    });
  }

  function renderDorks(dorks) {
    const el = $("#dorks-list");
    el.innerHTML = "";
    if (!dorks.length) { el.innerHTML = '<div class="text-slate-500 text-sm">No dorks generated.</div>'; return; }
    for (const d of dorks) {
      const row = document.createElement("div");
      row.className = "dork-row";
      row.innerHTML = `
        <div class="label">${escapeHTML(d.label)}</div>
        <div class="query">${escapeHTML(d.query)}</div>
        <div class="links">
          <a target="_blank" rel="noopener" href="${d.google}">google</a>
          <a target="_blank" rel="noopener" href="${d.bing}">bing</a>
          <a target="_blank" rel="noopener" href="${d.duckduckgo}">ddg</a>
          <button class="copy-btn">copy</button>
        </div>`;
      row.querySelector(".copy-btn").addEventListener("click", () => navigator.clipboard.writeText(d.query));
      el.appendChild(row);
    }
  }

  function renderWhois(records) {
    const el = $("#whois-list");
    el.innerHTML = "";
    if (!records.length) { el.innerHTML = '<div class="text-slate-500 text-sm">No domains looked up.</div>'; return; }
    for (const w of records) {
      const div = document.createElement("div");
      div.className = "border border-line rounded-lg p-3 bg-panel2/50 text-xs";
      const contacts = (w.contacts || []).map(c =>
        `<div>${escapeHTML(c.roles || 'contact')}: ${escapeHTML(c.name || '')} ${c.email ? '· ' + escapeHTML(c.email) : ''} ${c.phone ? '· ' + escapeHTML(c.phone) : ''}</div>`
      ).join("");
      div.innerHTML = `
        <div class="flex justify-between"><div class="font-mono text-accent">${escapeHTML(w.domain)}</div><div class="text-slate-500">${escapeHTML(w.registrar || '')}</div></div>
        <div class="text-slate-400 mt-1">created: ${escapeHTML(w.created || '—')} · expires: ${escapeHTML(w.expires || '—')}</div>
        <div class="text-slate-500 mt-1">ns: ${(w.nameservers || []).map(escapeHTML).join(", ") || '—'}</div>
        ${contacts ? `<div class="text-slate-300 mt-2 space-y-0.5">${contacts}</div>` : ""}
        ${w.error ? `<div class="text-danger mt-1">${escapeHTML(w.error)}</div>` : ""}
      `;
      el.appendChild(div);
    }
  }

  function renderSnapshots(snaps) {
    const el = $("#snapshots-list");
    el.innerHTML = "";
    if (!snaps.length) { el.innerHTML = '<div class="text-slate-500 text-sm">No profile snapshots captured.</div>'; return; }
    for (const s of snaps) el.appendChild(snapshotCard(s));
  }

  function appendSnapshot(s) {
    const el = $("#snapshots-list");
    if (el.querySelector(".text-slate-500")) el.innerHTML = "";
    el.appendChild(snapshotCard(s));
  }

  // --- Local Database (Elasticsearch) — authoritative section ---
  function renderLocalDatabase(local, legacyHits, legacySummary) {
    const el = $("#es-results");
    const meta = $("#es-meta");
    const pill = $("#es-status-pill");
    if (!el) return;

    // Prefer the new `local_db` block (UPPERCASE NAME/PHONE/EMAIL/TAGS/ASONDATE
    // per spec); fall back to the v1 flat `elasticsearch_results` list (lowercase).
    // Normalize both shapes into the lowercase form `localDbCard` reads.
    const records = (local && Array.isArray(local.records))
      ? local.records.map(r => ({
          name: r.NAME ?? r.name ?? "",
          phone: r.PHONE ?? r.phone ?? "",
          email: r.EMAIL ?? r.email ?? "",
          tags: r.TAGS ?? r.tags ?? [],
          asondate: r.ASONDATE ?? r.asondate ?? "",
          confidence: r.confidence ?? 100,
          matched_field: r.matched_field, match_reason: r.match_reason ?? r.reason,
          match_strength: r.match_strength ?? r.confidence,
          es_id: r.es_id, es_score: r.es_score,
        }))
      : (legacyHits || []).map(h => ({
          name: h.name, phone: h.phone, email: h.email, tags: h.tags,
          asondate: h.asondate, confidence: 100,
          matched_field: h.matched_field, match_reason: h.reason,
          match_strength: h.confidence, es_id: h.es_id, es_score: h.es_score,
        }));
    el.innerHTML = "";

    if (!records.length) {
      pill.textContent = "no hits";
      pill.className = "text-xs font-mono px-2 py-0.5 rounded-full border border-line text-slate-500";
      meta.textContent = local
        ? `${escapeHTML(local.source || "")} · trust=${escapeHTML(local.trust_level || "")}`
        : "";
      const empty = (local && local.empty_message) || "❌ No data found in local database";
      el.innerHTML = `<div class="text-slate-400 font-mono text-sm">${escapeHTML(empty)}</div>`;
      return;
    }
    pill.textContent = `${records.length} verified record${records.length === 1 ? "" : "s"}`;
    pill.className = "text-xs font-mono px-2 py-0.5 rounded-full border border-ok/40 text-ok";
    const fields = legacySummary && legacySummary.by_field
      ? Object.entries(legacySummary.by_field).map(([k, v]) => `${k}:${v}`).join(" · ")
      : "";
    meta.textContent = `${(local && local.trust_level) ? local.trust_level : "HIGH (AUTHORITATIVE)"}` + (fields ? ` · ${fields}` : "");
    for (const r of records) el.appendChild(localDbCard(r));
  }

  function appendEsHit(h) {
    // SSE incremental hit — same authoritative styling. Engine streams
    // raw ESHit dicts; project them into the local-DB record shape.
    const el = $("#es-results");
    if (!el) return;
    if (el.querySelector(".text-slate-500")) el.innerHTML = "";
    el.appendChild(localDbCard({
      name: h.name, phone: h.phone, email: h.email, tags: h.tags,
      asondate: h.asondate, confidence: 100,
      matched_field: h.matched_field, match_reason: h.reason,
      match_strength: h.confidence, es_id: h.es_id, es_score: h.es_score,
    }));
    const pill = $("#es-status-pill");
    const cur = parseInt((pill.textContent || "0").replace(/\D/g, ""), 10) || 0;
    pill.textContent = `${cur + 1} verified record${cur + 1 === 1 ? "" : "s"}`;
    pill.className = "text-xs font-mono px-2 py-0.5 rounded-full border border-ok/40 text-ok";
  }

  function localDbCard(r) {
    // Authoritative record card. Confidence is ALWAYS 100 (trusted layer);
    // we surface match_strength as "ES match strength" so the analyst can
    // still see HOW the local DB matched without that score being mistaken
    // for the record's authoritative confidence.
    const div = document.createElement("div");
    div.className = "es-row border border-ok/30 rounded-lg p-3 bg-ok/5";
    const tags = (r.tags || []).slice(0, 8).map(t =>
      `<span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-panel border border-line text-slate-400">${escapeHTML(t)}</span>`
    ).join(" ");
    div.innerHTML = `
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-ok text-xs font-mono">✓ verified</span>
            <span class="font-semibold text-slate-100 truncate">${escapeHTML(r.name || "(no name)")}</span>
          </div>
          <div class="text-xs text-slate-300 font-mono mt-1 space-y-0.5">
            ${r.email ? `<div>📧 <span>${escapeHTML(r.email)}</span></div>` : ""}
            ${r.phone ? `<div>📞 <span>${escapeHTML(r.phone)}</span></div>` : ""}
          </div>
          ${tags ? `<div class="mt-2 flex flex-wrap gap-1">${tags}</div>` : ""}
        </div>
        <div class="text-right shrink-0">
          <div class="text-ok font-mono font-bold text-lg leading-tight">100</div>
          <div class="text-[10px] uppercase tracking-wider text-ok/80">authoritative</div>
        </div>
      </div>
      <div class="text-[11px] text-slate-500 font-mono mt-2 flex flex-wrap gap-x-3 gap-y-0.5">
        <span>match: <span class="text-slate-300">${escapeHTML(r.matched_field || "")}</span></span>
        <span>reason: <span class="text-slate-300">${escapeHTML(r.match_reason || "")}</span></span>
        ${typeof r.match_strength === "number" ? `<span>ES match strength: <span class="text-slate-300">${r.match_strength}</span></span>` : ""}
        ${r.asondate ? `<span>as of: <span class="text-slate-300">${escapeHTML(r.asondate)}</span></span>` : ""}
        ${r.es_id ? `<span>doc: <span class="text-slate-300">${escapeHTML(r.es_id)}</span></span>` : ""}
        ${typeof r.es_score === "number" ? `<span>_score: <span class="text-slate-300">${r.es_score}</span></span>` : ""}
      </div>`;
    return div;
  }

  function renderOsintBanner(p) {
    const meta = $("#osint-banner-meta");
    const body = $("#osint-stats-body");
    const ext = p.external_osint || {};
    const stats = ext.stats || {};
    const listings = ext.listings || [];
    const conf = (typeof ext.confidence === "number") ? `score=${ext.confidence}` : "";
    if (meta) meta.textContent = ext.trust_level ? `trust: ${ext.trust_level}${conf ? " · " + conf : ""}` : "";
    if (!body) return;

    const hasOsint = listings.length
      || (ext.results && (
        (ext.results.emails_found || []).length
        || (ext.results.usernames_found || []).length
        || (ext.results.phones_found || []).length
        || (ext.results.dork_sources || []).length));
    if (!hasOsint) {
      const empty = ext.empty_message || "❌ No external OSINT signals.";
      body.innerHTML = `<div class="text-slate-400 font-mono text-sm">${escapeHTML(empty)}</div>`;
      return;
    }
    const statsRow = `
      <div class="grid grid-cols-2 md:grid-cols-5 gap-2 text-center">
        <div class="metric"><div class="metric-label">Total Findings</div><div class="metric-value text-slate-100">${stats.total_findings ?? 0}</div></div>
        <div class="metric"><div class="metric-label">Verified Profiles</div><div class="metric-value text-ok">${stats.verified_profiles ?? 0}</div></div>
        <div class="metric"><div class="metric-label">Usernames</div><div class="metric-value text-accent2">${stats.usernames ?? 0}</div></div>
        <div class="metric"><div class="metric-label">Emails</div><div class="metric-value text-accent">${stats.emails ?? 0}</div></div>
        <div class="metric"><div class="metric-label">Confidence</div><div class="metric-value text-amber-300">${stats.confidence_score ?? 0}/100</div></div>
      </div>`;
    const items = listings.slice(0, 50).map((l, i) => `
      <div class="border border-line/60 rounded-lg p-2 bg-panel2/30 text-xs">
        <div class="flex items-center justify-between">
          <div class="font-mono text-slate-300">[${i + 1}] Platform: <span class="text-amber-200">${escapeHTML((l.platform || '').replace(/^./, c => c.toUpperCase()))}</span></div>
          <div class="font-mono text-amber-300">conf ${l.confidence | 0}${l.verified ? ' ✓' : ''}</div>
        </div>
        ${l.username ? `<div class="text-slate-400 font-mono ml-6">Username: <span class="text-slate-200">${escapeHTML(l.username)}</span></div>` : ""}
        ${l.link ? `<div class="text-slate-400 font-mono ml-6 truncate">Link: <a href="${l.link}" target="_blank" rel="noopener" class="text-accent hover:underline">${escapeHTML(l.link)}</a></div>` : ""}
      </div>`).join("");
    body.innerHTML = `${statsRow}${items ? `<div class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2 max-h-96 overflow-y-auto">${items}</div>` : ""}`;
  }

  function renderFinalSummary(s) {
    const el = $("#final-summary-body");
    if (!el) return;
    if (!s) { el.innerHTML = '<div class="text-slate-500 text-sm">No summary yet.</div>'; return; }
    const cl = s.confidence_logic || {};
    const dbYN = s.local_db_match_yn || (s.local_db_match ? "YES" : "NO");
    const osYN = s.osint_match_yn || (s.external_match ? "YES" : "NO");
    const score = s.summary_score ?? cl.local_db ?? cl.external_osint ?? 0;
    const dbColor = dbYN === "YES" ? "text-ok" : "text-slate-500";
    const osColor = osYN === "YES" ? "text-amber-300" : "text-slate-500";
    el.innerHTML = `
      <pre class="font-mono text-sm leading-7 m-0 text-slate-200">Local DB Match: <span class="${dbColor} font-bold">${escapeHTML(dbYN)}</span>
OSINT Match:    <span class="${osColor} font-bold">${escapeHTML(osYN)}</span>
Confidence Score: <span class="text-accent font-bold">${score}/100</span></pre>
      <div class="text-xs text-slate-400 italic">${escapeHTML(s.key_note || "")}</div>
      <div class="grid grid-cols-2 md:grid-cols-3 gap-3 mt-2 text-sm">
        <div class="metric"><div class="metric-label">Local DB</div><div class="metric-value text-ok">${cl.local_db ?? 0}</div></div>
        <div class="metric"><div class="metric-label">External OSINT</div><div class="metric-value text-amber-300">${cl.external_osint ?? 0}</div></div>
        <div class="metric md:col-span-1"><div class="metric-label">Decision</div><div class="text-xs font-mono text-slate-200">${escapeHTML(cl.final_decision || "")}</div></div>
      </div>
      <div class="text-[11px] text-slate-500 font-mono">merge policy: <span class="text-slate-300">${escapeHTML(cl.merge_policy || "no_merge")}</span></div>
    `;
  }

  function renderTextReport(text) {
    const el = $("#text-report-body");
    const btn = $("#copy-report-btn");
    if (!el) return;
    el.textContent = text || "(no report yet)";
    if (btn) {
      btn.onclick = () => {
        if (text) navigator.clipboard.writeText(text).catch(() => {});
      };
      btn.disabled = !text;
    }
  }

  function snapshotCard(s) {
    const div = document.createElement("div");
    div.className = "snap-card";
    div.innerHTML = `
      ${s.avatar_url ? `<img src="/api/image?url=${encodeURIComponent(s.avatar_url)}" referrerpolicy="no-referrer" alt="" loading="lazy" onerror="this.remove()" />` : ""}
      <div class="flex-1 min-w-0">
        <a href="${s.url}" target="_blank" rel="noopener" class="text-accent hover:underline font-mono text-xs">${escapeHTML(s.platform)}/${escapeHTML(s.handle || '')}</a>
        <div class="text-slate-100 font-semibold truncate">${escapeHTML(s.display_name || '')}</div>
        <div class="text-slate-400 text-xs line-clamp-2">${escapeHTML(s.bio || '')}</div>
      </div>`;
    return div;
  }

  // --- History ---
  $("#refresh-history").addEventListener("click", refreshHistory);

  async function refreshHistory() {
    const r = await fetch("/api/history?limit=12");
    if (!r.ok) return;
    const j = await r.json();
    const el = $("#history-list");
    el.innerHTML = "";
    if (!j.items.length) {
      el.innerHTML = '<div class="text-slate-500 text-sm md:col-span-2 lg:col-span-3">No prior searches yet.</div>';
      return;
    }
    for (const it of j.items) {
      const a = document.createElement("a");
      a.href = "#"; a.className = "history-card";
      a.innerHTML = `
        <div class="flex justify-between items-start">
          <div>
            <div class="text-xs font-mono uppercase text-slate-500">${escapeHTML(it.query_kind)}</div>
            <div class="font-semibold text-slate-200 truncate max-w-[16rem]">${escapeHTML(it.query_value)}</div>
          </div>
          <span class="conf-badge conf-${it.confidence_label}">${it.confidence}</span>
        </div>
        <div class="text-xs text-slate-500 mt-2 font-mono">${new Date(it.created_at).toLocaleString()}</div>`;
      a.addEventListener("click", async (e) => {
        e.preventDefault();
        const r2 = await fetch(`/api/history/${it.id}`);
        if (!r2.ok) return;
        const data = await r2.json();
        data.id = it.id;
        state.findings.clear();
        ingestFindings(data.findings || []);
        state.currentRecord = data;
        renderDashboard(data);
      });
      el.appendChild(a);
    }
  }

  // --- Download Report -----------------------------------------------------
  // Single entry point for the "Download Report" button. Tries server-side PDF
  // first (best fidelity: backend renders the same plain-text report you see
  // in the dashboard, plus PDF formatting). If the search hasn't been persisted
  // to the DB yet (no `id`), falls back to a client-side .txt build so the
  // download still works in every state — including dorks-only / SSE flows.
  function downloadReport(p) {
    if (!p) return;
    if (p.id) {
      // Server-side PDF — proven path, identical content to the existing PDF
      // export button. Opens in a new tab so the browser handles the download.
      window.open(`/api/export/${p.id}/pdf`, "_blank");
      return;
    }
    // Client-side text report — assembled from the in-memory result.
    const text = buildClientReport(p);
    const safe = (s) => String(s || "").replace(/[^a-z0-9._-]+/gi, "_").slice(0, 60);
    const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    const fname = `osint-report-${safe(p.query_kind)}-${safe(p.query_value)}-${ts}.txt`;
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = fname;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  }

  // Compose a readable text report from the current result. Prefers the
  // backend-rendered `text_report` (same one the dashboard's Text Report card
  // displays); appends a "Findings" appendix so the file isn't ever empty.
  function buildClientReport(p) {
    const lines = [];
    const bar = "=".repeat(60);
    lines.push(bar);
    lines.push("OSINT PLATFORM — SEARCH REPORT");
    lines.push(bar);
    lines.push(`Query:      ${p.query_kind || "—"} = ${p.query_value || "—"}`);
    lines.push(`Started:    ${p.started_at || "—"}`);
    lines.push(`Finished:   ${p.finished_at || "—"}`);
    lines.push(`Generated:  ${new Date().toISOString()}`);
    if (typeof p.confidence_score === "number") {
      lines.push(`Confidence: ${p.confidence_score}/100 (${p.confidence_label || "—"})`);
    }
    lines.push("");

    // Use the backend's pre-rendered report verbatim when available — keeps
    // the dual-section layout (Local DB + OSINT Findings) consistent with the
    // dashboard's Text Report card.
    if (p.text_report && typeof p.text_report === "string" && p.text_report.trim()) {
      lines.push(p.text_report.trim());
      lines.push("");
    }

    // Always append a structured Findings appendix so the report is complete
    // even when the engine couldn't produce a text_report (e.g. dorks-only).
    const findings = Array.isArray(p.findings) ? p.findings : [];
    if (findings.length) {
      lines.push(bar);
      lines.push(`FINDINGS APPENDIX (${findings.length})`);
      lines.push(bar);
      findings
        .slice()
        .sort((a, b) => (b.confidence || 0) - (a.confidence || 0))
        .forEach((f, i) => {
          const verified = f.verified ? " ✓ VERIFIED" : "";
          lines.push(`[${i + 1}] ${f.type || "?"}: ${f.value || ""}${verified}`);
          lines.push(`    confidence: ${f.confidence ?? 0} (${f.label || "—"})`);
          (f.match_reasons || []).slice(0, 6).forEach(r => lines.push(`    - ${r}`));
          (f.sources || []).slice(0, 4).forEach(s => {
            const url = (s && s.url && !String(s.url).startsWith("urn:")) ? s.url : "(internal)";
            lines.push(`    src: ${s.source_type || "?"}  ${url}`);
          });
          lines.push("");
        });
    }

    // Local DB matches — short tabular block (the human-readable section the
    // user sees in the green DB panel).
    const ldb = p.local_db || p.local_database || null;
    const dbRecs = ldb && Array.isArray(ldb.records) ? ldb.records : [];
    if (dbRecs.length) {
      lines.push(bar);
      lines.push(`VERIFIED LOCAL DATABASE (${dbRecs.length})`);
      lines.push(bar);
      dbRecs.forEach((r, i) => {
        const tags = Array.isArray(r.TAGS) ? r.TAGS.join(", ") : (r.TAGS || "");
        const date = (r.ASONDATE || "").split(" ")[0];
        lines.push(`Record ${i + 1}`);
        lines.push(`  Name:   ${r.NAME || "—"}`);
        lines.push(`  Phone:  ${r.PHONE || "—"}`);
        lines.push(`  Email:  ${r.EMAIL || "—"}`);
        if (tags) lines.push(`  Tags:   ${tags}`);
        if (date) lines.push(`  Date:   ${date}`);
        if (r.matched_field) lines.push(`  Match:  ${r.matched_field} (${r.match_reason || ""})`);
        lines.push("");
      });
    }

    // Related identifiers — flat lists for quick reference.
    const sectionList = (label, arr) => {
      if (Array.isArray(arr) && arr.length) {
        lines.push(`${label} (${arr.length}):`);
        arr.slice(0, 50).forEach(v => lines.push(`  - ${v}`));
        lines.push("");
      }
    };
    lines.push(bar);
    lines.push("RELATED IDENTIFIERS");
    lines.push(bar);
    sectionList("Usernames", p.related_usernames);
    sectionList("Emails",    p.related_emails);
    sectionList("Phones",    p.related_phones);
    sectionList("Websites",  p.related_websites);
    sectionList("Domains",   p.related_domains);

    if (Array.isArray(p.social_profiles) && p.social_profiles.length) {
      lines.push(`Social profiles (${p.social_profiles.length}):`);
      p.social_profiles.slice(0, 60).forEach(sp =>
        lines.push(`  - ${sp.platform || "?"} / ${sp.handle || ""}  ${sp.url || ""}`));
      lines.push("");
    }

    lines.push(bar);
    lines.push("End of report — for ethical, lawful intelligence work only.");
    lines.push(bar);
    return lines.join("\n");
  }

  // --- helpers ---
  function escapeHTML(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
  }
  function truncate(s, n) { return s.length > n ? s.slice(0, n - 1) + "…" : s; }
  function shortHost(url) {
    try { return new URL(url).host.replace(/^www\./, ""); } catch { return url; }
  }
  function confColor(label) {
    return ({
      verified: "ok", high: "ok", likely: "ok",
      possible: "yellow-400", medium: "yellow-400",
      low: "orange-400",
      weak: "slate-400", unverified: "slate-400", none: "slate-500",
    })[label] || "slate-400";
  }

  refreshHistory();
})();
