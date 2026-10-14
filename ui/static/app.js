function toast(msg, kind = "ok") {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.className = `toast show ${kind}`;
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), 4200);
}

async function postForm(url, formEl, btn) {
  const fd = formEl ? new FormData(formEl) : new FormData();
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(url, { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || `Request failed (${res.status})`);
    }
    return data;
  } finally {
    if (btn) btn.disabled = false;
  }
}

function syncPackageTitleFromIdea(form) {
  const idea = (form.querySelector("[name=idea]")?.value || "").trim();
  const pkgEl = form.querySelector("[name=package_json]");
  const seoEl = form.querySelector("[name=seo_json]");
  if (!idea || !pkgEl) return;
  try {
    const pkg = JSON.parse(pkgEl.value || "{}");
    if (!pkg.title) pkg.title = idea.slice(0, 70);
    if (!pkg.thumbnail_text) pkg.thumbnail_text = "नई वीडियो";
    pkgEl.value = JSON.stringify(pkg, null, 2);
  } catch (_) {
    pkgEl.value = JSON.stringify(
      { title: idea.slice(0, 70), thumbnail_text: "नई वीडियो", thumbnail_brief: "हाई कंट्रास्ट हिंदी टेक्स्ट" },
      null,
      2
    );
  }
  if (seoEl) {
    try {
      const seo = JSON.parse(seoEl.value || "{}");
      if (!seo.description) seo.description = idea + "\n\n#Shorts #हिंदी";
      if (!seo.title) seo.title = idea.slice(0, 70);
      seoEl.value = JSON.stringify(seo, null, 2);
    } catch (_) {
      seoEl.value = JSON.stringify(
        { title: idea.slice(0, 70), description: idea + "\n\n#Shorts #हिंदी", tags: [], category_id: "22" },
        null,
        2
      );
    }
  }
}

function bindCreateForm() {
  const form = document.getElementById("create-form");
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = form.querySelector("button[type=submit]");
    try {
      syncPackageTitleFromIdea(form);
      toast("Run create ho raha hai...");
      const data = await postForm("/api/runs", form, btn);
      toast("Run ban gaya — redirecting...", "ok");
      window.location.href = data.redirect;
    } catch (err) {
      toast(String(err.message || err), "bad");
    }
  });
}

function bindRunPage() {
  const root = document.getElementById("run-root");
  if (!root) return;
  const runId = root.dataset.runId;
  const form = document.getElementById("run-form");
  const statusEl = document.getElementById("status-badge");

  async function refreshStatus(status) {
    if (status && statusEl) {
      statusEl.textContent = status;
      statusEl.className = `status ${status}`;
    }
  }

  async function saveFirst(btn) {
    toast("Files save ho rahi hain...");
    const data = await postForm(`/api/runs/${runId}/save`, form, btn);
    await refreshStatus(data.status);
    return data;
  }

  document.getElementById("btn-save")?.addEventListener("click", async (e) => {
    try {
      await saveFirst(e.currentTarget);
      toast("Saved", "ok");
    } catch (err) {
      toast(String(err.message || err), "bad");
    }
  });

  document.getElementById("btn-render")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    try {
      await saveFirst(btn);
      toast("Render chal raha hai (30–90 sec)... audio + video banega");
      btn.disabled = true;
      const data = await postForm(`/api/runs/${runId}/render`, null, btn);
      await refreshStatus(data.status);
      toast(`Render done — ${data.status}`, "ok");
      window.location.reload();
    } catch (err) {
      toast(String(err.message || err), "bad");
      btn.disabled = false;
    }
  });

  document.getElementById("btn-approve")?.addEventListener("click", async (e) => {
    try {
      toast("Ship it — approving...");
      const data = await postForm(`/api/runs/${runId}/approve`, null, e.currentTarget);
      await refreshStatus(data.status);
      toast("APPROVED — ab Upload dabao", "ok");
    } catch (err) {
      toast(String(err.message || err), "bad");
    }
  });

  document.getElementById("btn-upload")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    try {
      toast("YouTube upload shuru... browser login aa sakta hai");
      const fd = new FormData();
      const privacy = document.getElementById("privacy")?.value;
      if (privacy) fd.append("privacy", privacy);
      btn.disabled = true;
      const res = await fetch(`/api/runs/${runId}/upload`, { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) throw new Error(data.error || "Upload failed");
      await refreshStatus(data.status);
      const url = data.upload?.url;
      toast(url ? `Uploaded: ${url}` : "Uploaded", "ok");
      if (url) {
        const link = document.getElementById("yt-link");
        if (link) {
          link.href = url;
          link.textContent = url;
          link.hidden = false;
        }
      }
    } catch (err) {
      toast(String(err.message || err), "bad");
    } finally {
      btn.disabled = false;
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  bindCreateForm();
  bindRunPage();
});
