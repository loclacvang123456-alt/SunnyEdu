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

function renderChoiceAnswers(response) {
  const options = response.options || [];
  const selected = new Set((response.selected_options || []).map(String));
  const correct = new Set((response.correct_options || []).map(String));
  const container = el("div", { className: "grading-choice-answers" });
  const list = el("ul", { className: "grading-choice-list" });
  for (const option of options) {
    const picked = selected.has(String(option.id));
    const wrong = correct.size > 0 && picked && !correct.has(String(option.id));
    const right = picked && correct.has(String(option.id));
    list.append(el("li", {
      className: `grading-choice-option${wrong ? " is-wrong" : right ? " is-correct" : ""}`,
      text: `${option.key}. ${option.content}`,
      ...(wrong || right ? {"aria-label": `${option.key}. ${option.content} — ${wrong ? "đáp án sai" : "đáp án đúng"}`} : {}),
    }));
  }
  container.append(list);
  return container;
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
        leftCol.append(renderChoiceAnswers(r));
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
      } else if (r.type === "SENTENCE_TRANSFORM" || r.type === "WORD_FORM") {
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

      if (r.type === "SINGLE_CHOICE" || r.type === "MULTIPLE_CHOICE" || r.type === "WORD_ORDER" || r.type === "STRESS_CHOICE" || r.type === "MATCH_IMAGE" || r.type === "SENTENCE_TRANSFORM" || r.type === "WORD_FORM") {
        const scoreClass = !r.grade ? "pill-warning" : Number(r.grade.points) < Number(r.max_points) ? "pill-danger" : "pill-success";
        const scoreText = r.grade ? `Đã chấm tự động: ${r.grade.points} / ${r.max_points} điểm` : "Chưa có điểm";
        rightCol.append(el("div", { className: `pill ${scoreClass}`, text: scoreText }));
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

        const saveBtn = el("button", { type: "submit", className: "button primary st-action-btn", title: "Lưu điểm nháp", "aria-label": "Lưu điểm nháp" });
        saveBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';
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
      errorSection.append(el("div", {className: "grading-error-heading"}, [el("h3", { text: "Nhãn lỗi", "data-error-help": "" })]));
      const matchingTags = (currentData.error_tags || []).filter(t => t.skill === r.skill);
      const activeErrors = (r.errors || []).filter(error => !error.withdrawn_at);
      const hasWithdrawn = (r.errors || []).some(error => Boolean(error.withdrawn_at));
      const currentError = activeErrors.find(error => error.source === "TEACHER") || activeErrors[0];
      const suggestion = !currentError && !hasWithdrawn ? r.default_error_tag_name || "" : "";
      const suggestedId = suggestion ? r.default_error_tag_id : "";
      if (matchingTags.length || currentError) {
        const tagSelect = document.createElement("select");
        tagSelect.setAttribute("aria-label", "Chọn nhãn lỗi");
        tagSelect.className = "grading-error-select";
        tagSelect.append(el("option", { value: "", text: "Không chọn nhãn lỗi" }));
        for (const t of matchingTags) {
          tagSelect.append(el("option", { value: t.id, text: t.name }));
        }
        if (currentError && !matchingTags.some(t => t.id === currentError.tag_id)) {
          tagSelect.append(el("option", { value: currentError.tag_id, text: `${currentError.tag_name} (đã lưu trữ)` }));
        }
        tagSelect.value = currentError?.tag_id || suggestedId || "";
        tagSelect.disabled = isVoid || !currentData.is_current;
        const selectedHelp = el("span", { "data-error-help": currentError?.tag_name || suggestion });
        const warning = el("span", {className: "grading-error-suggestion", title: "Nhãn gợi ý tự động. Giáo viên có thể đổi nếu chưa phù hợp.", "aria-label": "Nhãn gợi ý tự động, cần kiểm tra", text: "!"});
        warning.hidden = !(suggestedId || (currentError && currentError.source !== "TEACHER"));
        let savedValue = tagSelect.value;
        tagSelect.addEventListener("change", async () => {
          const chosen = tagSelect.value;
          const label = matchingTags.find(t => t.id === chosen)?.name || "";
          selectedHelp.dataset.errorHelp = label;
          const selects = [...listEl.querySelectorAll(".grading-error-select:not(:disabled)")];
          selects.forEach(select => { select.disabled = true; });
          try {
            const res = await fetch(`/api/v1/owner/responses/${r.response_id}/errors/`, {
              method: "POST",
              headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
              body: JSON.stringify({ expected_revision: currentData.revision, tag_id: chosen, replace_selection: true }),
            });
            const payload = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(payload.error?.message || "Không lưu được nhãn lỗi.");
            currentData.revision = payload.data.attempt_revision;
            revEl.textContent = String(currentData.revision);
            savedValue = chosen;
            warning.hidden = true;
            showNotice("Đã lưu nhãn lỗi.");
          } catch (error) {
            tagSelect.value = savedValue;
            selectedHelp.dataset.errorHelp = savedValue ? (matchingTags.find(t => t.id === savedValue)?.name || currentError?.tag_name || "") : "";
            showNotice(error.message || "Không lưu được nhãn lỗi.", true);
          } finally {
            selects.forEach(select => { select.disabled = false; });
          }
        });
        errorSection.append(el("div", { className: "grading-error-row" }, [selectedHelp, tagSelect, warning]));
      } else {
        errorSection.append(el("p", {className: "muted", text: "Chưa có nhãn lỗi cho kỹ năng này."}));
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
