// 站内链接：通知父窗口切换词条
document.addEventListener("click", function (e) {
  const a = e.target.closest && e.target.closest("a[data-page-id]");
  if (!a) return;
  e.preventDefault();
  const id = a.getAttribute("data-page-id");
  if (id) window.parent.postMessage({ kbNavigate: id }, "*");
});

// 标签页：记住当前分页（地址栏 #tab-2），刷新/分享后可回到同一页
(function () {
  const labels = Array.from(document.querySelectorAll("label.tabl"));
  if (!labels.length) return;
  // 支持 #tab-2 与 #tab-2.skin-3（角色页皮肤分页）
  function apply(hash) {
    const m = /^#tab-(\d+)(?:\.skin-(\d+))?/.exec(hash || "");
    if (!m) return;
    const tab = document.getElementById("m" + m[1]);
    if (tab) tab.checked = true;
    if (m[2]) {
      const sk = document.getElementById("sk" + m[2]);
      if (sk) sk.checked = true;
    }
  }
  apply(location.hash);
  labels.forEach(function (lab) {
    lab.addEventListener("click", function () {
      const id = (lab.getAttribute("for") || "").replace(/^m/, "");
      if (id) history.replaceState(null, "", "#tab-" + id);
    });
  });
  document.querySelectorAll("label.skin-tab").forEach(function (lab) {
    lab.addEventListener("click", function () {
      const n = (lab.getAttribute("for") || "").replace(/^sk/, "");
      const cur = /#tab-(\d+)/.exec(location.hash);
      history.replaceState(null, "", "#tab-" + (cur ? cur[1] : "1") + ".skin-" + n);
    });
  });
  window.addEventListener("hashchange", function () { apply(location.hash); });
})();

// 图片放大：点击弹层、左右切换、ESC 关闭
(function () {
  const box = document.getElementById("lightbox");
  if (!box) return;
  const img = box.querySelector(".lb-img");
  const cap = box.querySelector(".lb-cap");
  let items = [], cur = 0;

  // 只轮播当前可见的图（隐藏的 tab 面板里的图不参与）
  function visibleItems() {
    return Array.from(document.querySelectorAll(".shot, .emoji, .item-img, .hero-art"))
      .filter(function (el) { return el.offsetParent !== null && el.querySelector("img"); });
  }

  function show(i) {
    if (!items.length) return;
    cur = (i + items.length) % items.length;
    const el = items[cur];
    const source = el.querySelector("img");
    img.src = source.src;
    img.alt = source.alt || "";
    const fc = el.querySelector("figcaption b") || el.querySelector("figcaption");
    cap.textContent = (fc && fc.textContent.trim()) || source.alt || "";
  }

  document.addEventListener("click", function (e) {
    const hit = e.target.closest && e.target.closest(".shot, .emoji, .item-img, .hero-art");
    if (!hit) return;
    items = visibleItems();
    const i = items.indexOf(hit);
    if (i < 0) return;
    show(i);
    box.hidden = false;
  });

  box.querySelector(".lb-close").addEventListener("click", function () { box.hidden = true; });
  box.querySelector(".lb-prev").addEventListener("click", function () { show(cur - 1); });
  box.querySelector(".lb-next").addEventListener("click", function () { show(cur + 1); });
  box.addEventListener("click", function (e) { if (e.target === box) box.hidden = true; });
  document.addEventListener("keydown", function (e) {
    if (box.hidden) return;
    if (e.key === "Escape") box.hidden = true;
    if (e.key === "ArrowLeft") show(cur - 1);
    if (e.key === "ArrowRight") show(cur + 1);
  });
})();
