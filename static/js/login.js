    const form = document.getElementById("login-form");
    const err = document.getElementById("err");
    const go = document.getElementById("go");

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      err.style.display = "none";
      go.disabled = true; go.textContent = "Signing in…";
      const fd = new FormData(form);
      try {
        const res = await fetch("/api/v1/auth/login", {
          method: "POST",
          credentials: "same-origin",
          body: new URLSearchParams({ username: fd.get("username"), password: fd.get("password") }),
        });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(body?.detail?.message || "Sign in failed");
        location.href = "/dashboard.html";
      } catch (ex) {
        err.textContent = ex.message;
        err.style.display = "block";
        go.disabled = false; go.textContent = "Sign in";
      }
    });
  
