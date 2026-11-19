(function () {
  "use strict";

  var PER_PAGE = 25;
  var state = { items: [], q: "", rating: 0, sort: "title", instock: false, page: 1 };

  var $ = function (id) { return document.getElementById(id); };
  var gbp = new Intl.NumberFormat("ru-RU", { style: "currency", currency: "GBP" });
  var int = new Intl.NumberFormat("ru-RU");
  var dateFmt = new Intl.DateTimeFormat("ru-RU", {
    day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Moscow"
  });

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function plural(n, one, few, many) {
    var m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return one;
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
    return many;
  }

  function stars(r) {
    if (!r) return "—";
    var on = "★★★★★".slice(0, r), off = "★★★★★".slice(r);
    return '<span class="stars" aria-label="' + r + ' из 5">' + on + '<span class="off">' + off + "</span></span>";
  }

  function getJSON(url) {
    return fetch(url, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error(url + ": HTTP " + r.status);
      return r.json();
    });
  }

  /* ---------- header stats ---------- */
  function renderStats(snap) {
    var items = snap.items;
    var sum = items.reduce(function (a, b) { return a + b.price; }, 0);
    var inStock = items.filter(function (b) { return b.in_stock; }).length;
    $("s-updated").textContent = dateFmt.format(new Date(snap.scraped_at)) + " МСК";
    $("s-total").textContent = int.format(items.length);
    $("s-avg").textContent = items.length ? gbp.format(sum / items.length) : "—";
    $("s-stock").textContent = int.format(inStock);
  }

  /* ---------- changes band ---------- */
  function shortDate(iso) {
    var p = iso.split("-");
    return p[2] + "." + p[1] + "." + p[0];
  }

  function renderChanges(ch) {
    var box = $("changes");
    if (!ch) {
      box.innerHTML = '<p class="muted">Файл изменений пока не создан. Он появится после первого запуска парсера.</p>';
      return;
    }
    if (ch.first_run) {
      box.innerHTML =
        '<p class="empty-title">Сравнивать пока не с чем</p>' +
        '<p class="empty-sub">Это первый срез цен. Завтра после утреннего запуска здесь появятся подорожавшие и подешевевшие книги.</p>';
      return;
    }
    var pc = ch.price_changes || [], add = ch.added || [], rem = ch.removed || [];
    var since = "Сравнение со срезом от " + shortDate(ch.compared_with) + ".";
    if (!pc.length && !add.length && !rem.length) {
      box.innerHTML =
        '<p class="empty-title">Цены за сутки не изменились</p>' +
        '<p class="empty-sub">' + since + " Ассортимент тоже прежний: новых книг нет, ни одна не пропала.</p>";
      return;
    }
    var parts = [];
    if (pc.length) parts.push("цена изменилась у <strong>" + pc.length + "</strong> " + plural(pc.length, "книги", "книг", "книг"));
    if (add.length) parts.push("новых: <strong>" + add.length + "</strong>");
    if (rem.length) parts.push("пропало из каталога: <strong>" + rem.length + "</strong>");
    var html = '<p class="chg-summary">По сравнению со срезом от ' + shortDate(ch.compared_with) + ": " + parts.join(", ") + ".</p>";
    if (pc.length) {
      html += '<ul class="chg-list">' + pc.slice(0, 10).map(function (c) {
        var cls = c.delta < 0 ? "down" : "up";
        var sign = c.delta < 0 ? "−" : "+";
        return "<li>" +
          '<a href="' + esc(c.url) + '">' + esc(c.title) + "</a>" +
          '<span class="chg-old">' + gbp.format(c.old_price) + "</span>" +
          '<span class="chg-new">' + gbp.format(c.new_price) +
          '<span class="d ' + cls + '">' + sign + gbp.format(Math.abs(c.delta)) + "</span></span>" +
          "</li>";
      }).join("") + "</ul>";
      if (pc.length > 10) html += '<p class="muted" style="margin-top:10px">Ещё ' + (pc.length - 10) + " в файле data/changes.json.</p>";
    }
    box.innerHTML = html;
  }

  /* ---------- table ---------- */
  var sorters = {
    "title": function (a, b) { return a.title.localeCompare(b.title, "en"); },
    "price-asc": function (a, b) { return a.price - b.price; },
    "price-desc": function (a, b) { return b.price - a.price; },
    "rating-desc": function (a, b) { return (b.rating || 0) - (a.rating || 0) || a.price - b.price; }
  };

  function filtered() {
    var q = state.q.trim().toLowerCase();
    var out = state.items.filter(function (b) {
      if (q && b.title.toLowerCase().indexOf(q) === -1) return false;
      if (state.rating && (b.rating || 0) < state.rating) return false;
      if (state.instock && !b.in_stock) return false;
      return true;
    });
    return out.sort(sorters[state.sort]);
  }

  function renderTable() {
    var list = filtered();
    var pages = Math.max(1, Math.ceil(list.length / PER_PAGE));
    if (state.page > pages) state.page = pages;
    var start = (state.page - 1) * PER_PAGE;
    var slice = list.slice(start, start + PER_PAGE);

    $("found").textContent = list.length
      ? "Найдено " + int.format(list.length) + " " + plural(list.length, "книга", "книги", "книг") +
        (pages > 1 ? ", показаны " + (start + 1) + "–" + (start + slice.length) : "")
      : "";

    $("rows").innerHTML = slice.length ? slice.map(function (b) {
      return "<tr>" +
        '<td><a href="' + esc(b.url) + '">' + esc(b.title) + "</a></td>" +
        '<td class="cat">' + esc(b.category || "—") + "</td>" +
        '<td class="num">' + gbp.format(b.price) + "</td>" +
        "<td>" + stars(b.rating) + "</td>" +
        '<td class="stock' + (b.in_stock ? "" : " no") + '">' + (b.in_stock ? "В наличии" : "Нет в наличии") + "</td>" +
        "</tr>";
    }).join("") : '<tr class="empty-row"><td colspan="5">Под эти условия не подходит ни одна книга. Сократите запрос или снимите фильтры.</td></tr>';

    renderPager(pages);
  }

  function pageList(cur, total) {
    if (total <= 7) return Array.from({ length: total }, function (_, i) { return i + 1; });
    var set = [1, total, cur - 1, cur, cur + 1].filter(function (n) { return n >= 1 && n <= total; });
    set = Array.from(new Set(set)).sort(function (a, b) { return a - b; });
    var out = [];
    set.forEach(function (n, i) {
      if (i && n - set[i - 1] > 1) out.push("…");
      out.push(n);
    });
    return out;
  }

  function renderPager(pages) {
    var nav = $("pager");
    if (pages <= 1) { nav.innerHTML = ""; return; }
    var cur = state.page;
    var html = '<button type="button" data-p="' + (cur - 1) + '"' + (cur === 1 ? " disabled" : "") + ' aria-label="Предыдущая страница">‹</button>';
    pageList(cur, pages).forEach(function (n) {
      html += n === "…"
        ? '<span class="gap" aria-hidden="true">…</span>'
        : '<button type="button" data-p="' + n + '"' + (n === cur ? ' aria-current="page"' : "") + ' aria-label="Страница ' + n + '">' + n + "</button>";
    });
    html += '<button type="button" data-p="' + (cur + 1) + '"' + (cur === pages ? " disabled" : "") + ' aria-label="Следующая страница">›</button>';
    nav.innerHTML = html;
  }

  function bind() {
    $("q").addEventListener("input", function (e) { state.q = e.target.value; state.page = 1; renderTable(); });
    $("rating").addEventListener("change", function (e) { state.rating = +e.target.value; state.page = 1; renderTable(); });
    $("sort").addEventListener("change", function (e) { state.sort = e.target.value; state.page = 1; renderTable(); });
    $("instock").addEventListener("change", function (e) { state.instock = e.target.checked; state.page = 1; renderTable(); });
    $("pager").addEventListener("click", function (e) {
      var btn = e.target.closest("button[data-p]");
      if (!btn || btn.disabled) return;
      state.page = +btn.dataset.p;
      renderTable();
      var focusBtn = $("pager").querySelector('[aria-current="page"]');
      if (focusBtn) focusBtn.focus();
      $("catalog").scrollIntoView({ block: "start" });
    });
  }

  bind();

  getJSON("data/latest.json").then(function (snap) {
    state.items = snap.items || [];
    renderStats(snap);
    renderTable();
  }).catch(function (err) {
    $("rows").innerHTML = '<tr class="empty-row"><td colspan="5">Не удалось загрузить data/latest.json (' + esc(err.message) + "). Откройте страницу через веб-сервер, а не как файл.</td></tr>";
  });

  getJSON("data/changes.json").then(renderChanges).catch(function () { renderChanges(null); });
})();
