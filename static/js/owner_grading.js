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

function initGradingDetail() {
  const root = document.getElementById("grading-root");
  if (!root) return;
  const attemptId = root.dataset.attemptId;
  const csrf = root.querySelector('[name="csrfmiddlewaretoken"]')?.value || "";
  const noticeEl = document.getElementById("grading-notice");
  const listEl = document.getElementById("grading-responses");
  const statusEl = document.getElementById("gr-status");
  const revEl = document.getElementById("gr-rev");
  const publishBtn = document.getElementById("publish-result-btn");
  const voidBtn = document.getElementById("void-attempt-btn");

  let currentData = null;

  function showNotice(msg, isError = false) {
    noticeEl.hidden = false;
    noticeEl.className = isError ? "notice notice-error" : "notice";
    noticeEl.textContent = msg;
  }

  function renderErrorList(container, r) {
    container.replaceChildren();
    const activeErrors = r.errors || [];
    if (!activeErrors.length) {
      container.append(el("p", { className: "muted", text: "Chưa gắn nhãn lỗi nào." }));
      return;
    }
    for (const err of activeErrors) {
      const card = el("div", { style: "padding:8px 10px;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:8px" }, [
        el("div", { style: "display:flex;justify-content:space-between;gap:8px;align-items:center" }, [
          el("strong", { text: `${err.tag_name} (${err.source})`, "data-error-help": err.tag_name }),
          err.withdrawn_at ? el("span", { className: "pill pill-danger", text: "Đã rút lại" }) : el("span", { className: "pill", text: "Hiệu lực" }),
        ]),
        err.note ? el("div", { className: "muted", text: err.note }) : null,
      ]);

      if (!err.withdrawn_at && currentData.status !== "VOID") {
        const actions = el("div", { className: "inline-form", style: "margin-top:6px" });
        if (err.source === "AI") {
          const accBtn = el("button", { type: "button", className: "button secondary", text: "Xác nhận lỗi AI" });
          const rejBtn = el("button", { type: "button", className: "button secondary danger-btn", text: "Bác bỏ lỗi AI" });
          accBtn.addEventListener("click", () => reviewAiError(err.id, true));
          rejBtn.addEventListener("click", () => reviewAiError(err.id, false));
          actions.append(accBtn, rejBtn);
        } else {
          const wBtn = el("button", { type: "button", className: "button secondary", text: "Rút lại lỗi" });
          wBtn.addEventListener("click", () => toggleTeacherError(r.response_id, { tag_id: err.tag_id, withdraw: true }));
          actions.append(wBtn);
        }
        card.append(actions);
      }
      container.append(card);
    }
  }

  async function reviewAiError(occurrenceId, accept) {
    const res = await fetch(`/api/v1/owner/errors/${occurrenceId}/teacher-review/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({ reviewed: accept, teacher_note: "" }),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      showNotice(payload.error?.message || "Không thể duyệt nhãn AI.", true);
      return;
    }
    showNotice(accept ? "Đã xác nhận nhãn lỗi AI." : "Đã bác bỏ nhãn lỗi AI.");
    await load();
  }

  async function toggleTeacherError(responseId, body) {
    const res = await fetch(`/api/v1/owner/responses/${responseId}/errors/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({ expected_revision: currentData.revision, ...body }),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      showNotice(payload.error?.message || "Thao tác nhãn lỗi thất bại.", true);
      return;
    }
    showNotice(body.withdraw ? "Đã rút lại nhãn lỗi." : "Đã lưu nhãn lỗi giáo viên.");
    await load();
  }

  function render() {
    const statusText = currentData.status === "SUBMITTED" ? "Cần chấm" : (currentData.status === "GRADED" ? "Đã chấm" : (currentData.status === "VOID" ? "Đã hủy" : currentData.status));
    statusEl.textContent = statusText;
    statusEl.className = currentData.status === "SUBMITTED" ? "pill pill-warning" : (currentData.status === "GRADED" ? "pill pill-success" : (currentData.status === "VOID" ? "pill pill-danger" : ""));
    revEl.textContent = String(currentData.revision);
    listEl.replaceChildren();
    const isVoid = currentData.status === "VOID";
    publishBtn.disabled = isVoid || !currentData.is_current;
    voidBtn.disabled = isVoid;

    for (const r of currentData.responses) {
      const leftCol = el("div", { className: "card-stack" });
      leftCol.append(el("h2", { text: `Câu ${r.position} · ${r.skill} (${r.max_points} điểm)` }));
      if (r.passage_text) {
        leftCol.append(el("div", { style: "padding:10px;background:#f8fafc;border-radius:8px;font-size:14px", text: r.passage_text }));
      }
      leftCol.append(el("p", { text: r.prompt }));

      if (r.type === "SINGLE_CHOICE" || r.type === "MULTIPLE_CHOICE" || r.type === "STRESS_CHOICE") {
        const ul = el("ul");
        for (const opt of r.options || []) {
          const picked = (r.selected_options || []).includes(opt.id);
          ul.append(el("li", { text: `${opt.key}. ${opt.content}${picked ? "  [Học sinh chọn]" : ""}` }));
        }
        leftCol.append(ul);
      } else if (r.type === "MATCH_IMAGE") {
        const wordMap = new Map((r.match_words || []).map((word) => [word.id, word.text]));
        const chosen = new Map((r.match_pairs || []).map((pair) => [pair.image_id, pair.word_id]));
        for (const [index, image] of (r.match_images || []).entries()) {
          const row = el("div", {className: "match-connection"});
          row.append(el("img", {src: image.url, width: "80", height: "64", alt: `Tranh ${index + 1}`, style: "object-fit:contain"}));
          row.append(el("span", {text: `Em nối: ${wordMap.get(chosen.get(image.id)) || "chưa nối"} · Đáp án: ${wordMap.get(image.correct_word_id) || "—"}`}));
          leftCol.append(row);
        }
      } else if (r.type === "WORD_ORDER") {
        const wordsById = new Map((r.options || []).map((opt) => [opt.id, opt.content]));
        const selected = (r.ordered_option_ids || []).map((id) => wordsById.get(id)).filter(Boolean);
        leftCol.append(el("p", { text: `Học sinh sắp xếp: ${selected.join(" ") || "(Học sinh bỏ trống)"}` }));
        leftCol.append(el("p", { text: `Thứ tự đúng: ${(r.options || []).map((opt) => opt.content).join(" ")}` }));
      } else if (r.type === "SENTENCE_TRANSFORM") {
        leftCol.append(el("p", { text: `Học sinh trả lời: ${r.text_answer || "(Học sinh bỏ trống)"}` }));
        const stdOpt = (r.options || [])[0];
        if (stdOpt) leftCol.append(el("p", { style: "color:#15803d;font-weight:600", text: `Đáp án chuẩn: ${stdOpt.content}` }));
      } else if (r.type === "TEXT") {
        const pre = el("pre", {
          style: "white-space:pre-wrap;padding:12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;margin:0",
          text: r.text_answer || "(Học sinh bỏ trống)",
        });
        const words = (r.text_answer || "").trim() ? r.text_answer.trim().split(/\s+/).length : 0;
        leftCol.append(el("div", { className: "muted", text: `Bài viết học sinh (${words} từ):` }), pre);
      } else if (r.type === "AUDIO") {
        if (r.audio_asset_id) {
          const audio = document.createElement("audio");
          audio.controls = true;
          audio.preload = "none";
          audio.src = `/api/v1/owner/assets/${r.audio_asset_id}/content`;
          leftCol.append(audio);
        } else {
          leftCol.append(el("p", { className: "empty", text: "Học sinh chưa ghi âm câu này." }));
        }
      }

      const rightCol = el("div", { className: "card-stack" });

      if (r.type === "SINGLE_CHOICE" || r.type === "MULTIPLE_CHOICE" || r.type === "WORD_ORDER" || r.type === "STRESS_CHOICE" || r.type === "MATCH_IMAGE" || r.type === "SENTENCE_TRANSFORM") {
        rightCol.append(el("div", { className: "pill pill-success", text: `Đã chấm tự động: ${r.grade ? r.grade.points : "0.00"} / ${r.max_points} điểm` }));
      } else {
        const isGraded = r.grade && r.grade.source === "TEACHER";
        if (isGraded || currentData.status === "GRADED") {
          rightCol.append(el("div", { className: "pill pill-success", text: `Đã chấm: ${r.grade ? r.grade.points : "0.00"} / ${r.max_points} điểm` }));
        } else {
          rightCol.append(el("div", { className: "pill pill-warning", text: `Cần chấm (Tự luận): ${r.grade ? r.grade.points : "0.00"} / ${r.max_points} điểm` }));
        }
        const levelsMap = {};
        const notesMap = {};
        for (const cs of r.grade?.criteria || []) {
          levelsMap[cs.id] = cs.level;
          notesMap[cs.id] = cs.note || "";
        }
        const liveScore = el("strong", { text: `Điểm dự kiến: ${r.grade ? r.grade.points : "0.00"} / ${r.max_points}` });

        function updateLiveScore() {
          let sum = 0;
          let count = 0;
          for (const crit of r.criteria || []) {
            const picked = rightCol.querySelector(`input[name="crit-${r.response_id}-${crit.id}"]:checked`);
            if (picked) {
              sum += Number(picked.value);
              count += 1;
            }
          }
          if (count === 4) {
            const pts = ((sum / 16) * Number(r.max_points)).toFixed(2);
            liveScore.textContent = `Điểm dự kiến: ${pts} / ${r.max_points}`;
          }
        }

        const gradeForm = el("form", { className: "card-stack" });
        for (const crit of r.criteria || []) {
          const critBox = el("div", { style: "padding:10px;border:1px solid #e2e8f0;border-radius:8px" }, [
            el("strong", { text: crit.label }),
          ]);
          const radios = el("div", { className: "inline-form", style: "margin:8px 0" });
          for (const lv of [0, 1, 2, 3, 4]) {
            const radio = document.createElement("input");
            radio.type = "radio";
            radio.name = `crit-${r.response_id}-${crit.id}`;
            radio.value = String(lv);
            radio.checked = levelsMap[crit.id] === lv;
            radio.disabled = isVoid;
            radio.title = crit.level_descriptions?.[String(lv)] || "";
            radio.addEventListener("change", updateLiveScore);
            radios.append(el("label", { style: "display:inline-flex;align-items:center;gap:4px;margin:0", title: crit.level_descriptions?.[String(lv)] || "" }, [
              radio,
              el("span", { text: String(lv) }),
            ]));
          }
          const noteInp = el("input", { value: notesMap[crit.id] || "", placeholder: `Ghi chú tiêu chí ${crit.label} (tùy chọn)` });
          noteInp.dataset.critNote = crit.id;
          noteInp.disabled = isVoid;
          critBox.append(radios, noteInp);
          gradeForm.append(critBox);
        }

        const feedbackInp = document.createElement("textarea");
        feedbackInp.rows = 2;
        feedbackInp.value = r.grade?.feedback || "";
        feedbackInp.placeholder = "Nhận xét câu trả lời...";
        feedbackInp.disabled = isVoid;

        const reasonInp = document.createElement("input");
        reasonInp.placeholder = currentData.latest_release ? "Lý do sửa điểm sau khi đã công bố (bắt buộc)" : "Lý do chấm lại (nếu có)";
        reasonInp.disabled = isVoid;

        const saveBtn = el("button", { type: "submit", className: "button", text: "Lưu điểm nháp" });
        saveBtn.disabled = isVoid;

        gradeForm.append(
          el("div", {}, [liveScore]),
          el("div", { className: "field-group" }, [el("label", { text: "Nhận xét giáo viên" }), feedbackInp]),
          reasonInp,
          saveBtn
        );

        gradeForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          const criterion_levels = {};
          const criterion_notes = {};
          for (const crit of r.criteria || []) {
            const checked = gradeForm.querySelector(`input[name="crit-${r.response_id}-${crit.id}"]:checked`);
            if (!checked) {
              showNotice(`Vui lòng chọn mức 0..4 cho tiêu chí "${crit.label}".`, true);
              return;
            }
            criterion_levels[crit.id] = Number(checked.value);
            criterion_notes[crit.id] = gradeForm.querySelector(`[data-crit-note="${crit.id}"]`)?.value?.trim() || "";
          }
          const res = await fetch(`/api/v1/owner/responses/${r.response_id}/grade/`, {
            method: "PUT",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
            body: JSON.stringify({
              expected_revision: currentData.revision,
              grade_revision: r.grade ? r.grade.revision : 0,
              criterion_levels,
              criterion_notes,
              feedback: feedbackInp.value.trim(),
              reason: reasonInp.value.trim(),
            }),
          });
          const payload = await res.json().catch(() => ({}));
          if (!res.ok) {
            showNotice(payload.error?.message || "Lưu điểm thất bại.", true);
            return;
          }
          showNotice(`Đã lưu nháp điểm Câu ${r.position} (${payload.data.points} điểm).`);
          await load();
        });

        rightCol.append(gradeForm);
      }

      const errorSection = el("div", { style: "border-top:1px solid #e2e8f0;padding-top:12px" });
      errorSection.append(el("h3", { text: "Nhãn lỗi", "data-error-help": "" }));
      const errListBox = el("div");
      renderErrorList(errListBox, r);
      errorSection.append(errListBox);

      if (!isVoid && (currentData.error_tags || []).length) {
        const tagSelect = document.createElement("select");
        const matchingTags = currentData.error_tags.filter((t) => t.skill === r.skill);
        const tagsToShow = matchingTags.length ? matchingTags : currentData.error_tags;
        for (const t of tagsToShow) {
          tagSelect.append(el("option", { value: t.id, text: `${t.name} (${t.skill})` }));
        }
        const selectedHelp = el("span", { "data-error-help-select": "" });
        selectedHelp.dataset.errorHelp = tagsToShow[0]?.name || "";
        tagSelect.addEventListener("change", () => {
          selectedHelp.dataset.errorHelp = tagsToShow.find(t => String(t.id) === tagSelect.value)?.name || "";
        });
        const errNote = el("input", { placeholder: "Ghi chú lỗi hoặc đoạn trích cần sửa" });
        const errBtn = el("button", { type: "button", className: "button secondary", text: "Gắn nhãn lỗi" });
        errBtn.addEventListener("click", () => toggleTeacherError(r.response_id, {
          tag_id: tagSelect.value,
          note: errNote.value.trim(),
          withdraw: false,
        }));
        errorSection.append(el("div", { className: "inline-form", style: "margin-top:8px" }, [tagSelect, selectedHelp, errNote, errBtn]));
      }

      rightCol.append(errorSection);
      listEl.append(el("section", { className: "panel grading-layout" }, [leftCol, rightCol]));
    }
  }

  async function load() {
    const res = await fetch(`/api/v1/owner/attempts/${attemptId}/grading/`);
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      showNotice(payload.error?.message || "Không tải được bài làm.", true);
      return;
    }
    currentData = payload.data;
    render();
  }

  publishBtn?.addEventListener("click", async () => {
    if (!currentData) return;
    let reason = "";
    if (currentData.latest_release) {
      const promptRes = await window.sunnyDialog.prompt("Nhập lý do công bố lại kết quả (tối thiểu 3 ký tự):");
      if (promptRes === null) return;
      reason = promptRes.trim();
    }
    const res = await fetch(`/api/v1/owner/attempts/${attemptId}/publish-result/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({ expected_revision: currentData.revision, reason }),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      showNotice(payload.error?.message || "Công bố kết quả thất bại.", true);
      return;
    }
    await window.sunnyDialog.success(`Đã công bố kết quả (bản #${payload.data.number}, tổng ${payload.data.total_points}/${payload.data.max_points}).`);
    window.location.assign(document.getElementById('grading-root').dataset.queueUrl);
  });

  voidBtn?.addEventListener("click", async () => {
    if (!currentData) return;
    const reason = await window.sunnyDialog.prompt("Nhập lý do hủy bài (VOID, bắt buộc ít nhất 3 ký tự):");
    if (!reason) return;
    const res = await fetch(`/api/v1/owner/attempts/${attemptId}/void/`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({ expected_revision: currentData.revision, reason: reason.trim() }),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      showNotice(payload.error?.message || "Hủy bài thất bại.", true);
      return;
    }
    await window.sunnyDialog.success("Đã hủy hiệu lực bài làm (VOID).");
    await load();
  });

  load();
}

initGradingDetail();
