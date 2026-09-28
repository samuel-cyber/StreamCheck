    const queueEl = document.getElementById("queue");
    let items = [];
    let focusIdx = 0;

    function csrfToken() {
      const m = document.cookie.match(/(?:^|;\s*)riparia_csrf=([^;]+)/);
      return m ? decodeURIComponent(m[1]) : "";
    }

    function skeletonCard() {
      return `<div class="card review"><div class="review-grid">
        <div class="photo-pane skeleton" style="height:280px"></div>
        <div class="content-pane">
          <div class="skeleton" style="height:18px;width:80%"></div>
          <div class="skeleton" style="height:56px"></div>
          <div class="skeleton" style="height:12px;width:40%"></div>
        </div></div></div>`;
    }

    function confTone(c) { return c >= 0.75 ? "ok" : c >= 0.5 ? "warn" : "danger"; }

    function card(o, idx) {
      const pct = Math.round((o.ai_confidence ?? 0) * 100);
      const chips = (o.ai_indicators ?? []).map(i => `<span class="chip">${escapeHtml(i.replaceAll("_", " "))}</span>`).join("");
      const when = new Date(o.created_at).toLocaleString();
      return `
      <article class="card review" data-id="${o.id}" data-idx="${idx}" tabindex="0" aria-label="Observation ${o.id}">
        <div class="review-top">
          <span class="id">OBS-${String(o.id).padStart(4, "0")}</span>
          <span class="id">${escapeHtml(when)}</span>
        </div>
        <div class="review-grid">
          <div class="photo-pane"><img src="${escapeHtml(o.photo_url)}" alt="Citizen-submitted stream photo" loading="lazy"></div>
          <div class="content-pane">
            <blockquote class="quote">${escapeHtml(o.text_description)}<span class="citizen">Citizen report</span></blockquote>
            <div class="conf-block">
              <div class="row"><span class="label">AI confidence</span><span class="val">${pct}%</span></div>
              <div class="meter"><i data-w="${pct}"></i></div>
            </div>
            <div class="ai-note">
              <span class="ai-tag">AI assessment</span>
              ${escapeHtml(o.ai_reasoning)}
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">${chips || '<span class="chip muted">no indicators detected</span>'}</div>
            <div class="decide">
              <button class="btn btn-approve" data-act="approve">✓ Approve &amp; commit</button>
              <button class="btn btn-reject" data-act="reject">✗ Reject</button>
            </div>
          </div>
        </div>
        <div class="verdict-slot"></div>
      </article>`;
    }

    function showVerdict(el, cls, html) {
      const slot = el.querySelector(".verdict-slot");
      slot.innerHTML = `<div class="verdict ${cls} fade-in">${html}</div>`;
    }

    async function decide(el, action) {
      const id = el.dataset.id;
      const buttons = el.querySelectorAll(".decide .btn");
      buttons.forEach(b => b.disabled = true);
      try {
        const updated = await api(`/api/v1/observations/${id}/${action}`, {
          method: "POST",
          headers: { "X-CSRF-Token": csrfToken() },
        });
        if (action === "approve") {
          showVerdict(el, "ok", `✓ Committed to FHIR — Observation/${escapeHtml(updated.fhir_id)}<a target="_blank" rel="noopener" href="${escapeHtml(FHIR_BASE)}${escapeHtml(updated.fhir_id)}">view resource ↗</a>`);
        } else {
          showVerdict(el, "ok", `✗ Rejected — nothing sent to FHIR`);
        }
        el.classList.add("resolved");
        setTimeout(() => { el.remove(); loadStats(); }, 700);
      } catch (err) {
        buttons.forEach(b => b.disabled = false);
        if (err.status === 401) { location.href = "/login.html"; return; }
        showVerdict(el, "err", `⚠ ${escapeHtml(err.message)}`);
      }
    }

    const FHIR_BASE = "https://hapi.fhir.org/baseR4/Observation/";

    function bindCard(el) {
      el.querySelectorAll(".decide .btn").forEach(btn => {
        btn.addEventListener("click", () => decide(el, btn.dataset.act));
      });
      el.addEventListener("focus", () => { focusIdx = +el.dataset.idx; });
    }

    async function loadStats() {
      try {
        const all = await api("/api/v1/observations?limit=100");
        const count = s => all.items.filter(i => i.status === s).length;
        document.getElementById("stat-approved").textContent = count("approved");
        document.getElementById("stat-rejected").textContent = count("rejected");
      } catch { /* stats are non-critical */ }
    }

    async function loadQueue() {
      queueEl.innerHTML = skeletonCard() + skeletonCard();
      try {
        const data = await api("/api/v1/queue");
        items = data.items ?? [];
        document.getElementById("stat-pending").textContent = items.length;
        document.getElementById("updated-at").textContent = "updated " + new Date().toLocaleTimeString();

        if (!items.length) {
          queueEl.innerHTML = `<div class="card state-block">
            <h2>Queue clear</h2>
            <p>Every observation has been reviewed. New citizen submissions will appear here automatically.</p>
          </div>`;
          return;
        }
        queueEl.innerHTML = items.map(card).join("");
        queueEl.querySelectorAll(".review").forEach(el => {
          bindCard(el);
          requestAnimationFrame(() => {
            const bar = el.querySelector(".meter i");
            if (bar) bar.style.width = bar.dataset.w + "%";
          });
        });
        loadStats();
      } catch (err) {
        if (err.status === 401) { location.href = "/login.html"; return; }
        queueEl.innerHTML = `<div class="card state-block">
          <h2>Couldn't load the queue</h2>
          <p>${escapeHtml(err.message)}</p>
          <p style="margin-top:12px"><button class="btn btn-ghost" id="retry-btn">Retry</button></p>
        </div>`;
        document.getElementById("retry-btn").addEventListener("click", loadQueue);
      }
    }

    // keyboard shortcuts
    document.addEventListener("keydown", (e) => {
      if (e.target.matches("input, textarea")) return;
      const el = queueEl.querySelector(`.review[data-idx="${focusIdx}"]`);
      if (!el) return;
      if (e.key === "a" || e.key === "A") decide(el, "approve");
      if (e.key === "r" || e.key === "R") decide(el, "reject");
    });

    document.getElementById("logout-btn").addEventListener("click", async () => {
      try { await api("/api/v1/auth/logout", { method: "POST" }); } catch {}
      location.href = "/login.html";
    });

    // Show who is signed in (best effort)
    api("/api/v1/observations?limit=1").then(() => {
      document.getElementById("who").textContent = "reviewer";
    }).catch(() => {});

    loadQueue();
  
