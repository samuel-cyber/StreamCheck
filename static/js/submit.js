    const form = document.getElementById("obs-form");
    const photo = document.getElementById("photo");
    const dz = document.getElementById("dropzone");
    const dzText = document.getElementById("dz-text");
    const preview = document.getElementById("preview");
    const desc = document.getElementById("description");
    const counter = document.getElementById("char-count");
    const btn = document.getElementById("submit-btn");
    const statusEl = document.getElementById("status");

    desc.addEventListener("input", () => counter.textContent = desc.value.length);

    function showFile(file) {
      if (!file) return;
      preview.src = URL.createObjectURL(file);
      preview.style.display = "block";
      dzText.textContent = file.name;
    }
    photo.addEventListener("change", () => showFile(photo.files[0]));
    ["dragover", "dragenter"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("over"); }));
    ["dragleave", "drop"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove("over"); }));
    dz.addEventListener("drop", e => {
      if (e.dataTransfer.files.length) {
        photo.files = e.dataTransfer.files;
        showFile(photo.files[0]);
      }
    });

    function renderError(msg) {
      statusEl.style.display = "block";
      statusEl.innerHTML = `<div class="panel error fade-in"><h3>Submission failed</h3><p>${escapeHtml(msg)}</p></div>`;
    }

    function renderSuccess(obs) {
      const pct = Math.round((obs.ai_confidence ?? 0) * 100);
      const chips = (obs.ai_indicators ?? []).map(i => `<span class="chip">${escapeHtml(i.replaceAll("_", " "))}</span>`).join("");
      statusEl.style.display = "block";
      statusEl.innerHTML = `
        <div class="panel success fade-in">
          <h3>✓ Observation received — now in human review</h3>
          <p>${escapeHtml(obs.ai_reasoning ?? "")}</p>
          <div class="conf-row">
            <span class="conf-num" data-count="${pct}">0%</span>
            <div class="meter"><i data-w="${pct}"></i></div>
          </div>
          <div class="chips">${chips || '<span class="chip muted">no indicators detected</span>'}</div>
        </div>`;
      requestAnimationFrame(() => {
        const bar = statusEl.querySelector(".meter i");
        const num = statusEl.querySelector(".conf-num");
        if (bar) bar.style.width = bar.dataset.w + "%";
        if (num) {
          const target = +num.dataset.count; const t0 = performance.now();
          (function tick(t) {
            const p = Math.min(1, (t - t0) / 900);
            num.textContent = Math.round(target * (1 - Math.pow(1 - p, 3))) + "%";
            if (p < 1) requestAnimationFrame(tick);
          })(t0);
        }
      });
      form.reset(); preview.style.display = "none";
      dzText.textContent = "Tap to choose a photo — or drop one here";
      counter.textContent = "0";
    }

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!photo.files[0]) return renderError("Please choose a photo first.");
      if (desc.value.trim().length < 3) return renderError("Please describe what you observed (at least 3 characters).");

      btn.disabled = true;
      btn.innerHTML = `<span class="spinner"></span>Assessing…`;
      statusEl.style.display = "block";
      statusEl.innerHTML = `<div class="panel"><span class="spinner"></span>Running AI assessment against published indicators…</div>`;

      const fd = new FormData();
      fd.append("photo", photo.files[0]);
      fd.append("text_description", desc.value.trim());

      try {
        const obs = await api("/api/v1/observations", { method: "POST", body: fd });
        renderSuccess(obs);
      } catch (err) {
        renderError(err.message);
      } finally {
        btn.disabled = false;
        btn.textContent = "Submit observation";
      }
    });
  
