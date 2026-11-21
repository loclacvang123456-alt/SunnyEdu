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
  let lastBatch = null;

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
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    fd.set("kind", kind);
    commitBtn.disabled = true;
    const res = await fetch("/api/v1/owner/imports/preview", {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken(form) },
      body: fd,
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      resultBox.hidden = false;
      tableEl.replaceChildren();
      summaryEl.className = "notice notice-error";
      summaryEl.textContent = payload.error?.message || "Không thể đọc tệp nhập.";
      return;
    }
    renderPreview(payload.data);
  });

  commitBtn.addEventListener("click", async () => {
    if (!lastBatch) return;
    commitBtn.disabled = true;
    const body = { expected_digest: lastBatch.source_digest };
    if (kind === "QUESTIONS") {
      body.title = document.getElementById("imp-title")?.value?.trim() || "";
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

function initSortableTables() {
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
  });
}

function initTableSearch() {
  document.addEventListener("input", (e) => {
    const inp = e.target.closest("input[data-table-search]");
    if (!inp) return;
    const tbody = document.getElementById(inp.dataset.tableSearch);
    if (!tbody) return;
    const q = normalizeSearch(inp.value.trim());
    Array.from(tbody.rows).forEach((row) => {
      if (row.classList.contains("empty-row")) return;
      row.hidden = Boolean(q) && !normalizeSearch(row.textContent).includes(q);
    });
  });
}

function syncTableSelection(tableId) {
  const table = document.getElementById(tableId);
  if (!table) return;
  const checked = Array.from(table.querySelectorAll("tbody input.row-check:checked"));
  const allBoxes = Array.from(table.querySelectorAll("tbody input.row-check"));
  const selectAll = table.querySelector("thead input[data-select-all]");
  if (selectAll) {
    selectAll.checked = allBoxes.length > 0 && checked.length === allBoxes.length;
  }

  if (tableId === "ca-classes-table" || tableId === "ca-students-table") {
    const caClasses = document.querySelectorAll("#ca-classes-table tbody input.row-check:checked").length;
    const caStudents = document.querySelectorAll("#ca-students-table tbody input.row-check:checked").length;
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

function resetMultiselect(tableId) {
  const table = document.getElementById(tableId);
  if (!table) return;
  const toggleBtn = document.querySelector(`[data-toggle-multiselect="${tableId}"]`);
  if (toggleBtn) {
    toggleBtn.dataset.msActive = "0";
    toggleBtn.textContent = "☑️ Chọn nhiều";
  }
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
    btn.dataset.msActive = active ? "1" : "0";
    btn.textContent = active ? "✕ Bỏ chọn nhiều" : "☑️ Chọn nhiều";
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
        if (!cb.closest("tr")?.hidden) cb.checked = selectAll.checked;
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
  return Array.from(document.querySelectorAll(`#${tableId} tbody input.row-check:checked`)).map((cb) => ({
    id: cb.value,
    label: cb.dataset.label || cb.value,
  }));
}

function renderScheduleTargets(modalId, classes, students) {
  const modal = document.getElementById(modalId);
  const list = modal?.querySelector("[data-target-list]");
  const tabs = modal?.querySelectorAll("[data-target-tab]");
  if (!list || !tabs) return;
  const groups = { class: classes, student: students };
  function show(type) {
    tabs.forEach((tab) => {
      const selected = tab.dataset.targetTab === type;
      tab.setAttribute("aria-selected", String(selected));
      const items = groups[tab.dataset.targetTab];
      tab.textContent = `${tab.dataset.targetTab === "class" ? "Lớp" : "Học sinh"} (${items.length})`;
    });
    list.replaceChildren();
    if (!groups[type].length) {
      const empty = document.createElement("p");
      empty.className = "schedule-target-empty";
      empty.textContent = type === "class" ? "Chưa chọn lớp nào." : "Chưa chọn học sinh nào.";
      list.append(empty);
    }
    groups[type].forEach((item) => {
      const card = document.createElement("div");
      card.className = "schedule-target-card";
      card.textContent = item.label;
      list.append(card);
    });
  }
  tabs.forEach((tab) => { tab.onclick = () => show(tab.dataset.targetTab); });
  show(classes.length ? "class" : "student");
}

function initAssignmentWorkflow() {
  // 1. assignment_detail.html schedule modal
  const detailHidden = document.getElementById("detail-schedule-hidden-inputs");
  const detailDue = document.getElementById("detail-sched-due");
  const detailTries = document.getElementById("detail-sched-tries");

  function openDetailSchedule(classes, students, due, tries) {
    if (!detailHidden || !detailDue || !detailTries) return;
    populateHiddenInputs(detailHidden, [
      ...classes.map((c) => ({ name: "class_ids", value: c.id })),
      ...students.map((s) => ({ name: "student_ids", value: s.id })),
    ]);
    renderScheduleTargets("modal-assign-schedule", classes, students);
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
      const isClass = detailSingle.dataset.detailSingle === "class";
      openDetailSchedule(isClass ? [item] : [], isClass ? [] : [item], detailSingle.dataset.due, detailSingle.dataset.tries);
      return;
    }

    const detailBulk = e.target.closest("[data-detail-bulk]");
    if (detailBulk) {
      const items = collectChecked(detailBulk.dataset.bulkFor);
      if (!items.length) return;
      const isClass = detailBulk.dataset.detailBulk === "class";
      openDetailSchedule(isClass ? items : [], isClass ? [] : items, "", "1");
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

const recipientSearch = document.getElementById("recipient-search");
recipientSearch?.addEventListener("input", () => {
  const query = normalizeSearch(recipientSearch.value.trim());
  document.querySelectorAll("#recipient-list label").forEach((label) => { label.hidden = !normalizeSearch(label.textContent).includes(query); });
});

