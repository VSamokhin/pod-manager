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

  // Tag pickers: chips + typeahead over the managed tag list. The hidden input keeps the comma-separated value.
  document.querySelectorAll("[data-tagpick]").forEach((root) => {
    const field = root.querySelector('input[name="tags"]');
    const options = [...root.querySelectorAll("datalist option")].map((o) => ({ name: o.value, color: o.dataset.color }));
    const byKey = new Map(options.map((o) => [o.name.toLowerCase(), o]));
    const picked = [];
    field.value.split(",").map((s) => s.trim().toLowerCase()).forEach((k) => {
      if (byKey.has(k) && !picked.includes(byKey.get(k))) picked.push(byKey.get(k));
    });

    field.type = "hidden";
    field.removeAttribute("list");
    const wrap = document.createElement("div");
    wrap.className = "tagwrap";
    const box = document.createElement("div");
    box.className = "tagbox";
    const typer = document.createElement("input");
    typer.className = "tagtype";
    typer.autocomplete = "off";
    typer.placeholder = options.length ? "Type to add a tag" : "No tags yet";
    typer.setAttribute("aria-label", "Add a tag");
    typer.setAttribute("role", "combobox");
    typer.setAttribute("aria-expanded", "false");
    const list = document.createElement("ul");
    list.className = "tagsugg";
    list.setAttribute("role", "listbox");
    list.hidden = true;
    wrap.append(box, list);
    field.after(wrap);
    let matches = [], active = 0;

    const sync = () => {
      field.value = picked.map((t) => t.name).join(", ");
      box.querySelectorAll(".tagchip").forEach((c) => c.remove());
      picked.forEach((t, i) => {
        const chip = document.createElement("span");
        chip.className = "tagchip";
        chip.style.setProperty("--c", t.color || "#64748b");
        chip.textContent = t.name;
        const x = document.createElement("button");
        x.type = "button";
        x.textContent = "×";
        x.setAttribute("aria-label", "Remove " + t.name);
        x.addEventListener("click", () => { picked.splice(i, 1); sync(); typer.focus(); });
        chip.append(x);
        box.insertBefore(chip, typer);
      });
    };
    const render = () => {
      const q = typer.value.trim().toLowerCase();
      matches = options.filter((o) => !picked.includes(o) && o.name.toLowerCase().includes(q));
      matches.sort((a, b) => a.name.toLowerCase().startsWith(q) === b.name.toLowerCase().startsWith(q) ? 0 : a.name.toLowerCase().startsWith(q) ? -1 : 1);
      active = Math.min(active, Math.max(matches.length - 1, 0));
      list.innerHTML = "";
      matches.slice(0, 50).forEach((o, i) => {
        const li = document.createElement("li");
        li.setAttribute("role", "option");
        li.className = i === active ? "on" : "";
        const dot = document.createElement("span");
        dot.className = "dot";
        dot.style.setProperty("--c", o.color || "#64748b");
        li.append(dot, document.createTextNode(o.name));
        li.addEventListener("mousedown", (e) => { e.preventDefault(); add(o); });
        list.append(li);
      });
      if (!matches.length) {
        const li = document.createElement("li");
        li.className = "none";
        li.textContent = q ? `“${typer.value.trim()}” is not on the tag list` : "All tags are already added";
        list.append(li);
      }
      root.classList.toggle("bad", !!q && !matches.length);
      list.hidden = false;
      typer.setAttribute("aria-expanded", "true");
    };
    const close = () => { list.hidden = true; typer.setAttribute("aria-expanded", "false"); };
    const add = (o) => { picked.push(o); typer.value = ""; active = 0; sync(); close(); }; // reopens on typing

    box.append(typer);
    box.addEventListener("click", () => { typer.focus(); render(); });
    typer.addEventListener("focus", render);
    typer.addEventListener("input", () => { active = 0; render(); });
    typer.addEventListener("blur", () => { close(); typer.value = ""; root.classList.remove("bad"); });
    typer.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (matches.length) active = (active + (e.key === "ArrowDown" ? 1 : matches.length - 1)) % matches.length;
        render();
      } else if (e.key === "Enter" || e.key === "," || (e.key === "Tab" && typer.value.trim())) {
        if (e.key === "Enter" && !typer.value.trim()) return; // an empty Enter submits the form
        e.preventDefault();
        const exact = byKey.get(typer.value.trim().toLowerCase());
        const pick = exact && !picked.includes(exact) ? exact : matches[active];
        if (pick && typer.value.trim()) add(pick);
      } else if (e.key === "Backspace" && !typer.value && picked.length) {
        picked.pop();
        sync();
        render();
      } else if (e.key === "Escape") {
        close();
      }
    });
    sync();
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
