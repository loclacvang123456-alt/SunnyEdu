function csrfToken(root = document) {
  return root.querySelector('[name="csrfmiddlewaretoken"]')?.value || "";
}

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "text") node.textContent = v;
    else if (k === "className") node.className = v;
    else node.setAttribute(k, v);
  }
  for (const child of children) {
    if (child != null) node.append(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

function initMobileNav() {
  const btn = document.getElementById("owner-nav-toggle");
  const nav = document.getElementById("owner-nav");
  const sidebar = document.getElementById("owner-sidebar");
  if (!btn || !nav || !sidebar) return;
  btn.addEventListener("click", () => {
    const open = !nav.classList.contains("is-open");
    nav.classList.toggle("is-open", open);
    sidebar.classList.toggle("is-open", open);
    btn.setAttribute("aria-expanded", open ? "true" : "false");
  });
}

function initImportApp() {
  const form = document.getElementById("import-preview-form");
  if (!form) return;
  const kind = form.dataset.kind;
  const resultBox = document.getElementById("import-result");
  const summaryEl = document.getElementById("import-summary");
  const tableEl = document.getElementById("import-table");
  const commitBtn = document.getElementById("import-commit-btn");
  const fileInput = document.getElementById("imp-file");
  const titleInput = document.getElementById("imp-title");
  const examSelect = document.getElementById("imp-exam");
  let lastBatch = null;

  // Auto-detect exam title from filename on selection
  if (fileInput && titleInput) {
    fileInput.addEventListener("change", () => {
      const files = Array.from(fileInput.files || []);
      if (files.length === 1) {
        const detected = files[0].name.replace(/\.[^/.]+$/, "").replace(/[_-]+/g, " ").trim();
        if (!titleInput.value.trim() || titleInput.dataset.autofilled === "1") {
          titleInput.value = detected;
          titleInput.dataset.autofilled = "1";
        }
        titleInput.disabled = false;
        if (examSelect) examSelect.disabled = false;
      } else if (files.length > 1) {
        titleInput.value = "";
        titleInput.placeholder = `Tự động nhận diện tên cho cả ${files.length} tệp đã chọn`;
        titleInput.disabled = true;
        if (examSelect) {
          examSelect.value = "";
          examSelect.disabled = true;
        }
      }
    });
    titleInput.addEventListener("input", () => {
      delete titleInput.dataset.autofilled;
    });
  }

  function renderBatchPreview(data) {
    lastBatch = { isBatch: true, batches: data.batches || [] };
    resultBox.hidden = false;
    tableEl.replaceChildren();
    summaryEl.className = "notice";
    summaryEl.textContent = `Đã kiểm tra ${data.total_files} tệp (${data.total_questions} câu hỏi). Tất cả đều hợp lệ. Hãy kiểm tra tên từng đề rồi bấm nút Tạo bên dưới.`;

    const thead = el("thead", {}, [el("tr", {}, [
      el("th", { text: "#" }),
      el("th", { text: "Tên tệp" }),
      el("th", { text: "Tiêu đề đề thi sẽ tạo" }),
      el("th", { text: "Số câu" }),
      el("th", { text: "Trạng thái" }),
    ])]);

    const tbody = el("tbody", {}, (data.batches || []).map((b, i) => {
      const inputEl = document.createElement("input");
      inputEl.type = "text";
      inputEl.className = "batch-title-input";
      inputEl.dataset.batchId = b.batch_id;
      inputEl.value = b.default_title || "";
      inputEl.style.width = "100%";
      inputEl.style.minWidth = "220px";
      inputEl.maxLength = 200;

      return el("tr", {}, [
        el("td", { text: String(i + 1) }),
        el("td", { text: b.filename }),
        el("td", {}, [inputEl]),
        el("td", { text: `${b.question_count} câu` }),
        el("td", { text: "Hợp lệ" }),
      ]);
    }));

    tableEl.append(thead, tbody);
    commitBtn.disabled = data.total_files === 0;
    commitBtn.title = `Tạo toàn bộ ${data.total_files} đề thi`;
  }

  function renderPreview(batch) {
    lastBatch = batch;
    resultBox.hidden = false;
    tableEl.replaceChildren();
    const rows = batch.rows || [];
    const hasErrors = rows.some((r) => Array.isArray(r.errors) && r.errors.length > 0);
    summaryEl.className = hasErrors ? "notice notice-error" : "notice";

    if (kind === "QUESTIONS") {
      summaryEl.textContent = `${rows.length} câu hợp lệ. Xác nhận để tạo bản nháp.`;
      const thead = el("thead", {}, [el("tr", {}, [
        el("th", { text: "Câu" }), el("th", { text: "Loại" }), el("th", { text: "Kỹ năng" }),
        el("th", { text: "Độ khó" }), el("th", { text: "Điểm" }), el("th", { text: "Tài liệu" }), el("th", { text: "Nội dung" }),
      ])]);
      const tbody = el("tbody", {}, rows.map((r) => el("tr", {}, [
        el("td", { text: String(r.position) }),
        el("td", { text: r.type }),
        el("td", { text: r.skill }),
        el("td", { text: r.difficulty }),
        el("td", { text: String(r.max_points) }),
        el("td", { text: r.passage_ref || "—" }),
        el("td", { text: String(r.prompt || "").slice(0, 120) }),
      ])));
      tableEl.append(thead, tbody);
      commitBtn.disabled = rows.length === 0 || hasErrors;
      commitBtn.title = "Tạo bản nháp";
    } else {
      const errorCount = rows.filter((r) => r.errors && r.errors.length).length;
      const existingCount = rows.filter((r) => r.exists_in_db).length;
      summaryEl.textContent = errorCount
        ? `${errorCount}/${rows.length} dòng có lỗi. Hãy sửa tệp trước khi xác nhận.`
        : `${rows.length} học sinh hợp lệ. Giữ nguyên tên và lớp trường của ${existingCount} học sinh đã có.`;
      const thead = el("thead", {}, [el("tr", {}, [
        el("th", { text: "Dòng" }), el("th", { text: "Mã HS" }), el("th", { text: "Tên hiển thị" }),
        el("th", { text: "Trường / Lớp" }), el("th", { text: "Trạng thái" }), el("th", { text: "Lỗi" }),
      ])]);
      const tbody = el("tbody", {}, rows.map((r) => el("tr", {}, [
        el("td", { text: String(r.line || "") }),
        el("td", { text: r.student_ref || "" }),
        el("td", { text: r.display_name || "" }),
        el("td", { text: [r.school_code, r.school_year, r.grade ? `K${r.grade}` : "", r.school_class_name].filter(Boolean).join(" / ") || "—" }),
        el("td", { text: r.exists_in_db ? "Đã tồn tại" : "Tạo mới" }),
        el("td", { text: (r.errors || []).join("; ") || "Hợp lệ" }),
      ])));
      tableEl.append(thead, tbody);
      commitBtn.disabled = rows.length === 0 || errorCount > 0;
    }
    if (tableEl.dataset.pageSize) applyTablePagination(tableEl, true);
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const files = Array.from(fileInput?.files || []);
    const isMulti = files.length > 1;
    const endpoint = (isMulti && kind === "QUESTIONS") ? "/api/v1/owner/imports/batch-preview" : "/api/v1/owner/imports/preview";

    const fd = new FormData(form);
    fd.set("kind", kind);
    commitBtn.disabled = true;

    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken(form) },
      body: fd,
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      resultBox.hidden = false;
      tableEl.replaceChildren();
      const pagination = tablePaginationState.get(tableEl);
      if (pagination) pagination.bar.hidden = true;
      summaryEl.className = "notice notice-error";
      summaryEl.textContent = payload.error?.message || "Không thể đọc tệp nhập.";
      return;
    }

    if (isMulti && kind === "QUESTIONS") {
      renderBatchPreview(payload.data);
    } else {
      renderPreview(payload.data);
    }
  });

  commitBtn.addEventListener("click", async () => {
    if (!lastBatch) return;
    commitBtn.disabled = true;

    // Batch commit for multiple files
    if (lastBatch.isBatch) {
      const inputs = tableEl.querySelectorAll(".batch-title-input");
      const titleMap = {};
      inputs.forEach((inp) => { titleMap[inp.dataset.batchId] = inp.value.trim(); });

      const items = lastBatch.batches.map((b) => ({
        batch_id: b.batch_id,
        expected_digest: b.expected_digest,
        title: titleMap[b.batch_id] || b.default_title,
      }));

      const res = await fetch("/api/v1/owner/imports/batch-commit", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(form) },
        body: JSON.stringify({ items }),
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        summaryEl.className = "notice notice-error";
        summaryEl.textContent = payload.error?.message || "Xác nhận hàng loạt thất bại.";
        commitBtn.disabled = false;
        return;
      }
      summaryEl.className = "notice";
      summaryEl.textContent = `Đã tạo thành công ${payload.data.created_count} đề thi mới! Đang chuyển hướng đến danh sách đề...`;
      setTimeout(() => { window.location.assign("/teacher/exams/"); }, 800);
      return;
    }

    // Single file commit
    const body = { expected_digest: lastBatch.source_digest };
    if (kind === "QUESTIONS") {
      body.title = document.getElementById("imp-title")?.value?.trim() || lastBatch.default_title || "";
      body.default_title = lastBatch.default_title || "";
      body.target_exam_id = document.getElementById("imp-exam")?.value || "";
    } else {
      body.class_id = document.getElementById("stu-import-class")?.value || "";
    }
    const res = await fetch(`/api/v1/owner/imports/${lastBatch.id}/commit`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken(form) },
      body: JSON.stringify(body),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      summaryEl.className = "notice notice-error";
      summaryEl.textContent = payload.error?.message || "Xác nhận thất bại.";
      commitBtn.disabled = false;
      return;
    }
    if (kind === "QUESTIONS") {
      window.location.assign(`/teacher/exams/${payload.data.exam_id}/versions/${payload.data.version_id}/`);
    } else {
      summaryEl.className = "notice";
      summaryEl.textContent = `Đã nhập ${payload.data.committed} dòng: tạo ${payload.data.created} học sinh, thêm ${payload.data.joined} học sinh vào lớp.`;
    }
  });
}

function initAssignmentNew() {
  const form = document.getElementById("assignment-new-form");
  const membersEl = document.getElementById("assignment-class-members");
  if (!form || !membersEl) return;
  const classMembers = JSON.parse(membersEl.textContent || "{}");
  const checks = Array.from(form.querySelectorAll('input[name="class_ids"]'));
  const preview = document.getElementById("a-recipient-preview");
  const warn = document.getElementById("a-noschool-warn");
  const latePolicy = document.getElementById("a-late-policy");
  const lateWrap = document.getElementById("a-late-until-wrap");
  const lateInput = document.getElementById("a-late-until");

  function refreshCount() {
    const seen = new Map();
    for (const cb of checks) {
      if (!cb.checked) continue;
      for (const m of classMembers[cb.value] || []) {
        seen.set(m.id, m.no_school);
      }
    }
    const noSchool = Array.from(seen.values()).filter(Boolean).length;
    preview.textContent = seen.size
      ? `Dự kiến giao cho ${seen.size} học sinh (đã gộp trùng).`
      : "Chọn lớp để xem số học sinh.";
    warn.hidden = noSchool === 0;
    if (noSchool) {
      warn.textContent = `${noSchool} học sinh chưa có lớp ở trường.`;
    }
  }

  function syncLatePolicy() {
    if (!latePolicy || !lateWrap || !lateInput) return;
    const blocked = latePolicy.value === "BLOCK";
    lateWrap.hidden = blocked;
    lateInput.disabled = blocked;
  }

  checks.forEach((cb) => cb.addEventListener("change", refreshCount));
  latePolicy?.addEventListener("change", syncLatePolicy);
  refreshCount();
  syncLatePolicy();
}

function initReportFilters() {
  const toggleBtn = document.getElementById("report-filter-toggle");
  const drawer = document.getElementById("report-filter-drawer");
  if (toggleBtn && drawer) {
    toggleBtn.addEventListener("click", () => {
      drawer.hidden = !drawer.hidden;
      const expanded = !drawer.hidden;
      toggleBtn.setAttribute("aria-expanded", String(expanded));
      toggleBtn.classList.toggle("is-active", expanded || toggleBtn.dataset.hasFilters === "1");
    });
  }

  const schoolSel = document.getElementById("rep-school");
  const gradeSel = document.getElementById("rep-grade");
  const classSel = document.getElementById("rep-school-class");
  const dataEl = document.getElementById("report-school-classes");
  if (!schoolSel || !gradeSel || !classSel || !dataEl) return;
  const allClasses = JSON.parse(dataEl.textContent || "[]");

  schoolSel.addEventListener("change", () => {
    const schoolId = schoolSel.value;
    gradeSel.disabled = !schoolId;
    if (!schoolId) gradeSel.value = "";
    const prevClass = classSel.value;
    classSel.replaceChildren(el("option", { value: "", text: "Tất cả lớp trường" }));
    for (const c of allClasses) {
      if (!schoolId || c.school_id === schoolId) {
        const opt = el("option", { value: c.id, text: c.label });
        if (c.id === prevClass) opt.selected = true;
        classSel.append(opt);
      }
    }
  });
}

function initRankingScope() {
  const scopeSel = document.getElementById("rk-scope");
  if (!scopeSel) return;
  const targets = Array.from(document.querySelectorAll(".rk-target"));
  const showPeers = document.querySelector('#ranking-new-form input[name="show_peers"]');
  function sync() {
    const val = scopeSel.value;
    for (const box of targets) {
      const scopes = (box.dataset.scope || "").split(/\s+/);
      box.hidden = !scopes.includes(val);
    }
    if (showPeers) {
      const allowed = val === "ENGLISH_CLASS";
      showPeers.disabled = !allowed;
      if (!allowed) showPeers.checked = false;
    }
  }
  scopeSel.addEventListener("change", sync);
  sync();
}

function initModals() {
  const open = (id) => {
    const modal = document.getElementById(id);
    if (!modal) return;
    modal.hidden = false;
    const firstInput = modal.querySelector("input:not([type=hidden]):not([disabled]), textarea:not([disabled]), select:not([disabled])");
    if (firstInput) setTimeout(() => firstInput.focus(), 20);
  };
  const close = (modal) => {
    if (typeof modal === "string") modal = document.getElementById(modal);
    if (modal) modal.hidden = true;
  };
  window.ownerModal = { open, close };

  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-modal-open]");
    if (opener) {
      e.preventDefault();
      if (opener.hasAttribute("data-modal-close")) {
        close(opener.closest(".modal-overlay"));
      }
      open(opener.dataset.modalOpen);
      return;
    }
    const closer = e.target.closest("[data-modal-close]");
    if (closer) {
      e.preventDefault();
      close(closer.closest(".modal-overlay"));
      return;
    }
    if (e.target.classList?.contains("modal-overlay")) {
      close(e.target);
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    document.querySelectorAll(".modal-overlay:not([hidden])").forEach((m) => close(m));
  });
}

function normalizeSearch(text) {
  return String(text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/gi, "d").toLowerCase();
}

function initTabs() {
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".context-pill[data-tab-target]");
    if (!btn) return;
    const group = btn.closest("[data-tab-group]");
    if (!group) return;
    const targetId = btn.dataset.tabTarget;
    group.querySelectorAll(".context-pill[data-tab-target]").forEach((pill) => {
      pill.classList.toggle("is-selected", pill === btn);
    });
    group.querySelectorAll("[data-tab-pane]").forEach((pane) => {
      pane.hidden = pane.id !== targetId;
    });
  });
}

const tablePaginationState = new WeakMap();

function applyTablePagination(table, resetPage = false) {
  const pageSizeAttr = Number(table?.dataset.pageSize || 0);
  if (!pageSizeAttr) return;
  const tbody = table.tBodies?.[0];
  if (!tbody) return;

  let state = tablePaginationState.get(table);
  if (!state) {
    const wrap = table.closest(".table-wrap") || table;
    const bar = el("div", { className: "table-pagination" });
    const info = el("span", { className: "table-pagination-info" });
    const controls = el("div", { className: "table-pagination-controls" });
    const sizeLabel = el("label", { className: "table-pagination-size" }, ["Số dòng/trang: "]);
    const sizeSel = el("select", { "aria-label": "Số dòng mỗi trang" });
    for (const optSize of [5, 10]) {
      if (![5, 10].includes(pageSizeAttr) && optSize > pageSizeAttr) {
        sizeSel.append(el("option", { value: String(pageSizeAttr), text: String(pageSizeAttr) }));
      }
      sizeSel.append(el("option", { value: String(optSize), text: String(optSize) }));
    }
    sizeSel.value = String(pageSizeAttr);
    sizeLabel.append(sizeSel);

    const prevBtn = el("button", { type: "button", className: "button secondary", text: "Trước" });
    const nextBtn = el("button", { type: "button", className: "button secondary", text: "Sau" });
    if (table.dataset.fixedPageSize === "1") {
      controls.append(prevBtn, nextBtn);
    } else {
      controls.append(prevBtn, nextBtn, sizeLabel);
    }
    bar.append(info, controls);
    wrap.insertAdjacentElement("afterend", bar);

    state = { page: 1, pageSize: pageSizeAttr, bar, info, prevBtn, nextBtn, sizeSel };
    tablePaginationState.set(table, state);

    prevBtn.addEventListener("click", () => {
      if (state.page > 1) {
        state.page -= 1;
        applyTablePagination(table);
      }
    });
    nextBtn.addEventListener("click", () => {
      state.page += 1;
      applyTablePagination(table);
    });
    sizeSel.addEventListener("change", () => {
      state.pageSize = Number(sizeSel.value) || pageSizeAttr;
      state.page = 1;
      applyTablePagination(table);
    });
  }

  if (resetPage) state.page = 1;
  const allRows = Array.from(tbody.rows).filter((r) => !r.classList.contains("empty-row"));
  const matchingRows = allRows.filter((r) => r.dataset.searchHidden !== "1");
  const total = matchingRows.length;
  const totalPages = Math.max(1, Math.ceil(total / state.pageSize));
  state.page = Math.min(Math.max(1, state.page), totalPages);

  const start = (state.page - 1) * state.pageSize;
  const end = start + state.pageSize;
  allRows.forEach((r) => {
    if (r.dataset.searchHidden === "1") {
      r.hidden = true;
    }
  });
  matchingRows.forEach((r, idx) => {
    r.hidden = idx < start || idx >= end;
  });

  state.bar.hidden = allRows.length === 0;
  state.info.textContent = total
    ? `Trang ${state.page} / ${totalPages} (Tổng ${total} dòng)`
    : "Không có dòng phù hợp (0 dòng)";
  state.prevBtn.disabled = state.page <= 1;
  state.nextBtn.disabled = state.page >= totalPages;
  if (table.id && table.querySelector('input[data-select-all]')) syncTableSelection(table.id);
}

function initSortableTables() {
  document.querySelectorAll("table[data-sortable-table][data-page-size]").forEach((table) => {
    applyTablePagination(table, true);
  });

  document.addEventListener("click", (e) => {
    const th = e.target.closest("th[data-sort-col]");
    if (!th) return;
    const table = th.closest("table[data-sortable-table]");
    const tbody = table?.tBodies?.[0];
    if (!tbody) return;

    const colIndex = th.cellIndex;
    const isNum = th.dataset.sortType === "num";
    const dir = th.dataset.sortDir === "asc" ? "desc" : "asc";

    th.closest("tr")?.querySelectorAll("th[data-sort-col]").forEach((h) => {
      delete h.dataset.sortDir;
      h.classList.remove("is-sorted");
      const ind = h.querySelector(".sort-ind");
      if (ind) ind.textContent = "↕";
    });

    th.dataset.sortDir = dir;
    th.classList.add("is-sorted");
    const activeInd = th.querySelector(".sort-ind");
    if (activeInd) activeInd.textContent = dir === "asc" ? "↑" : "↓";

    const rows = Array.from(tbody.rows).filter((r) => !r.classList.contains("empty-row"));
    rows.sort((a, b) => {
      const cellA = a.cells[colIndex];
      const cellB = b.cells[colIndex];
      const valA = cellA?.dataset.sortVal ?? cellA?.textContent.trim() ?? "";
      const valB = cellB?.dataset.sortVal ?? cellB?.textContent.trim() ?? "";
      const cmp = isNum
        ? (Number(valA) || 0) - (Number(valB) || 0)
        : String(valA).localeCompare(String(valB), "vi", { numeric: true, sensitivity: "base" });
      return dir === "asc" ? cmp : -cmp;
    });
    rows.forEach((row) => tbody.append(row));
    if (table.dataset.pageSize) applyTablePagination(table, true);
  });
}

function initTableSearch() {
  document.addEventListener("input", (e) => {
    const inp = e.target.closest("input[data-table-search]");
    if (!inp) return;
    const tbody = document.getElementById(inp.dataset.tableSearch);
    if (!tbody) return;
    const table = tbody.closest("table");
    const q = normalizeSearch(inp.value.trim());
    Array.from(tbody.rows).forEach((row) => {
      if (row.classList.contains("empty-row")) return;
      const isHidden = Boolean(q) && !normalizeSearch(row.textContent).includes(q);
      row.dataset.searchHidden = isHidden ? "1" : "0";
      if (!table?.dataset.pageSize) row.hidden = isHidden;
    });
    if (table?.dataset.pageSize) applyTablePagination(table, true);
  });
}

function getStudentQuestionLog() {
  const dataEl = document.getElementById("student-question-log-data");
  if (!dataEl) return [];
  try {
    return JSON.parse(dataEl.textContent || "[]");
  } catch {
    return [];
  }
}

function keywordMatchDetails(item, rawQuery) {
  const query = normalizeSearch(String(rawQuery || "").trim());
  if (!query) return [];
  const edSearch = query === "ed" || query === "-ed";
  const fields = edSearch
    ? [["Câu hỏi", item.prompt], ["Đáp án đúng", item.correct_answer]]
    : [["Câu hỏi", item.prompt], ["Đáp án đúng", item.correct_answer], ["Các lựa chọn", item.options_text], ["Giải thích", item.explanation]];
  return fields.flatMap(([label, value]) => {
    const text = String(value || "");
    if (edSearch) {
      const words = text.match(/(?:-ed\b|\b[a-z]{3,}ed\b)/gi) || [];
      const matches = words.filter((word) => !/^(?:need|seed|speed|feed|bleed|breed|greed|weed|indeed|hundred)$/i.test(word));
      return matches.length ? [`${label}: ${[...new Set(matches)].join(", ")}`] : [];
    }
    const normalized = normalizeSearch(text);
    if (/^[a-z0-9]+$/.test(query)) {
      return normalized.split(/[^a-z0-9]+/).includes(query) ? [label] : [];
    }
    return normalized.includes(query) ? [label] : [];
  });
}

function questionMatchesKeyword(item, rawQuery) {
  return keywordMatchDetails(item, rawQuery).length > 0;
}

function initKeywordPatternAnalyzer() {
  const root = document.getElementById("student-keyword-analyzer");
  const input = document.getElementById("student-keyword-input");
  const summaryEl = document.getElementById("student-keyword-summary");
  const resultsEl = document.getElementById("student-keyword-results");
  if (!root || !document.getElementById("student-question-log-data") || !input || !summaryEl || !resultsEl) return;

  const questionLog = getStudentQuestionLog();

  function render() {
    const q = input.value.trim();
    resultsEl.replaceChildren();
    if (!q) {
      summaryEl.textContent = "Nhập từ khóa để tìm trong câu hỏi, đáp án, lựa chọn và giải thích. Với -ed, chỉ tìm trong câu hỏi và đáp án đúng.";
      return;
    }
    const matches = questionLog.filter((item) => questionMatchesKeyword(item, q));
    if (!matches.length) {
      summaryEl.textContent = `Không tìm thấy câu hỏi nào chứa "${q}" trong các bài học sinh đã làm.`;
      return;
    }
    const wrong = matches.filter((m) => m.is_wrong).length;
    const correct = matches.length - wrong;
    const wrongPct = ((wrong / matches.length) * 100).toFixed(1);
    summaryEl.replaceChildren(
      el("span", { text: `Từ khóa "${q}": Đã làm ${matches.length} câu · Đúng ${correct} · Sai ${wrong} · Tỉ lệ sai ${wrongPct}% ` }),
      el("button", {
        type: "button",
        className: "button secondary",
        style: "min-height:32px;padding:4px 12px;font-size:13px;margin-left:6px",
        "data-qlog-open": "keyword",
        "data-qlog-value": q,
        "data-qlog-tab": wrong ? "wrong" : "correct",
        "data-qlog-title": `Từ khóa: "${q}"`,
        text: "Xem popup Đúng / Sai",
      }),
    );
    if (["ed", "-ed"].includes(normalizeSearch(q))) {
      summaryEl.append(el("span", { text: " Tìm từ kết thúc bằng -ed, không tự xác định thì hoặc cách phát âm." }));
    }

    const table = el("table", { className: "data-table" });
    table.append(
      el("thead", {}, [
        el("tr", {}, [
          el("th", { text: "Bài tập" }),
          el("th", { text: "Nội dung câu hỏi" }),
          el("th", { text: "HS trả lời / Đáp án đúng" }),
          el("th", { text: "Kết quả" }),
        ]),
      ]),
    );
    const tbody = el("tbody", {}, matches.slice(0, 20).map((m) => {
      const link = el("a", { href: `/teacher/assignments/${m.assignment_id}/`, text: m.assignment_title });
      const ansCell = el("td", {}, [
        el("div", {}, [el("strong", { text: "HS: " }), m.student_answer || "—"]),
        el("div", {}, [el("small", { className: "muted", text: `Đúng: ${m.correct_answer || "—"}` })]),
      ]);
      const badge = el("span", {
        className: `pill ${m.is_wrong ? "pill-danger" : "pill-success"}`,
        text: m.is_wrong ? `Sai (${m.points}/${m.max_points})` : `Đúng (${m.points}/${m.max_points})`,
      });
      return el("tr", {}, [
        el("td", {}, [link]),
        el("td", {}, [el("div", { text: m.prompt || "-" }), el("small", { className: "muted", text: `Khớp tại: ${keywordMatchDetails(m, q).join("; ")}` })]),
        ansCell,
        el("td", {}, [badge]),
      ]);
    }));
    table.append(tbody);
    const wrap = el("div", { className: "table-wrap", style: "margin-top:10px" }, [table]);
    resultsEl.append(wrap);
    if (matches.length > 20) resultsEl.append(el("p", { className: "muted", text: `Đang hiển thị 20/${matches.length} câu. Mở bảng Đúng / Sai để xem tất cả.` }));
  }

  input.addEventListener("input", render);
  root.addEventListener("click", (e) => {
    const preset = e.target.closest("[data-kw-preset]");
    if (!preset) return;
    input.value = preset.dataset.kwPreset || "";
    render();
    input.focus();
  });
  render();
}

function initQuestionLogModal() {
  const modal = document.getElementById("modal-student-qlog");
  if (!modal) return;
  const questionLog = getStudentQuestionLog();
  const titleEl = document.getElementById("qlog-modal-title");
  const subtitleEl = document.getElementById("qlog-modal-subtitle");
  const countCorrectEl = document.getElementById("qlog-count-correct");
  const countWrongEl = document.getElementById("qlog-count-wrong");
  const listCorrectEl = document.getElementById("qlog-list-correct");
  const listWrongEl = document.getElementById("qlog-list-wrong");
  const tabCorrectBtn = document.getElementById("qlog-tab-btn-correct");
  const tabWrongBtn = document.getElementById("qlog-tab-btn-wrong");
  const paneCorrect = document.getElementById("qlog-pane-correct");
  const paneWrong = document.getElementById("qlog-pane-wrong");

  function renderCard(m) {
    const head = el("div", { className: "qlog-card-head" }, [
      el("div", { className: "qlog-card-meta" }, [
        el("a", { href: `/teacher/assignments/${m.assignment_id}/` }, [el("strong", { text: m.assignment_title })]),
        m.question_type_label ? el("span", { className: "pill", text: m.question_type_label }) : null,
      ]),
      el("span", {
        className: `pill ${m.is_wrong ? "pill-danger" : "pill-success"}`,
        text: m.is_wrong ? `Sai (${m.points}/${m.max_points}đ)` : `Đúng (${m.points}/${m.max_points}đ)`,
      }),
    ]);

    const bodyNodes = [
      head,
      el("div", { className: "qlog-prompt" }, [el("strong", { text: "Câu hỏi: " }), m.prompt || m.assignment_title]),
    ];

    if (Array.isArray(m.options_list) && m.options_list.length) {
      const prefix = m.question_type === "WORD_ORDER" ? "Các từ: " : "Các lựa chọn: ";
      bodyNodes.push(
        el("div", { className: "qlog-options-hint" }, [
          el("small", { className: "muted", text: prefix + m.options_list.join(" · ") }),
        ]),
      );
    }

    const ansGrid = el("div", { className: "qlog-ans-grid" }, [
      el("div", { className: `qlog-ans-box ${m.is_wrong ? "is-wrong" : "is-student-ok"}` }, [
        el("small", { className: "qlog-ans-label", text: "Đáp án học sinh trả lời" }),
        el("div", { className: "qlog-ans-value", text: m.student_answer || "—" }),
      ]),
      el("div", { className: "qlog-ans-box is-correct" }, [
        el("small", { className: "qlog-ans-label", text: "Đáp án đúng" }),
        el("div", { className: "qlog-ans-value", text: m.correct_answer || "—" }),
      ]),
    ]);
    bodyNodes.push(ansGrid);

    if (m.explanation) {
      bodyNodes.push(el("div", { className: "qlog-explanation", text: `Giải thích: ${m.explanation}` }));
    }

    return el("article", { className: "qlog-card" }, bodyNodes);
  }

  function selectTab(tab) {
    const showWrong = tab === "wrong";
    tabCorrectBtn?.classList.toggle("is-selected", !showWrong);
    tabWrongBtn?.classList.toggle("is-selected", showWrong);
    if (paneCorrect) paneCorrect.hidden = showWrong;
    if (paneWrong) paneWrong.hidden = !showWrong;
  }

  document.addEventListener("click", (e) => {
    const trigger = e.target.closest("[data-qlog-open]");
    if (!trigger) return;
    e.preventDefault();
    const kind = trigger.dataset.qlogOpen;
    const value = trigger.dataset.qlogValue || "";
    const title = trigger.dataset.qlogTitle || value || "Chi tiết câu hỏi";
    const preferredTab = trigger.dataset.qlogTab || "";

    const matches = questionLog.filter((item) => {
      if (kind === "pattern") return Array.isArray(item.patterns) && item.patterns.includes(value);
      if (kind === "topic") return Array.isArray(item.topics) && item.topics.includes(value);
      if (kind === "qtype") return item.question_type === value;
      if (kind === "assignment") return item.assignment_id === value;
      if (kind === "keyword") return questionMatchesKeyword(item, value);
      return false;
    });

    const correctItems = matches.filter((m) => !m.is_wrong);
    const wrongItems = matches.filter((m) => m.is_wrong);

    if (titleEl) titleEl.textContent = title;
    if (subtitleEl) {
      subtitleEl.textContent = `Tổng ${matches.length} câu · Đúng ${correctItems.length} · Sai ${wrongItems.length}`;
    }
    if (countCorrectEl) countCorrectEl.textContent = String(correctItems.length);
    if (countWrongEl) countWrongEl.textContent = String(wrongItems.length);

    if (listCorrectEl) {
      listCorrectEl.replaceChildren(
        ...(correctItems.length
          ? correctItems.map(renderCard)
          : [el("p", { className: "muted", text: "Chưa có câu trả lời đúng nào trong mục này." })]),
      );
    }
    if (listWrongEl) {
      listWrongEl.replaceChildren(
        ...(wrongItems.length
          ? wrongItems.map(renderCard)
          : [el("p", { className: "muted", text: "Học sinh không có câu trả lời sai nào trong mục này." })]),
      );
    }

    const defaultTab = preferredTab || (wrongItems.length > 0 && correctItems.length === 0 ? "wrong" : "correct");
    selectTab(defaultTab);
    window.ownerModal?.open("modal-student-qlog");
  });
}

function syncTableSelection(tableId) {
  const table = document.getElementById(tableId);
  if (!table) return;
  const checked = Array.from(table.querySelectorAll("tbody input.row-check:checked:not(:disabled)"));
  const allBoxes = Array.from(table.querySelectorAll("tbody input.row-check:not(:disabled)"));
  const selectAll = table.querySelector("thead input[data-select-all]");
  if (selectAll) {
    const visible = allBoxes.filter(cb => !cb.closest("tr")?.hidden);
    const selectedVisible = visible.filter(cb => cb.checked).length;
    selectAll.checked = visible.length > 0 && selectedVisible === visible.length;
    selectAll.indeterminate = selectedVisible > 0 && selectedVisible < visible.length;
  }

  if (tableId === "ca-classes-table" || tableId === "ca-students-table") {
    const caClasses = document.querySelectorAll("#ca-classes-table tbody input.row-check:checked:not(:disabled)").length;
    const caStudents = document.querySelectorAll("#ca-students-table tbody input.row-check:checked:not(:disabled)").length;
    const total = caClasses + caStudents;
    document.querySelectorAll("[data-ca-bulk]").forEach((btn) => {
      btn.hidden = total === 0;
      const countEl = btn.querySelector(".sel-count");
      if (countEl) countEl.textContent = String(total);
    });
    return;
  }

  const bulkBtn = document.querySelector(`[data-bulk-for="${tableId}"]`);
  if (bulkBtn) {
    bulkBtn.hidden = checked.length === 0;
    const countEl = bulkBtn.querySelector(".sel-count");
    if (countEl) countEl.textContent = String(checked.length);
  }
}

const MULTISELECT_OFF_SVG = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>';
const MULTISELECT_ON_SVG = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';

function setMultiselectBtnState(btn, active) {
  if (!btn) return;
  const label = active ? "Bỏ chọn nhiều" : "Chọn nhiều";
  btn.dataset.msActive = active ? "1" : "0";
  btn.title = label;
  btn.setAttribute("aria-label", label);
  btn.innerHTML = active ? MULTISELECT_ON_SVG : MULTISELECT_OFF_SVG;
}

function resetMultiselect(tableId) {
  const table = document.getElementById(tableId);
  if (!table) return;
  const toggleBtn = document.querySelector(`[data-toggle-multiselect="${tableId}"]`);
  setMultiselectBtnState(toggleBtn, false);
  table.querySelectorAll(".multi-col").forEach((cell) => { cell.hidden = true; });
  table.querySelectorAll("input[type='checkbox']").forEach((cb) => { cb.checked = false; });
  syncTableSelection(tableId);
}

function initMultiselectTables() {
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-toggle-multiselect]");
    if (!btn) return;
    const tableId = btn.dataset.toggleMultiselect;
    const table = document.getElementById(tableId);
    if (!table) return;
    const active = btn.dataset.msActive !== "1";
    setMultiselectBtnState(btn, active);
    table.querySelectorAll(".multi-col").forEach((cell) => { cell.hidden = !active; });
    if (!active) {
      table.querySelectorAll("input[type='checkbox']").forEach((cb) => { cb.checked = false; });
    }
    syncTableSelection(tableId);
  });

  document.addEventListener("change", (e) => {
    const selectAll = e.target.closest("input[data-select-all]");
    if (selectAll) {
      const tableId = selectAll.dataset.selectAll;
      const table = document.getElementById(tableId);
      if (!table) return;
      table.querySelectorAll("tbody input.row-check").forEach((cb) => {
        if (!cb.closest("tr")?.hidden && !cb.disabled) cb.checked = selectAll.checked;
      });
      syncTableSelection(tableId);
      return;
    }
    const rowCheck = e.target.closest("tbody input.row-check");
    if (rowCheck) {
      const table = rowCheck.closest("table");
      if (table?.id) syncTableSelection(table.id);
    }
  });
}

function populateHiddenInputs(container, items) {
  container.replaceChildren(...items.map(({ name, value }) => el("input", { type: "hidden", name, value })));
}

function collectChecked(tableId) {
  return Array.from(document.querySelectorAll(`#${tableId} tbody input.row-check:checked:not(:disabled)`)).map((cb) => ({
    id: cb.value,
    label: cb.dataset.label || cb.value,
  }));
}

function renderScheduleTargets(modalId, classes, courses, students) {
  const modal = document.getElementById(modalId);
  const list = modal?.querySelector("[data-target-list]");
  const tabs = modal?.querySelectorAll("[data-target-tab]");
  if (!list || !tabs) return;
  if (students === undefined && Array.isArray(courses)) {
    students = courses;
    courses = [];
  }
  const groups = { class: classes || [], course: courses || [], student: students || [] };
  function show(type) {
    tabs.forEach((tab) => {
      const selected = tab.dataset.targetTab === type;
      tab.setAttribute("aria-selected", String(selected));
      const items = groups[tab.dataset.targetTab] || [];
      const label = tab.dataset.targetTab === "class" ? "Lớp" : tab.dataset.targetTab === "course" ? "Khóa học" : "Học sinh";
      tab.textContent = `${label} (${items.length})`;
    });
    list.replaceChildren();
    const curr = groups[type] || [];
    if (!curr.length) {
      const empty = document.createElement("p");
      empty.className = "schedule-target-empty";
      empty.textContent = type === "class" ? "Chưa chọn lớp nào." : type === "course" ? "Chưa chọn khóa học nào." : "Chưa chọn học sinh nào.";
      list.append(empty);
    }
    curr.forEach((item) => {
      const card = document.createElement("div");
      card.className = "schedule-target-card";
      card.textContent = item.label;
      list.append(card);
    });
  }
  tabs.forEach((tab) => { tab.onclick = () => show(tab.dataset.targetTab); });
  if ((classes || []).length) show("class");
  else if ((courses || []).length) show("course");
  else show("student");
}

function initAssignmentWorkflow() {
  // 1. assignment_detail.html schedule modal
  const detailHidden = document.getElementById("detail-schedule-hidden-inputs");
  const detailDue = document.getElementById("detail-sched-due");
  const detailTries = document.getElementById("detail-sched-tries");

  function openDetailSchedule(classes, courses, students, due, tries) {
    if (!detailHidden || !detailDue || !detailTries) return;
    if (students === undefined && Array.isArray(courses)) {
      students = courses;
      courses = [];
    }
    populateHiddenInputs(detailHidden, [
      ...(classes || []).map((c) => ({ name: "class_ids", value: c.id })),
      ...(courses || []).map((crs) => ({ name: "course_ids", value: crs.id })),
      ...(students || []).map((s) => ({ name: "student_ids", value: s.id })),
    ]);
    renderScheduleTargets("modal-assign-schedule", classes, courses, students);
    detailDue.value = due || detailDue.dataset.defaultDue || detailDue.value;
    detailTries.value = String(tries || 1);
    window.ownerModal.open("modal-assign-schedule");
  }

  // 2. course_detail.html 2-step assign modals
  const courseAssignSummary = document.getElementById("course-assign-summary");
  const courseSchedHidden = document.getElementById("course-sched-hidden-inputs");
  let pendingAssignments = [];

  function openCourseAssignModal(assignments) {
    if (!assignments.length || !courseAssignSummary) return;
    pendingAssignments = assignments;
    courseAssignSummary.textContent = `Bài tập (${assignments.length}): ${assignments.slice(0, 3).map((a) => a.label).join(", ")}${assignments.length > 3 ? "…" : ""}`;
    resetMultiselect("ca-classes-table");
    resetMultiselect("ca-students-table");
    const classTabBtn = document.querySelector('#modal-course-assign .context-pill[data-tab-target="ca-pane-classes"]');
    classTabBtn?.click();
    window.ownerModal.open("modal-course-assign");
  }

  function openCourseScheduleModal(classes, students) {
    if (!pendingAssignments.length || !courseSchedHidden) return;
    populateHiddenInputs(courseSchedHidden, [
      ...pendingAssignments.map((a) => ({ name: "assignment_ids", value: a.id })),
      ...classes.map((c) => ({ name: "class_ids", value: c.id })),
      ...students.map((s) => ({ name: "student_ids", value: s.id })),
    ]);
    renderScheduleTargets("modal-course-assign-schedule", classes, students);
    window.ownerModal.close("modal-course-assign");
    window.ownerModal.open("modal-course-assign-schedule");
  }

  document.getElementById("course-sched-back")?.addEventListener("click", () => {
    window.ownerModal.close("modal-course-assign-schedule");
    window.ownerModal.open("modal-course-assign");
  });

  document.addEventListener("click", (e) => {
    const detailSingle = e.target.closest("[data-detail-single]");
    if (detailSingle) {
      const item = { id: detailSingle.dataset.targetId, label: detailSingle.dataset.targetLabel };
      const kind = detailSingle.dataset.detailSingle;
      openDetailSchedule(
        kind === "class" ? [item] : [],
        kind === "course" ? [item] : [],
        kind === "student" ? [item] : [],
        detailSingle.dataset.due,
        detailSingle.dataset.tries
      );
      return;
    }

    const detailBulk = e.target.closest("[data-detail-bulk]");
    if (detailBulk) {
      const items = collectChecked(detailBulk.dataset.bulkFor);
      if (!items.length) return;
      const kind = detailBulk.dataset.detailBulk;
      openDetailSchedule(
        kind === "class" ? items : [],
        kind === "course" ? items : [],
        kind === "student" ? items : [],
        "",
        "1"
      );
      return;
    }

    const caExSingle = e.target.closest("[data-course-assign-single]");
    if (caExSingle) {
      openCourseAssignModal([{ id: caExSingle.dataset.courseAssignSingle, label: caExSingle.dataset.label || caExSingle.dataset.courseAssignSingle }]);
      return;
    }

    if (e.target.closest("[data-course-assign-bulk]")) {
      const items = collectChecked("course-ex-table");
      if (items.length) openCourseAssignModal(items);
      return;
    }

    const caSingle = e.target.closest("[data-ca-single]");
    if (caSingle) {
      const item = { id: caSingle.dataset.targetId, label: caSingle.dataset.targetLabel };
      const isClass = caSingle.dataset.caSingle === "class";
      openCourseScheduleModal(isClass ? [item] : [], isClass ? [] : [item]);
      return;
    }

    if (e.target.closest("[data-ca-bulk]")) {
      const classes = collectChecked("ca-classes-table");
      const students = collectChecked("ca-students-table");
      if (classes.length || students.length) {
        openCourseScheduleModal(classes, students);
      }
    }
  });
}

initMobileNav();
initModals();
initTabs();
initSortableTables();
initTableSearch();
initMultiselectTables();
initAssignmentWorkflow();
initImportApp();
initAssignmentNew();
initReportFilters();
initRankingScope();
initKeywordPatternAnalyzer();
initQuestionLogModal();

const recipientSearch = document.getElementById("recipient-search");
recipientSearch?.addEventListener("input", () => {
  const query = normalizeSearch(recipientSearch.value.trim());
  document.querySelectorAll("#recipient-list label").forEach((label) => { label.hidden = !normalizeSearch(label.textContent).includes(query); });
});

