// Small progressive enhancements. Everything works without JS except the live preview.
(function () {
  // Confirm destructive buttons.
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-confirm]");
    if (b && !confirm(b.dataset.confirm)) e.preventDefault();
  });

  // Select-all + counter on the image grid.
  const all = document.getElementById("select-all");
  const count = document.getElementById("sel-count");
  const boxes = () => document.querySelectorAll('#bulk input[name="ids"]');
  const update = () => {
    if (!count) return;
    const n = [...boxes()].filter((b) => b.checked).length;
    count.textContent = n + " selected";
    document.querySelectorAll("#bulk .tile").forEach((t) => t.classList.toggle("sel", t.querySelector("input").checked));
  };
  if (all) all.addEventListener("change", () => { boxes().forEach((b) => (b.checked = all.checked)); update(); });
  document.addEventListener("change", (e) => { if (e.target.name === "ids") update(); });

  // Drag & drop upload.
  const dz = document.getElementById("upload-form");
  const fi = document.getElementById("file-input");
  if (dz && fi) {
    ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("over"); }));
    ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, () => dz.classList.remove("over")));
    dz.addEventListener("drop", (e) => { e.preventDefault(); fi.files = e.dataTransfer.files; });
  }

  // Range sliders mirror their number inputs.
  document.addEventListener("input", (e) => {
    const m = e.target.dataset && e.target.dataset.mirror;
    if (m) {
      const n = e.target.form.querySelector(`input[type=number][name="${m}"]`);
      n.value = e.target.value;
      n.dispatchEvent(new Event("input", { bubbles: true }));
    } else if (e.target.type === "number" && e.target.name) {
      const r = e.target.parentElement.querySelector(`input[data-mirror="${e.target.name}"]`);
      if (r) r.value = e.target.value;
    }
  });
})();

window.PodPreview = {
  init(opts) {
    const form = document.getElementById("tplform");
    const box = document.getElementById("preview");
    const sizeEl = document.getElementById("preview-size");
    const info = document.getElementById("export-info");
    let timer = null, seq = 0, size = null;

    const exportInfo = () => {
      if (!info || !size) return;
      const dpi = +form.dpi.value || 300;
      const wmm = +form.width_mm.value || (size.w / dpi) * 25.4;
      const hmm = (wmm * size.h) / size.w;
      info.textContent = `Output: ${wmm.toFixed(0)} × ${hmm.toFixed(0)} mm, ${Math.round((wmm / 25.4) * dpi)} × ${Math.round((hmm / 25.4) * dpi)} px at ${dpi} dpi`;
    };

    const refresh = async () => {
      const my = ++seq;
      const fd = new FormData(form);
      fd.set("image_id", box.dataset.imageId);
      const r = await fetch("/api/preview", { method: "POST", body: fd });
      if (my !== seq) return;
      if (!r.ok) { box.textContent = "Preview failed."; return; }
      const svg = await r.text();
      box.innerHTML = svg;
      const s = (r.headers.get("X-Size") || "").split("x");
      size = { w: +s[0], h: +s[1] };
      if (sizeEl) sizeEl.textContent = `Composed size: ${s[0]} × ${s[1]} px (source image ${opts.w} × ${opts.h})`;
      exportInfo();
    };
    const schedule = () => { clearTimeout(timer); timer = setTimeout(refresh, 250); };
    form.addEventListener("input", schedule);
    form.addEventListener("change", schedule);

    const gs = document.getElementById("goods-select");
    if (gs) gs.addEventListener("change", () => {
      // Fit the composition inside the goods' print area.
      const o = gs.selectedOptions[0], w = +o.dataset.w, h = +o.dataset.h;
      let fit = w || "";
      if (w && h && size) fit = Math.min(w, (h * size.w) / size.h).toFixed(1);
      form.width_mm.value = fit;
      exportInfo();
    });
    refresh();
  },
};
