const TYPE_LABELS = {
  SINGLE_CHOICE: "Trắc nghiệm (1 đáp án)",
  MULTIPLE_CHOICE: "Trắc nghiệm (Nhiều đáp án)",
  WORD_ORDER: "Sắp xếp từ thành câu",
  STRESS_CHOICE: "Chọn trọng âm",
  MATCH_IMAGE: "Nối tranh với từ",
  SENTENCE_TRANSFORM: "Đổi câu / Viết lại câu",
  TEXT: "Tự luận / Viết",
  AUDIO: "Nói / Thu âm",
};

const DIFF_LABELS = {
  FOUNDATION: "Cơ bản",
  STANDARD: "Trung bình",
  CHALLENGE: "Nâng cao",
};

const DEFAULT_PROMPTS = {
  WORD_ORDER: "Sắp xếp các từ sau thành câu hoàn chỉnh.",
  STRESS_CHOICE: "Chọn âm tiết mang trọng âm chính của từ.",
  MATCH_IMAGE: "Nối hình ảnh với từ vựng tương ứng.",
  SENTENCE_TRANSFORM: "Viết lại câu sau sao cho nghĩa không đổi:",
};

const CONTEXT_ELIGIBLE = new Set(["SINGLE_CHOICE", "MULTIPLE_CHOICE", "STRESS_CHOICE"]);

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

function parseWordTokens(raw) {
  const trimmed = (raw || "").trim();
  if (!trimmed) return [];
  if (trimmed.includes("\n")) {
    return trimmed.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  }
  return trimmed.split(/\s+/).filter(Boolean);
}

function parseSyllables(raw) {
  return (raw || "")
    .split(/[-/\r\n]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function initVersionEditor() {
  const bootEl = document.getElementById("editor-bootstrap");
  const root = document.getElementById("version-editor");
  if (!bootEl || !root) return;

  const state = JSON.parse(bootEl.textContent);
  const readonly = root.dataset.readonly === "1";
  const csrf = root.querySelector('[name="csrfmiddlewaretoken"]')?.value || "";

  const qListEl = document.getElementById("editor-q-list");
  const globalStatus = document.getElementById("editor-global-status");

  const qForm = document.getElementById("question-form");
  const qHeading = document.getElementById("qe-heading");
  const qStatus = document.getElementById("qe-status");
  const qType = document.getElementById("q-type");
  const qTypeGrid = document.getElementById("q-type-grid");
  const qChoiceVariants = document.getElementById("q-choice-variants");
  const qGameHint = document.getElementById("q-game-hint");
  const qSkill = document.getElementById("q-skill");
  const qContextSection = document.getElementById("q-context-section");
  const qContextPills = document.getElementById("q-context-pills");
  const qCtxNonePane = document.getElementById("q-ctx-none-pane");
  const qPassagePickerBox = document.getElementById("q-passage-picker-box");
  const qPassageSelectWrap = document.getElementById("q-passage-select-wrap");
  const qPassageLabel = document.getElementById("q-passage-label");
  const qPassage = document.getElementById("q-passage");
  const qpTextWrap = document.getElementById("qp-text-wrap");
  const qpText = document.getElementById("qp-text");
  const qpAudioWrap = document.getElementById("qp-audio-wrap");
  const qpAudioSearch = document.getElementById("qp-audio-search");
  const qpAudioAssetSelect = document.getElementById("qp-audio-asset-select");
  const qpAudioFile = document.getElementById("qp-audio-file");

  const qDiff = document.getElementById("q-diff");
  const qPoints = document.getElementById("q-points");
  const qPrompt = document.getElementById("q-prompt");
  const qChoiceBox = document.getElementById("q-choice-box");
  const qAddOptEF = document.getElementById("q-add-opt-ef");
  const qOptionsRows = document.getElementById("q-options-rows");
  const qWordOrderBox = document.getElementById("q-word-order-box");
  const qWordTokens = document.getElementById("q-word-tokens");
  const qWordPreview = document.getElementById("q-word-preview");
  const qTransformBox = document.getElementById("q-transform-box");
  const qTransformStandard = document.getElementById("q-transform-standard");
  const qStressBox = document.getElementById("q-stress-box");
  const qStressSyllables = document.getElementById("q-stress-syllables");
  const qStressIndex = document.getElementById("q-stress-index");
  const qStressPicker = document.getElementById("q-stress-picker");
  const qMatchBox = document.getElementById("q-match-box");
  const qMatchRows = document.getElementById("q-match-rows");
  const qMatchAdd = document.getElementById("q-match-add");
  const qRubricBox = document.getElementById("q-rubric-box");
  const qRubricRows = document.getElementById("q-rubric-rows");
  const qTopics = document.getElementById("q-topics");
  const qErrors = document.getElementById("q-errors");
  const qExplanation = document.getElementById("q-explanation");
  const addQBtn = document.getElementById("add-question-btn");
  const deleteQBtn = document.getElementById("delete-question-btn");

  const fieldHelp = {
    'q-prompt': 'Viết câu hỏi hoặc yêu cầu mà học sinh sẽ nhìn thấy. Ví dụ: “Chọn đáp án đúng”.',
    'q-word-tokens': 'Nhập câu đúng theo thứ tự, ví dụ “I like English”. Hệ thống sẽ xáo trộn các từ để học sinh sắp xếp lại.',
    'q-transform-standard': 'Nhập câu trả lời đúng để hệ thống dùng khi chấm bài. Ví dụ: “She has lived here for five years.”',
    'q-stress-syllables': 'Tách từ bằng dấu gạch ngang, ví dụ “teach-er”, rồi chọn âm tiết được nhấn.',
    'q-points': 'Nhập số điểm tối đa học sinh nhận được nếu trả lời đúng câu này.',
    'q-diff': 'Chọn mức dễ, trung bình hoặc nâng cao để phân loại câu hỏi.',
    'q-explanation': 'Viết lời giải để học sinh hiểu đáp án. Có thể để trống nếu không cần.',
    'q-topics': 'Ghi kiến thức câu hỏi kiểm tra, ví dụ “Quá khứ đơn”. Dùng để nhóm câu hỏi trong báo cáo. Muốn thêm nhiều nhãn, ngăn cách bằng dấu |. Có thể để trống để hệ thống tự phân loại.',
    'qp-text': 'Nhập đoạn văn để học sinh đọc trước khi trả lời. Có thể dùng chung cho nhiều câu hỏi.',
    'qp-audio-file': 'Chọn tệp âm thanh học sinh cần nghe trước khi trả lời câu hỏi.',
    'q-passage': 'Chọn đoạn đọc hoặc tệp nghe đã thêm vào đề để gắn với câu hỏi này.',
  };
  function addFieldHelp(label, description) {
    if (!label) return;
    const help = document.createElement('span');
    help.className = 'field-help';
    help.tabIndex = 0;
    help.setAttribute('aria-label', description);
    help.textContent = '?';
    const bubble = document.createElement('span');
    bubble.className = 'field-help-text';
    bubble.setAttribute('role', 'tooltip');
    bubble.textContent = description;
    help.appendChild(bubble);
    label.prepend(help);
  }
  Object.entries(fieldHelp).forEach(([id, description]) => addFieldHelp(qForm.querySelector(`label[for="${id}"]`), description));
  qForm.querySelectorAll('label[data-help]').forEach(label => addFieldHelp(label, label.dataset.help));

  // Passage manager modal elements
  const passageListBox = document.getElementById("passage-list-box");
  const passageStatus = document.getElementById("passage-status");
  const pForm = document.getElementById("passage-form");
  const pRef = document.getElementById("pas-ref");
  const pText = document.getElementById("pas-text");
  const pAudioFile = document.getElementById("pas-audio-file");
  const pUploadBtn = document.getElementById("upload-audio-btn");
  const pAudioSearch = document.getElementById("pas-audio-search");
  const pAudioSelect = document.getElementById("pas-audio-select");
  const pTranscript = document.getElementById("pas-transcript");

  if (!Array.isArray(state.audio_assets)) state.audio_assets = [];

  let selectedId = null;
  let currentContext = "NONE";
  let currentPirateGame = false;
  let showExtraOpts = false;

  function showFormError(msg) {
    qStatus.textContent = msg || "";
    qStatus.hidden = !msg;
  }

  function nextUniqueRef(prefix) {
    const used = new Set((state.passages || []).map((p) => p.ref));
    let idx = (state.passages || []).length + 1;
    while (used.has(`${prefix} ${idx}`)) idx += 1;
    return `${prefix} ${idx}`.slice(0, 40);
  }

  function renderFilteredAudioSelect(selectEl, emptyLabel, query = "") {
    if (!selectEl) return 0;
    const prev = selectEl.value;
    const term = (query || "").trim().toLowerCase();
    const allAssets = state.audio_assets || [];
    const filtered = term
      ? allAssets.filter((a) => `${a.name || ""} ${a.mime || ""}`.toLowerCase().includes(term))
      : allAssets;
    const defaultText = term
      ? `-- Tìm thấy ${filtered.length}/${allAssets.length} file nghe khớp "${query.trim()}" --`
      : (allAssets.length ? emptyLabel : "-- Chưa có tệp nghe nào trong kho --");
    selectEl.replaceChildren(el("option", { value: "", text: defaultText }));
    for (const a of filtered) {
      const opt = el("option", { value: a.id, text: `${a.name} (${a.mime})` });
      if (a.id === prev) opt.selected = true;
      selectEl.append(opt);
    }
    return filtered.length;
  }

  function syncAudioAssetDropdown(query = "") {
    renderFilteredAudioSelect(
      qpAudioAssetSelect,
      "-- Chọn file nghe từ kho (hoặc tải file mới bên dưới) --",
      query,
    );
  }

  function syncPassagesDropdown(query = "") {
    const prev = qPassage.value;
    const term = currentContext === "LISTENING" ? (query || "").trim().toLowerCase() : "";
    const eligible = (state.passages || []).filter((p) => {
      const isAudio = Boolean(p.audio_asset_id);
      if (currentContext === "LISTENING" && !isAudio) return false;
      if (currentContext === "READING" && isAudio && !p.text_body) return false;
      return true;
    });
    const matched = term
      ? eligible.filter((p) => `${p.ref || ""} ${p.audio_asset_name || ""} ${p.transcript || ""}`.toLowerCase().includes(term))
      : eligible;
    const placeholderText = term
      ? `-- Tìm thấy ${matched.length}/${eligible.length} bài nghe khớp "${query.trim()}" --`
      : "-- Nhập / tải tài liệu mới bên dưới --";
    qPassage.replaceChildren(el("option", { value: "", text: placeholderText }));
    for (const p of matched) {
      const isAudio = Boolean(p.audio_asset_id);
      const audioTag = isAudio ? (p.audio_asset_name ? ` [🎧 ${p.audio_asset_name}]` : " [Audio]") : "";
      const label = `${p.ref}${audioTag}${p.text_body ? " — " + p.text_body.slice(0, 56) : ""}`;
      const opt = el("option", { value: p.id, text: label });
      if (p.id === prev) opt.selected = true;
      qPassage.append(opt);
    }
    if (qPassageSelectWrap) {
      qPassageSelectWrap.hidden = eligible.length === 0;
    }
  }

  function renderPassageManagerList() {
    if (!passageListBox) return;
    passageListBox.replaceChildren();
    if (!state.passages || !state.passages.length) {
      passageListBox.append(el("p", { className: "hint", text: "Chưa có đoạn văn hoặc file nghe nào trong bài này." }));
      return;
    }
    for (const p of state.passages) {
      const row = el("div", { className: "panel", style: "padding:12px;display:flex;justify-content:space-between;align-items:center;gap:12px" }, [
        el("div", {}, [
          el("strong", { text: `${p.ref}${p.audio_asset_id ? ` 🎧 [${p.audio_asset_name || "Audio"}]` : " 📖 [Đoạn văn]"}` }),
          p.text_body ? el("p", { className: "hint", style: "margin:4px 0 0", text: p.text_body.slice(0, 120) }) : null,
        ]),
      ]);
      if (!readonly) {
        const del = el("button", { type: "button", className: "button primary st-action-btn", title: "Xóa tài liệu", "aria-label": "Xóa tài liệu" });
        del.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>';
        del.addEventListener("click", async () => {
          const res = await fetch(`/api/v1/owner/passages/${p.id}`, {
            method: "DELETE",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
            body: JSON.stringify({ expected_revision: state.revision, ui_direct_edit: true }),
          });
          const payload = await res.json().catch(() => ({}));
          if (!res.ok) {
            passageStatus.textContent = payload.error?.message || "Không thể xóa tài liệu đang được câu hỏi sử dụng.";
            return;
          }
          state.revision = payload.data.version_revision;
          state.passages = state.passages.filter((x) => x.id !== p.id);
          renderPassageManagerList();
          syncPassagesDropdown(qpAudioSearch?.value || "");
          passageStatus.textContent = `Đã xóa tài liệu ${p.ref}.`;
        });
        row.append(del);
      }
      passageListBox.append(row);
    }
  }

  function setContext(ctx) {
    currentContext = ctx;
    qContextPills?.querySelectorAll(".context-pill").forEach((btn) => {
      btn.classList.toggle("is-selected", btn.dataset.ctx === ctx);
    });
    if (ctx === "NONE") {
      if (qCtxNonePane) qCtxNonePane.hidden = false;
      qPassagePickerBox.hidden = true;
      qPassage.value = "";
      if (qpText) qpText.value = "";
      if (qpAudioFile) qpAudioFile.value = "";
      if (qpAudioSearch) qpAudioSearch.value = "";
      if (qpAudioAssetSelect) qpAudioAssetSelect.value = "";
    } else {
      if (qCtxNonePane) qCtxNonePane.hidden = true;
      qPassagePickerBox.hidden = false;
      if (qPassageLabel) {
        qPassageLabel.textContent = ctx === "LISTENING"
          ? "Dùng lại bài nghe đã có trong đề (hoặc chọn từ kho / tải file mới bên dưới)"
          : "Dùng lại đoạn văn đã có (hoặc nhập đoạn mới bên dưới)";
      }
      syncPassagesDropdown(ctx === "LISTENING" ? (qpAudioSearch?.value || "") : "");
      if (ctx === "LISTENING") {
        syncAudioAssetDropdown(qpAudioSearch?.value || "");
      }
      qpTextWrap.hidden = ctx === "LISTENING";
      qpAudioWrap.hidden = ctx !== "LISTENING";
    }
    syncHiddenSkill();
  }

  function syncHiddenSkill() {
    const t = qType.value;
    if (t === "TEXT") qSkill.value = "WRITING";
    else if (t === "AUDIO") qSkill.value = "SPEAKING";
    else if (t === "WORD_ORDER" || t === "SENTENCE_TRANSFORM") {
      const current = state.questions.find((x) => x.id === selectedId);
      qSkill.value = current?.skill === "READING" ? "READING" : "WRITING";
    } else if (currentContext === "LISTENING") {
      qSkill.value = "LISTENING";
    } else {
      qSkill.value = "READING";
    }
  }

  function renderChoiceRows(options = []) {
    qOptionsRows.replaceChildren();
    const isMulti = qType.value === "MULTIPLE_CHOICE";
    const keys = showExtraOpts ? ["A", "B", "C", "D", "E", "F"] : ["A", "B", "C", "D"];
    if (qAddOptEF) qAddOptEF.hidden = showExtraOpts || readonly;
    keys.forEach((key, idx) => {
      const existing = options.find((o) => o.key === key) || options[idx] || { content: "", is_correct: false };
      const checkInput = document.createElement("input");
      checkInput.type = isMulti ? "checkbox" : "radio";
      checkInput.name = "correct_opt_pick";
      checkInput.value = key;
      checkInput.checked = Boolean(existing.is_correct);
      checkInput.disabled = readonly;

      const textInput = document.createElement("input");
      textInput.type = "text";
      textInput.dataset.optKey = key;
      textInput.value = existing.content || "";
      textInput.placeholder = `Đáp án ${key}${idx < 2 ? " (bắt buộc)" : ""}`;
      textInput.disabled = readonly;
      textInput.style.flex = "1";

      const row = el("div", { className: "inline-form", style: "width:100%" }, [
        el("label", { style: "display:flex;align-items:center;gap:6px;min-width:54px;margin:0;cursor:pointer" }, [checkInput, el("strong", { text: key })]),
        textInput,
      ]);
      qOptionsRows.append(row);
    });
  }

  function renderWordPreview() {
    const tokens = parseWordTokens(qWordTokens.value);
    qWordPreview.replaceChildren();
    if (!tokens.length) {
      qWordPreview.hidden = true;
      return;
    }
    qWordPreview.hidden = false;
    tokens.forEach((tok) => qWordPreview.append(el("span", { className: "word-chip-preview", text: tok })));
  }

  function renderStressPicker() {
    const syllables = parseSyllables(qStressSyllables.value);
    qStressPicker.replaceChildren();
    if (!syllables.length) {
      qStressPicker.append(el("span", { className: "hint", style: "margin:0", text: "Nhập các âm tiết cách nhau bởi dấu '-' ở trên (VD: in-for-ma-tion)" }));
      qStressIndex.value = "";
      return;
    }
    let idxNum = Number(qStressIndex.value);
    if (!Number.isInteger(idxNum) || idxNum < 1 || idxNum > syllables.length) {
      idxNum = 1;
      qStressIndex.value = "1";
    }
    syllables.forEach((syl, i) => {
      const pos = i + 1;
      const btn = el("button", {
        type: "button",
        className: `syllable-chip${pos === idxNum ? " is-selected" : ""}`,
        text: syl,
      });
      btn.disabled = readonly;
      btn.addEventListener("click", () => {
        qStressIndex.value = String(pos);
        renderStressPicker();
      });
      qStressPicker.append(btn);
    });
  }

  function renderRubricRows(criteria = []) {
    qRubricRows.replaceChildren();
    const defaults = state.default_rubrics?.[qType.value] || state.default_rubrics?.TEXT || [];
    for (let idx = 0; idx < 4; idx += 1) {
      const def = defaults[idx] || [`c${idx + 1}`, `Tiêu chí ${idx + 1}`];
      const existing = criteria[idx] || {
        key: def[0],
        label: def[1],
        level_descriptions: { ...state.default_levels },
      };
      const card = el("div", { className: "panel", style: "padding:12px" });
      card.dataset.critKey = existing.key || def[0];
      const labelInput = el("input", { value: existing.label || def[1], required: "required" });
      labelInput.dataset.critField = "label";
      labelInput.disabled = readonly;
      card.append(el("div", { className: "field-group" }, [
        el("label", { text: `Tiêu chí ${idx + 1}` }),
        labelInput,
      ]));
      const levels = el("div", { className: "owner-grid-2" });
      for (const lv of ["0", "1", "2", "3", "4"]) {
        const inp = el("input", { value: existing.level_descriptions?.[lv] || state.default_levels?.[lv] || `Mức ${lv}` });
        inp.dataset.critLevel = lv;
        inp.disabled = readonly;
        levels.append(el("div", {}, [el("label", { text: `Mức ${lv}` }), inp]));
      }
      card.append(levels);
      qRubricRows.append(card);
    }
  }

  function addMatchRow(pair = {}) {
    if (qMatchRows.children.length >= 6) return;
    const row = el("div", { className: "panel card-stack", style: "padding:12px;gap:8px" });
    row.dataset.assetId = pair.image_asset_id || "";
    const word = el("input", { type: "text", maxlength: "200", placeholder: "Nhập từ tiếng Anh tương ứng...", value: pair.word || "" });
    word.classList.add("match-word-input");
    word.disabled = readonly;
    const image = el("img", { alt: "Ảnh cặp từ", width: "96", height: "96" });
    image.style.objectFit = "contain";
    image.hidden = !row.dataset.assetId;
    if (row.dataset.assetId) image.src = `/api/v1/owner/image-assets/${encodeURIComponent(row.dataset.assetId)}/content/`;
    const file = el("input", { type: "file", accept: "image/png,image/jpeg", "aria-label": "Chọn ảnh" });
    file.disabled = readonly;
    const feedback = el("p", { className: "hint", style: "margin:0", text: row.dataset.assetId ? "Đã có ảnh." : "Chọn ảnh PNG/JPG." });
    file.addEventListener("change", async () => {
      const selected = file.files?.[0];
      if (!selected) return;
      row.dataset.uploading = "1";
      feedback.textContent = "Đang tải ảnh…";
      const fd = new FormData();
      fd.append("file", selected);
      try {
        const res = await fetch("/api/v1/owner/image-assets/", { method: "POST", headers: { "X-CSRFToken": csrf }, body: fd });
        const payload = await res.json();
        if (!res.ok || !payload.data?.id) throw new Error(payload.error?.message || "Không tải được ảnh.");
        row.dataset.assetId = payload.data.id;
        image.src = `/api/v1/owner/image-assets/${encodeURIComponent(payload.data.id)}/content/`;
        image.hidden = false;
        feedback.textContent = "Đã tải ảnh.";
      } catch (error) {
        feedback.textContent = error.message || "Không tải được ảnh.";
      } finally {
        row.dataset.uploading = "0";
      }
    });
    const remove = el("button", { type: "button", className: "button secondary", style: "min-height:36px;padding:4px 12px;font-size:13px", text: "Xóa cặp" });
    remove.disabled = readonly;
    remove.addEventListener("click", () => row.remove());
    row.append(el("div", { className: "owner-grid-2", style: "align-items:center" }, [
      el("div", {}, [image, file, feedback]),
      el("div", { className: "card-stack", style: "gap:8px" }, [el("label", { text: "Từ tiếng Anh" }), word, remove]),
    ]));
    qMatchRows.append(row);
  }

  function applyQuestionTypeUI(existingOptions = [], existingCriteria = [], existingPairs = []) {
    const t = qType.value;
    const isChoice = t === "SINGLE_CHOICE" || t === "MULTIPLE_CHOICE";
    const isWordOrder = t === "WORD_ORDER";
    const isStress = t === "STRESS_CHOICE";
    const isMatch = t === "MATCH_IMAGE";
    const isTransform = t === "SENTENCE_TRANSFORM";
    qTypeGrid?.querySelectorAll(".type-chip").forEach((chip) => {
      chip.classList.toggle("is-selected", chip.dataset.qgroup === "choice" ? isChoice : chip.dataset.qtype === t);
    });
    if (qChoiceVariants) {
      qChoiceVariants.hidden = !isChoice;
      qChoiceVariants.querySelectorAll(".choice-variant").forEach((button) => {
        button.classList.toggle("is-selected", button.dataset.qtype === t && (button.dataset.game === "true") === (currentPirateGame === true));
      });
    }
    if (qGameHint) {
      qGameHint.hidden = !isChoice || currentPirateGame === false;
      qGameHint.textContent = currentPirateGame === null
        ? "Câu cũ dùng thiết lập bắn thuyền của bài giao. Chọn lại kiểu câu để thay đổi."
        : "Chọn chế độ luyện tập và bật Bắn thuyền khi giao bài để học sinh chơi; bài kiểm tra hiển thị trắc nghiệm thông thường.";
    }
    const editingMatchWithContext = isMatch && state.questions.some(q => q.id === selectedId && q.type === "MATCH_IMAGE" && q.passage_id);
    const allowsContext = CONTEXT_ELIGIBLE.has(t) && currentPirateGame !== true;
    qContextSection.hidden = !allowsContext;
    if (!allowsContext && !editingMatchWithContext) setContext("NONE");
    else syncHiddenSkill();

    qChoiceBox.hidden = !isChoice;
    qWordOrderBox.hidden = !isWordOrder;
    if (qTransformBox) qTransformBox.hidden = !isTransform;
    qStressBox.hidden = !isStress;
    qMatchBox.hidden = !isMatch;
    qRubricBox.hidden = isChoice || isWordOrder || isStress || isMatch || isTransform;

    if (isChoice) {
      renderChoiceRows(existingOptions);
    } else if (isTransform) {
      if (qTransformStandard) {
        qTransformStandard.value = existingOptions[0]?.content || "";
      }
    } else if (isWordOrder) {
      const hasSpaces = existingOptions.some((o) => o.content.includes(" "));
      qWordTokens.value = existingOptions.map((o) => o.content).join(hasSpaces ? "\n" : " ");
      renderWordPreview();
    } else if (isStress) {
      qStressSyllables.value = existingOptions.map((o) => o.content).join("-");
      const correctIndex = existingOptions.findIndex((o) => o.is_correct);
      qStressIndex.value = correctIndex >= 0 ? String(correctIndex + 1) : "1";
      renderStressPicker();
    } else if (isMatch) {
      qMatchRows.replaceChildren();
      if (existingPairs.length) existingPairs.forEach(addMatchRow);
      else {
        addMatchRow();
        addMatchRow();
      }
      if (qMatchAdd) qMatchAdd.disabled = readonly;
    } else {
      renderRubricRows(existingCriteria);
    }
  }

  function openQuestionModal(q) {
    selectedId = q ? q.id : null;
    showFormError("");
    if (qpText) qpText.value = "";
    if (qpAudioFile) qpAudioFile.value = "";
    if (qpAudioSearch) qpAudioSearch.value = "";
    if (qpAudioAssetSelect) qpAudioAssetSelect.value = "";

    if (!q) {
      qHeading.textContent = "Thêm câu hỏi mới";
      qType.value = "SINGLE_CHOICE";
      currentPirateGame = false;
      qDiff.value = "STANDARD";
      qPoints.value = "1.00";
      qPrompt.value = "";
      qTopics.value = "";
      qErrors.value = "";
      qExplanation.value = "";
      showExtraOpts = false;
      setContext("NONE");
      if (deleteQBtn) deleteQBtn.hidden = true;
      applyQuestionTypeUI([], [], []);
    } else {
      qHeading.textContent = `Sửa câu hỏi số ${q.position}`;
      qType.value = q.type;
      currentPirateGame = q.pirate_game ?? null;
      qDiff.value = q.difficulty;
      qPoints.value = q.max_points;
      qPrompt.value = q.prompt || "";
      qTopics.value = (q.topic_tags || []).join(" | ");
      qErrors.value = (q.error_tags || []).join(" | ");
      qExplanation.value = q.explanation || "";
      showExtraOpts = (q.options || []).length > 4;

      if (q.skill === "LISTENING") setContext("LISTENING");
      else if (q.passage_id) setContext("READING");
      else setContext("NONE");

      qPassage.value = q.passage_id || "";
      if (q.passage_id && currentContext === "READING" && qpText) {
        const pObj = (state.passages || []).find((p) => p.id === q.passage_id);
        qpText.value = pObj?.text_body || "";
      }
      if (deleteQBtn) deleteQBtn.hidden = readonly;
      applyQuestionTypeUI(q.options || [], q.criteria || [], q.match_pairs || []);
    }

    if (window.ownerModal?.open) {
      window.ownerModal.open("modal-question-editor");
    } else {
      const m = document.getElementById("modal-question-editor");
      if (m) m.hidden = false;
    }
  }

  async function deleteQuestionById(q) {
    if (readonly || !q) return;
    if (!await window.sunnyDialog.confirm(`Xóa câu hỏi số ${q.position}?`)) return;
    const res = await fetch(`/api/v1/owner/questions/${q.id}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({ expected_revision: state.revision, ui_direct_edit: true }),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (globalStatus) {
        globalStatus.className = "notice notice-error";
        globalStatus.textContent = payload.error?.message || "Không thể xóa câu hỏi.";
        globalStatus.hidden = false;
      }
      return;
    }
    const targetUrl = new URL(window.location.href);
    targetUrl.searchParams.delete("q");
    targetUrl.searchParams.delete("new_q");
    window.location.assign(targetUrl.toString());
  }

  function renderQuestionCards() {
    qListEl.replaceChildren();
    if (!state.questions.length) {
      const emptyBox = el("div", { className: "empty-state" }, [
        el("h3", { text: "Bài tập này chưa có câu hỏi nào" }),
        el("p", { text: "Bấm nút bên dưới để bắt đầu thêm câu hỏi đầu tiên." }),
      ]);
      if (!readonly) {
        const btn = el("button", { type: "button", className: "button primary", style: "margin-top:16px", text: "+ Thêm câu hỏi đầu tiên" });
        btn.addEventListener("click", () => openQuestionModal(null));
        emptyBox.append(btn);
      }
      qListEl.append(emptyBox);
      return;
    }

    const passageById = new Map((state.passages || []).map((p) => [p.id, p]));

    for (const q of state.questions) {
      const card = el("article", { className: "q-card" });

      // Header
      const meta = el("div", { className: "q-card-meta" }, [
        el("strong", { text: `Câu ${q.position}` }),
        el("span", { className: "pill", text: TYPE_LABELS[q.type] || q.type }),
        el("span", { className: "pill", style: "background:#f1f5f9;color:#475569", text: DIFF_LABELS[q.difficulty] || q.difficulty }),
        el("span", { className: "pill pill-success", text: `${q.max_points}đ` }),
      ]);
      const pObj = q.passage_id ? passageById.get(q.passage_id) : null;
      if (pObj) {
        meta.append(el("span", { className: "pill pill-warning", text: pObj.audio_asset_id ? `🎧 ${pObj.ref}` : `📖 ${pObj.ref}` }));
      }

      const actions = el("div", { className: "inline-form" });
      if (!readonly) {
        const editBtn = el("button", { type: "button", className: "button primary st-action-btn", title: "Sửa câu hỏi", "aria-label": "Sửa câu hỏi" });
        editBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>';
        editBtn.addEventListener("click", () => openQuestionModal(q));
        const delBtn = el("button", { type: "button", className: "button primary st-action-btn", title: "Xóa câu hỏi", "aria-label": "Xóa câu hỏi" });
        delBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>';
        delBtn.addEventListener("click", () => deleteQuestionById(q));
        actions.append(editBtn, delBtn);
      }

      card.append(el("div", { className: "q-card-head" }, [meta, actions]));

      if (pObj?.text_body) {
        card.append(el("div", { className: "q-card-passage", text: pObj.text_body.slice(0, 240) + (pObj.text_body.length > 240 ? "…" : "") }));
      }

      card.append(el("div", { className: "q-card-prompt", text: q.prompt }));

      // Body preview per question type
      if (q.type === "SINGLE_CHOICE" || q.type === "MULTIPLE_CHOICE") {
        const optsGrid = el("div", { className: "q-card-options" });
        for (const o of q.options || []) {
          optsGrid.append(el("div", {
            className: `q-opt-pill${o.is_correct ? " q-opt-correct" : ""}`,
            text: `${o.is_correct ? "✓ " : ""}${o.key}. ${o.content}`,
          }));
        }
        card.append(optsGrid);
      } else if (q.type === "SENTENCE_TRANSFORM") {
        const wrap = el("div", { className: "hint", style: "margin-top:6px;background:#f8fafc;padding:8px 12px;border-radius:8px;border:1px solid #e2e8f0;" });
        wrap.append(el("strong", { text: "Đáp án chuẩn: " }), document.createTextNode(q.options?.[0]?.content || ""));
        card.append(wrap);
      } else if (q.type === "WORD_ORDER") {
        const wrap = el("div", { className: "word-preview-list" });
        for (const o of q.options || []) {
          wrap.append(el("span", { className: "word-chip-preview", text: o.content }));
        }
        card.append(wrap);
      } else if (q.type === "STRESS_CHOICE") {
        const wrap = el("div", { className: "syllable-picker" });
        for (const o of q.options || []) {
          wrap.append(el("span", {
            className: `syllable-chip${o.is_correct ? " is-selected" : ""}`,
            style: "padding:4px 12px;font-size:14px",
            text: o.content,
          }));
        }
        card.append(wrap);
      } else if (q.type === "MATCH_IMAGE") {
        const wrap = el("div", { className: "word-preview-list" });
        (q.match_pairs || []).forEach((pair, idx) => {
          wrap.append(el("span", { className: "word-chip-preview", text: `🖼️ Tranh ${idx + 1} ↔ ${pair.word}` }));
        });
        card.append(wrap);
      } else {
        card.append(el("p", { className: "hint", style: "margin:0", text: q.type === "AUDIO" ? "🎙️ Học sinh trả lời bằng cách ghi âm." : "✍️ Học sinh nhập bài viết tự luận." }));
      }

      if (q.explanation) {
        card.append(el("div", { className: "q-card-explanation", text: `💡 Giải thích: ${q.explanation}` }));
      }
      if (Array.isArray(q.topic_tags) && q.topic_tags.length) {
        const tagRow = el("div", { style: "display:flex;flex-wrap:wrap;gap:6px;margin-top:8px" });
        for (const tname of q.topic_tags) {
          tagRow.append(el("span", { className: "pill", style: "background:#eff6ff;color:#1d4ed8;font-size:12px", text: `🏷️ ${tname}` }));
        }
        card.append(tagRow);
      }

      qListEl.append(card);
    }
  }

  // Event bindings
  qTypeGrid?.addEventListener("click", async (e) => {
    const chip = e.target.closest(".type-chip, .choice-variant");
    if (!chip || readonly) return;
    const prevType = qType.value;
    const nextType = chip.dataset.qgroup === "choice"
      ? (["SINGLE_CHOICE", "MULTIPLE_CHOICE"].includes(prevType) ? prevType : "SINGLE_CHOICE")
      : chip.dataset.qtype;
    const nextGame = chip.classList.contains("choice-variant") ? chip.dataset.game === "true"
      : chip.dataset.qgroup === "choice" && ["SINGLE_CHOICE", "MULTIPLE_CHOICE"].includes(prevType) ? currentPirateGame : false;
    if (prevType === nextType && currentPirateGame === nextGame) return;
    if (currentContext !== "NONE" && (!CONTEXT_ELIGIBLE.has(nextType) || nextGame === true) &&
        !await window.sunnyDialog.confirm("Đổi kiểu câu sẽ bỏ tài liệu đọc hoặc nghe đang chọn. Tiếp tục?")) return;
    const existingOptions = ["SINGLE_CHOICE", "MULTIPLE_CHOICE"].includes(prevType)
      ? Array.from(qOptionsRows.querySelectorAll("[data-opt-key]")).map(input => ({key: input.dataset.optKey, content: input.value, is_correct: Boolean(qOptionsRows.querySelector(`input[name="correct_opt_pick"][value="${input.dataset.optKey}"]`)?.checked)}))
      : [];
    qType.value = nextType;
    currentPirateGame = nextGame;
    const curPrompt = qPrompt.value.trim();
    const isDefaultOrEmpty = !curPrompt || Object.values(DEFAULT_PROMPTS).includes(curPrompt);
    if (isDefaultOrEmpty && DEFAULT_PROMPTS[nextType]) qPrompt.value = DEFAULT_PROMPTS[nextType];
    else if (isDefaultOrEmpty && !DEFAULT_PROMPTS[nextType] && Object.values(DEFAULT_PROMPTS).includes(curPrompt)) qPrompt.value = "";
    const current = state.questions.find((x) => x.id === selectedId);
    applyQuestionTypeUI(existingOptions.length && ["SINGLE_CHOICE", "MULTIPLE_CHOICE"].includes(nextType) ? existingOptions : current?.options || [], current?.criteria || [], current?.match_pairs || []);
  });

  qContextPills?.addEventListener("click", (e) => {
    const pill = e.target.closest(".context-pill");
    if (!pill || readonly) return;
    setContext(pill.dataset.ctx);
  });

  qAddOptEF?.addEventListener("click", () => {
    const saved = {};
    const checked = new Set(Array.from(qOptionsRows.querySelectorAll('input[name="correct_opt_pick"]:checked')).map((i) => i.value));
    qOptionsRows.querySelectorAll("[data-opt-key]").forEach((inp) => {
      saved[inp.dataset.optKey] = { key: inp.dataset.optKey, content: inp.value, is_correct: checked.has(inp.dataset.optKey) };
    });
    showExtraOpts = true;
    renderChoiceRows(["A", "B", "C", "D", "E", "F"].map((k) => saved[k] || { key: k, content: "", is_correct: false }));
  });

  qWordTokens?.addEventListener("input", renderWordPreview);
  qStressSyllables?.addEventListener("input", renderStressPicker);
  qMatchAdd?.addEventListener("click", () => addMatchRow());
  addQBtn?.addEventListener("click", () => openQuestionModal(null));
  deleteQBtn?.addEventListener("click", () => {
    const current = state.questions.find((x) => x.id === selectedId);
    if (current) deleteQuestionById(current);
  });

  qPassage?.addEventListener("change", () => {
    if (currentContext === "LISTENING") {
      if (qPassage.value) {
        if (qpAudioAssetSelect) qpAudioAssetSelect.value = "";
        if (qpAudioFile) qpAudioFile.value = "";
      }
      return;
    }
    if (currentContext !== "READING" || !qpText) return;
    const picked = (state.passages || []).find((p) => p.id === qPassage.value);
    qpText.value = picked ? (picked.text_body || "") : "";
  });

  qpAudioSearch?.addEventListener("input", () => {
    const term = qpAudioSearch.value;
    syncPassagesDropdown(term);
    syncAudioAssetDropdown(term);
  });

  qpAudioAssetSelect?.addEventListener("change", () => {
    if (qpAudioAssetSelect.value) {
      if (qPassage) qPassage.value = "";
      if (qpAudioFile) qpAudioFile.value = "";
    }
  });

  qpAudioFile?.addEventListener("change", () => {
    if (qpAudioFile.files?.[0]) {
      if (qPassage) qPassage.value = "";
      if (qpAudioAssetSelect) qpAudioAssetSelect.value = "";
    }
  });

  pAudioSearch?.addEventListener("input", () => {
    renderFilteredAudioSelect(pAudioSelect, "Không gắn audio", pAudioSearch.value);
  });

  async function createPassage(ref, textBody, audioAssetId, audioAssetName = "") {
    const res = await fetch(`/api/v1/owner/versions/${state.version_id}/passages`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({
        expected_revision: state.revision,
        ui_direct_edit: true,
        ref,
        text_body: textBody,
        audio_asset_id: audioAssetId || null,
        transcript: "",
      }),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(payload.error?.message || "Không thể lưu tài liệu.");
    }
    state.revision = payload.data.version_revision;
    state.passages.push({
      id: payload.data.id,
      ref: payload.data.ref,
      text_body: textBody,
      audio_asset_id: audioAssetId || "",
      audio_asset_name: audioAssetName || "",
      transcript: "",
    });
    return payload.data.id;
  }

  async function resolveOrCreateContextPassage() {
    if (currentContext === "NONE") return null;
    if (currentContext === "READING") {
      const textBody = (qpText?.value || "").trim();
      const selected = (state.passages || []).find((p) => p.id === qPassage.value);
      if (selected && (selected.text_body || "").trim() === textBody) {
        return selected.id;
      }
      const existing = (state.passages || []).find((p) => !p.audio_asset_id && (p.text_body || "").trim() === textBody);
      if (existing) return existing.id;
      return await createPassage(nextUniqueRef("Đoạn"), textBody, null, "");
    }

    // LISTENING
    const file = qpAudioFile?.files?.[0];
    if (file) {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("purpose", "PROMPT_AUDIO");
      const upRes = await fetch("/api/v1/owner/assets", { method: "POST", headers: { "X-CSRFToken": csrf }, body: fd });
      const upPayload = await upRes.json().catch(() => ({}));
      if (!upRes.ok) {
        throw new Error(upPayload.error?.message || "Tải tệp nghe thất bại.");
      }
      const uploaded = upPayload.data;
      state.audio_assets.unshift({ id: uploaded.id, name: uploaded.original_name || file.name, mime: uploaded.detected_mime || file.type });
      return await createPassage(nextUniqueRef("Audio"), "", uploaded.id, uploaded.original_name || file.name);
    }

    if (qPassage.value) {
      return qPassage.value;
    }

    const pickedAssetId = qpAudioAssetSelect?.value;
    if (pickedAssetId) {
      const existingPassage = (state.passages || []).find((p) => p.audio_asset_id === pickedAssetId && !p.text_body);
      if (existingPassage) return existingPassage.id;
      const assetObj = (state.audio_assets || []).find((a) => a.id === pickedAssetId);
      return await createPassage(nextUniqueRef("Audio"), "", pickedAssetId, assetObj?.name || "");
    }

    return null;
  }

  // Passage manager modal handlers
  pUploadBtn?.addEventListener("click", async () => {
    const file = pAudioFile?.files?.[0];
    if (!file) {
      passageStatus.textContent = "Hãy chọn tệp nghe trước.";
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    fd.append("purpose", "PROMPT_AUDIO");
    pUploadBtn.disabled = true;
    const res = await fetch("/api/v1/owner/assets", { method: "POST", headers: { "X-CSRFToken": csrf }, body: fd });
    const payload = await res.json().catch(() => ({}));
    pUploadBtn.disabled = false;
    if (!res.ok) {
      passageStatus.textContent = payload.error?.message || "Tải tệp audio thất bại.";
      return;
    }
    const a = payload.data;
    state.audio_assets.unshift({ id: a.id, name: a.original_name, mime: a.detected_mime });
    if (pAudioSearch) pAudioSearch.value = "";
    renderFilteredAudioSelect(pAudioSelect, "Không gắn audio", "");
    pAudioSelect.value = a.id;
    syncAudioAssetDropdown(qpAudioSearch?.value || "");
    passageStatus.textContent = `Đã tải tệp nghe ${a.original_name}.`;
  });

  pForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const res = await fetch(`/api/v1/owner/versions/${state.version_id}/passages`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({
        expected_revision: state.revision,
        ui_direct_edit: true,
        ref: pRef.value.trim(),
        text_body: pText.value.trim(),
        audio_asset_id: pAudioSelect.value || null,
        transcript: pTranscript.value.trim(),
      }),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      passageStatus.textContent = payload.error?.message || "Lưu tài liệu thất bại.";
      return;
    }
    state.revision = payload.data.version_revision;
    document.querySelectorAll('input[name="expected_revision"]').forEach((inp) => { inp.value = String(state.revision); });
    const existingIdx = state.passages.findIndex((p) => p.id === payload.data.id);
    const audioAssetObj = (state.audio_assets || []).find((a) => a.id === pAudioSelect.value);
    const updatedP = {
      id: payload.data.id,
      ref: payload.data.ref,
      text_body: pText.value.trim(),
      audio_asset_id: pAudioSelect.value || "",
      audio_asset_name: audioAssetObj?.name || "",
      transcript: pTranscript.value.trim(),
    };
    if (existingIdx >= 0) state.passages[existingIdx] = updatedP;
    else state.passages.push(updatedP);
    syncPassagesDropdown(qpAudioSearch?.value || "");
    renderPassageManagerList();
    pRef.value = "";
    pText.value = "";
    pTranscript.value = "";
    passageStatus.textContent = `Đã lưu tài liệu ${payload.data.ref}.`;
  });

  qForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (readonly) return;
    showFormError("");
    syncHiddenSkill();

    const isChoice = qType.value === "SINGLE_CHOICE" || qType.value === "MULTIPLE_CHOICE";
    if (currentContext === "READING" && !(qpText?.value || "").trim()) {
      showFormError("Vui lòng nhập nội dung đoạn văn đọc hiểu hoặc chọn đoạn văn đã có.");
      return;
    }
    if (currentContext === "LISTENING" && !qPassage.value && !qpAudioAssetSelect?.value && !qpAudioFile?.files?.[0]) {
      showFormError("Vui lòng chọn file nghe từ kho, chọn bài nghe đã có, hoặc tải tệp nghe mới (MP3/M4A).");
      return;
    }

    const body = {
      expected_revision: state.revision,
      ui_direct_edit: true,
      type: qType.value,
      pirate_game: qType.value === "SINGLE_CHOICE" ? currentPirateGame : false,
      skill: qSkill.value,
      difficulty: qDiff.value,
      max_points: qPoints.value,
      passage_id: null,
      prompt: qPrompt.value.trim(),
      topic_tags: qTopics.value.split("|").map((s) => s.trim()).filter(Boolean),
      error_tags: qErrors.value.split("|").map((s) => s.trim()).filter(Boolean),
      explanation: qExplanation.value.trim(),
    };

    if (isChoice) {
      const options = [];
      let stopped = false;
      const keys = showExtraOpts ? ["A", "B", "C", "D", "E", "F"] : ["A", "B", "C", "D"];
      for (const key of keys) {
        const val = qOptionsRows.querySelector(`[data-opt-key="${key}"]`)?.value?.trim() || "";
        if (!val) {
          stopped = true;
        } else if (stopped) {
          showFormError("Điền các lựa chọn liên tục từ A, không bỏ trống ở giữa.");
          return;
        } else {
          options.push({ content: val });
        }
      }
      body.options = options;
      body.correct_options = Array.from(qOptionsRows.querySelectorAll('input[name="correct_opt_pick"]:checked')).map((i) => i.value);
      if (options.length < 2) {
        showFormError("Nhập ít nhất 2 lựa chọn (A và B).");
        return;
      }
      if (qType.value === "SINGLE_CHOICE" && body.correct_options.length !== 1) {
        showFormError("Hãy chọn đúng 1 đáp án đúng.");
        return;
      }
      if (qType.value === "MULTIPLE_CHOICE" && body.correct_options.length < 2) {
        showFormError("Hãy chọn từ 2 đáp án đúng trở lên.");
        return;
      }
    } else if (qType.value === "SENTENCE_TRANSFORM") {
      const std = qTransformStandard ? qTransformStandard.value.trim() : "";
      if (!std) {
        showFormError("Giáo viên cần nhập câu trả lời chuẩn.");
        return;
      }
      body.standard_answer = std;
    } else if (qType.value === "WORD_ORDER") {
      body.word_tokens = parseWordTokens(qWordTokens.value);
      if (body.word_tokens.length < 2 || body.word_tokens.length > 20) {
        showFormError("Cần từ 2 đến 20 từ/cụm từ theo thứ tự đúng.");
        return;
      }
    } else if (qType.value === "STRESS_CHOICE") {
      body.stress_syllables = parseSyllables(qStressSyllables.value);
      body.correct_syllable_index = Number(qStressIndex.value);
      if (body.stress_syllables.length < 2 || body.stress_syllables.length > 10 || !Number.isInteger(body.correct_syllable_index) || body.correct_syllable_index < 1 || body.correct_syllable_index > body.stress_syllables.length) {
        showFormError("Nhập từ có 2 đến 10 âm tiết (cách nhau bởi dấu '-') và bấm chọn trọng âm.");
        return;
      }
    } else if (qType.value === "MATCH_IMAGE") {
      const rows = [...qMatchRows.children];
      if (rows.some((row) => row.dataset.uploading === "1")) {
        showFormError("Hãy chờ ảnh tải xong trước khi lưu.");
        return;
      }
      body.match_pairs = rows.map((row) => ({
        image_asset_id: row.dataset.assetId,
        word: row.querySelector(".match-word-input").value.trim(),
      }));
      if (body.match_pairs.length < 2 || body.match_pairs.length > 6 || body.match_pairs.some((pair) => !pair.image_asset_id || !pair.word)) {
        showFormError("Cần từ 2 đến 6 cặp có đủ hình ảnh và từ vựng.");
        return;
      }
    } else {
      body.criteria = Array.from(qRubricRows.children).map((card) => {
        const descs = {};
        for (const lv of ["0", "1", "2", "3", "4"]) {
          descs[lv] = card.querySelector(`[data-crit-level="${lv}"]`)?.value?.trim() || "";
        }
        return {
          key: card.dataset.critKey,
          label: card.querySelector('[data-crit-field="label"]')?.value?.trim() || "",
          level_descriptions: descs,
        };
      });
    }

    try {
      body.passage_id = await resolveOrCreateContextPassage();
      body.expected_revision = state.revision;
    } catch (err) {
      showFormError(err.message || "Lưu tài liệu thất bại.");
      return;
    }

    const url = selectedId ? `/api/v1/owner/questions/${selectedId}` : `/api/v1/owner/versions/${state.version_id}/questions`;
    const method = selectedId ? "PATCH" : "POST";
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify(body),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      showFormError(payload.error?.message || "Lưu câu hỏi thất bại.");
      return;
    }
    const targetUrl = new URL(window.location.href);
    targetUrl.searchParams.delete("new_q");
    targetUrl.searchParams.set("q", payload.data.id);
    window.location.assign(targetUrl.toString());
  });

  if (readonly) {
    Array.from(qForm.querySelectorAll("input, select, textarea, button")).forEach((node) => { node.disabled = true; });
  }

  renderPassageManagerList();
  renderQuestionCards();

  const params = new URLSearchParams(window.location.search);
  if (params.get("new_q") === "1" && !readonly) {
    openQuestionModal(null);
  }
}

initVersionEditor();
