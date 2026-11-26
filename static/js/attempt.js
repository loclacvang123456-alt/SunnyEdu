import {createPirateGame} from './pirate-game.js?v=9';

const root = document.querySelector('#exercise');
const form = document.querySelector('#exercise-form');
const container = document.querySelector('#questions');
const status = document.querySelector('#save-status');
const message = document.querySelector('#exercise-message');
const receipt = document.querySelector('#submission-receipt');
const receiptText = document.querySelector('#submission-receipt-text');
const retry = document.querySelector('#retry-save');
const empty = document.querySelector('#exercise-empty');
const submitButton = document.querySelector('#submit-attempt');
const practiceNavigation = document.querySelector('#practice-navigation');
const previousQuestion = document.querySelector('#previous-question');
const nextQuestion = document.querySelector('#next-question');
const questionProgress = document.querySelector('#question-progress');
const attemptId = root.dataset.attemptId;
const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
const api = `/api/v1/attempts/${encodeURIComponent(attemptId)}/`;
const states = new Map();
let attemptRevision = 0;
let pendingSubmission = null;
let submitting = false;
let requiresReload = false;
let activeQuestion = 0;
let practiceEditable = false;
let visibilityActive = root.dataset.attemptStatus === 'IN_PROGRESS';
const visibilityKey = `sunny-visibility-${attemptId}`;
let visibilityInFlight = Promise.resolve();
function readVisibility() {
  try { return JSON.parse(sessionStorage.getItem(visibilityKey)) || {hiddenAt: null, pending: []}; }
  catch { return {hiddenAt: null, pending: []}; }
}
function writeVisibility(data) {
  try { sessionStorage.setItem(visibilityKey, JSON.stringify(data)); } catch { /* Storage can be unavailable. */ }
}
function flushVisibility() {
  visibilityInFlight = visibilityInFlight.then(async () => {
    let data = readVisibility();
    while (data.pending.length && visibilityActive) {
      const event = data.pending[0];
      let response;
      try {
        response = await fetch(`${api}visibility/`, {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf}, body: JSON.stringify(event)});
      } catch { return; }
      if (!response.ok) return;
      data = readVisibility();
      data.pending = data.pending.filter(item => item.id !== event.id);
      writeVisibility(data);
    }
  });
  return visibilityInFlight;
}
function trackVisibility() {
  if (!visibilityActive) return;
  const data = readVisibility();
  if (document.hidden) {
    if (data.hiddenAt === null) data.hiddenAt = Date.now();
  } else if (data.hiddenAt !== null) {
    const duration = Math.min(86400000, Math.max(0, Date.now() - data.hiddenAt));
    if (crypto.randomUUID) data.pending.push({id: crypto.randomUUID(), duration_ms: duration});
    data.hiddenAt = null;
  }
  writeVisibility(data);
  if (!document.hidden) flushVisibility();
}
document.addEventListener('visibilitychange', trackVisibility);
window.addEventListener('online', flushVisibility);
trackVisibility();

function showPracticeQuestion(index) {
  const panels = [...container.querySelectorAll(':scope > .question')];
  if (!panels.length) return;
  activeQuestion = Math.max(0, Math.min(index, panels.length - 1));
  panels.forEach((panel, i) => {
    const isCurrent = i === activeQuestion;
    panel.hidden = !isCurrent;
    if (!isCurrent) {
      panel.style.setProperty('display', 'none', 'important');
    } else {
      panel.style.removeProperty('display');
    }
  });
  const gameQuestion = panels[activeQuestion].dataset.gameQuestion === 'true';
  root.dataset.gameEnabled = String(gameQuestion);
  document.body.classList.toggle('is-pirate-game-mode', gameQuestion);
  practiceNavigation.hidden = gameQuestion;
  previousQuestion.disabled = activeQuestion === 0;
  previousQuestion.hidden = activeQuestion === 0;
  nextQuestion.disabled = activeQuestion === panels.length - 1;
  nextQuestion.hidden = activeQuestion === panels.length - 1;
  submitButton.hidden = !practiceEditable || activeQuestion !== panels.length - 1;
  questionProgress.textContent = `${activeQuestion + 1} / ${panels.length}`;
  requestAnimationFrame(() => { for (const state of states.values()) state.drawMatchLines?.(); });
}

function gameBusy() { return [...states.values()].some(state => state.gameMode && (!state.gameReady || state.game?.hasPending())); }
previousQuestion.addEventListener('click', () => { if (gameBusy()) return notify('Hãy chờ game lưu lựa chọn hoặc kiểm tra hình ảnh.', true); showPracticeQuestion(activeQuestion - 1); });
nextQuestion.addEventListener('click', () => { if (gameBusy()) return notify('Hãy chờ game lưu lựa chọn hoặc kiểm tra hình ảnh.', true); showPracticeQuestion(activeQuestion + 1); });

function notify(text, isError = false) {
  message.hidden = !text;
  message.textContent = text;
  message.setAttribute('role', isError ? 'alert' : 'status');
}

function updateStatus() {
  const all = [...states.values()];
  const blocked = all.some(s => s.error || s.conflict);
  const pending = all.some(s => s.dirty || s.saving);
  retry.hidden = !all.some(s => s.error && !s.conflict);
  status.dataset.state = blocked ? 'error' : pending ? 'pending' : 'saved';
  status.textContent = blocked ? 'Chưa lưu được' : pending ? 'Đang lưu…' : 'Đã lưu';
}

function make(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function readInput(state) {
  if (state.type === 'TEXT' || state.type === 'SENTENCE_TRANSFORM') return {text_answer: state.input.value};
  if (state.gameMode) return {option_ids: state.shot ? [state.shot.option_id] : []};
  if (state.type === 'WORD_ORDER') return {ordered_option_ids: [...state.answer.querySelectorAll(':scope > .word-tile')].map(tile => tile.dataset.optionId)};
  if (state.type === 'MATCH_IMAGE') return {match_pairs: [...state.matches].map(([image_id, word_id]) => ({image_id, word_id}))};
  return {option_ids: [...state.field.querySelectorAll('input:checked')].map(el => el.value)};
}

function writeInput(state, data) {
  if (state.type === 'TEXT' || state.type === 'SENTENCE_TRANSFORM') state.input.value = data.text_answer || '';
  else if (state.gameMode) return;
  else if (state.type === 'WORD_ORDER') {
    const tiles = new Map([...state.field.querySelectorAll('.word-tile')].map(tile => [tile.dataset.optionId, tile]));
    for (const tile of tiles.values()) state.bank.append(tile);
    for (const id of data.ordered_option_ids || []) {
      const tile = tiles.get(id);
      if (tile) state.answer.append(tile);
    }
    for (const tile of tiles.values()) {
      if (!state.answer.contains(tile)) state.bank.append(tile);
    }
  }
  else if (state.type === 'MATCH_IMAGE') {
    state.matches = new Map((data.match_pairs || []).map(pair => [pair.image_id, pair.word_id]));
    state.updateMatchDisplay();
  } else {
    const selected = new Set(data.selected_options || []);
    state.field.querySelectorAll('input').forEach(el => { el.checked = selected.has(el.value); });
  }
}

function conflictUI(state) {
  state.issue.replaceChildren();
  state.issue.append(make('p', 'Câu này đã được thay đổi ở nơi khác. Em chọn bản muốn giữ.'));
  const server = make('button', 'Dùng bản đã lưu', 'button secondary');
  const mine = make('button', 'Giữ bản em đang nhập', 'button secondary');
  server.type = mine.type = 'button';
  server.addEventListener('click', async () => {
    try {
      const current = await fetchAttempt();
      const question = current.questions.find(q => q.question_id === state.id);
      if (!question) throw new Error('Không tìm thấy câu hỏi.');
      writeInput(state, question);
      state.revision = question.response_revision;
      state.dirty = state.conflict = state.error = false;
      state.issue.replaceChildren();
      updateStatus();
    } catch (err) { notify(err.message, true); }
  });
  mine.addEventListener('click', async () => {
    try {
      const current = await fetchAttempt();
      const question = current.questions.find(q => q.question_id === state.id);
      if (!question) throw new Error('Không tìm thấy câu hỏi.');
      state.revision = question.response_revision;
      state.conflict = state.error = false;
      state.dirty = true;
      state.issue.replaceChildren();
      await save(state);
    } catch (err) { notify(err.message, true); }
  });
  state.issue.append(server, document.createTextNode(' '), mine);
}

async function fetchAttempt() {
  const response = await fetch(api, {credentials: 'same-origin', cache: 'no-store', headers: {'Accept': 'application/json'}});
  if (response.status === 401) throw new Error('Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại rồi quay lại bài.');
  if (!response.ok) throw new Error('Không tải được bài. Em hãy thử lại.');
  const payload = await response.json();
  attemptRevision = Math.max(attemptRevision, payload.data.revision);
  root.dataset.revision = String(attemptRevision);
  return payload.data;
}

async function save(state) {
  if (!state.dirty || state.saving || state.conflict) return;
  clearTimeout(state.timer);
  state.saving = true;
  state.error = false;
  const sentGeneration = state.generation;
  const body = {...readInput(state), expected_revision: state.revision};
  updateStatus();
  try {
    const response = await fetch(`${api}responses/${encodeURIComponent(state.id)}/`, {
      method: 'PUT', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf}, body: JSON.stringify(body)
    });
    if (response.status === 409) {
      state.conflict = true;
      conflictUI(state);
    } else if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(response.status === 401 ? 'Phiên đăng nhập đã hết hạn. Hãy giữ trang này mở và đăng nhập lại.' : (payload.error?.message || 'Chưa gửi được thay đổi. Em giữ trang này mở.'));
    } else {
      const payload = await response.json();
      state.revision = payload.data.response_revision;
      attemptRevision = Math.max(attemptRevision, payload.data.attempt_revision);
      root.dataset.revision = String(attemptRevision);
      state.dirty = state.generation !== sentGeneration;
      state.issue.replaceChildren();
      notify('');
    }
  } catch (err) {
    state.error = true;
    notify(err.message || 'Chưa gửi được thay đổi. Em giữ trang này mở.', true);
  } finally {
    state.saving = false;
    updateStatus();
    if (state.dirty && !state.error && !state.conflict) save(state);
  }
}

function changed(state) {
  state.generation += 1;
  state.dirty = true;
  state.error = false;
  clearTimeout(state.timer);
  if (!state.conflict) state.timer = setTimeout(() => save(state), 1000);
  updateStatus();
}

/* --- SFX & VFX Synthesizer for Instant Feedback --- */
let audioCtx = null;
function getAudioContext() {
  if (!audioCtx) {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (AudioContext) audioCtx = new AudioContext();
  }
  if (audioCtx && audioCtx.state === 'suspended') {
    audioCtx.resume().catch(() => {});
  }
  return audioCtx;
}

function playCorrectSound() {
  try {
    const ctx = getAudioContext();
    if (!ctx) return;
    const now = ctx.currentTime;
    const notes = [523.25, 659.25, 783.99, 1046.50];
    notes.forEach((freq, idx) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, now + idx * 0.07);
      gain.gain.setValueAtTime(0.18, now + idx * 0.07);
      gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.07 + 0.32);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now + idx * 0.07);
      osc.stop(now + idx * 0.07 + 0.32);
    });
  } catch (e) {}
}

function playWrongSound() {
  try {
    const ctx = getAudioContext();
    if (!ctx) return;
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(220, now);
    osc.frequency.exponentialRampToValueAtTime(130, now + 0.28);
    gain.gain.setValueAtTime(0.15, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 0.3);
  } catch (e) {}
}

function spawnConfetti(originEl) {
  const rect = originEl.getBoundingClientRect();
  const startX = rect.left + rect.width / 2;
  const startY = rect.top + rect.height / 2;
  const colors = ['#22c55e', '#3b82f6', '#f59e0b', '#ec4899', '#8b5cf6', '#10b981'];

  for (let i = 0; i < 26; i++) {
    const p = document.createElement('div');
    p.className = 'confetti-particle';
    const angle = Math.random() * 2 * Math.PI;
    const distance = 50 + Math.random() * 110;
    const dx = Math.cos(angle) * distance;
    const dy = Math.sin(angle) * distance - 20;
    const rot = (Math.random() - 0.5) * 720;
    const size = 6 + Math.random() * 8;

    p.style.left = `${startX}px`;
    p.style.top = `${startY}px`;
    p.style.width = `${size}px`;
    p.style.height = `${size * (Math.random() > 0.5 ? 1 : 1.6)}px`;
    p.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
    p.style.setProperty('--dx', `${dx}px`);
    p.style.setProperty('--dy', `${dy}px`);
    p.style.setProperty('--rot', `${rot}deg`);

    document.body.append(p);
    setTimeout(() => p.remove(), 1200);
  }
}

function triggerShake(element) {
  element.classList.remove('option--instant-wrong');
  void element.offsetWidth;
  element.classList.add('option--instant-wrong');
}

/* --- Fullscreen Enforcement & 5s Auto Submit --- */
let fsTimer = null;
let fsRemaining = 5;
let fsWarningModal = null;
let fsGateModal = null;
let fsGatePassed = false;

function isFullscreen() {
  return Boolean(document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement);
}

function requestFullscreen() {
  const docEl = document.documentElement;
  const fn = docEl.requestFullscreen || docEl.webkitRequestFullscreen || docEl.mozRequestFullScreen || docEl.msRequestFullscreen;
  if (fn) {
    return fn.call(docEl).catch(() => {});
  }
  return Promise.resolve();
}

function cleanupFullscreen() {
  if (fsTimer) {
    clearInterval(fsTimer);
    fsTimer = null;
  }
  if (fsWarningModal) {
    fsWarningModal.remove();
    fsWarningModal = null;
  }
  if (fsGateModal) {
    fsGateModal.remove();
    fsGateModal = null;
  }
  document.removeEventListener('fullscreenchange', handleFullscreenState);
  document.removeEventListener('webkitfullscreenchange', handleFullscreenState);
  document.removeEventListener('mozfullscreenchange', handleFullscreenState);
  document.removeEventListener('MSFullscreenChange', handleFullscreenState);
  document.removeEventListener('visibilitychange', handleFullscreenState);
}

function handleFullscreenState() {
  if (!practiceEditable || submitting) return;
  if (!fsGatePassed) return;

  const valid = isFullscreen() && !document.hidden;

  if (valid) {
    if (fsTimer) {
      clearInterval(fsTimer);
      fsTimer = null;
    }
    fsRemaining = 5;
    if (fsWarningModal) {
      fsWarningModal.remove();
      fsWarningModal = null;
    }
  } else {
    if (!fsTimer) {
      fsRemaining = 5;
      showFullscreenWarning();
      fsTimer = setInterval(() => {
        fsRemaining--;
        updateFullscreenWarningText();
        if (fsRemaining <= 0) {
          clearInterval(fsTimer);
          fsTimer = null;
          if (fsWarningModal) {
            const desc = fsWarningModal.querySelector('.fs-modal-desc');
            if (desc) desc.textContent = 'Đã hết 5 giây ngoài toàn màn hình. Hệ thống đang tự động kết thúc và nộp bài làm...';
          }
          doSubmit(true);
        }
      }, 1000);
    }
  }
}

function showFullscreenWarning() {
  if (fsWarningModal) return;
  fsWarningModal = document.createElement('div');
  fsWarningModal.className = 'fs-modal-overlay';
  fsWarningModal.innerHTML = `
    <div class="fs-modal-card is-warning" role="alertdialog" aria-modal="true">
      <div class="fs-modal-icon">⚠️</div>
      <h2 class="fs-modal-title">CẢNH BÁO RỜI TOÀN MÀN HÌNH!</h2>
      <div class="fs-countdown-badge" id="fs-count">5</div>
      <p class="fs-modal-desc">Em đã thoát toàn màn hình hoặc đổi tab! Bài làm sẽ <strong>tự động nộp và kết thúc</strong> nếu không quay lại trong <span id="fs-count-text">5</span> giây!</p>
      <button type="button" class="button primary fs-btn-action" id="fs-resume-btn">Quay lại toàn màn hình ngay</button>
    </div>
  `;
  document.body.append(fsWarningModal);
  const btn = fsWarningModal.querySelector('#fs-resume-btn');
  if (btn) {
    btn.addEventListener('click', async () => {
      await requestFullscreen();
      handleFullscreenState();
    });
  }
}

function updateFullscreenWarningText() {
  if (!fsWarningModal) return;
  const countEl = fsWarningModal.querySelector('#fs-count');
  const countText = fsWarningModal.querySelector('#fs-count-text');
  if (countEl) countEl.textContent = String(Math.max(0, fsRemaining));
  if (countText) countText.textContent = String(Math.max(0, fsRemaining));
}

function initFullscreenEnforcement() {
  if (!practiceEditable) return;

  document.addEventListener('fullscreenchange', handleFullscreenState);
  document.addEventListener('webkitfullscreenchange', handleFullscreenState);
  document.addEventListener('mozfullscreenchange', handleFullscreenState);
  document.addEventListener('MSFullscreenChange', handleFullscreenState);
  document.addEventListener('visibilitychange', handleFullscreenState);

  if (isFullscreen()) {
    fsGatePassed = true;
    return;
  }

  fsGateModal = document.createElement('div');
  fsGateModal.className = 'fs-modal-overlay';
  fsGateModal.innerHTML = `
    <div class="fs-modal-card" role="dialog" aria-modal="true">
      <div class="fs-modal-icon">🖥️</div>
      <h2 class="fs-modal-title">Chế độ Toàn Màn Hình</h2>
      <p class="fs-modal-desc">Bài làm yêu cầu hiển thị toàn màn hình để chống gian lận. <strong>Không được thoát toàn màn hình hoặc đổi tab quá 5 giây</strong>, nếu vi phạm bài thi sẽ lập tức kết thúc.</p>
      <button type="button" class="button primary fs-btn-action" id="fs-start-btn">Bật toàn màn hình và bắt đầu làm bài</button>
    </div>
  `;
  document.body.append(fsGateModal);

  const startBtn = fsGateModal.querySelector('#fs-start-btn');
  if (startBtn) {
    startBtn.addEventListener('click', async () => {
      await requestFullscreen();
      fsGatePassed = true;
      if (fsGateModal) {
        fsGateModal.remove();
        fsGateModal = null;
      }
    });
  }
}

function renderQuestion(question, editable, gameEnabled, questionIndex = 0, totalQuestions = 1) {
  const panel = make('section', undefined, 'panel question');
  const gameQuestion = question.type === 'SINGLE_CHOICE' && gameEnabled && question.pirate_game !== false && !question.passage_text;
  panel.dataset.gameQuestion = String(gameQuestion);
  const field = make('fieldset');
  field.disabled = !editable;
  if (!gameQuestion) {
    const legend = make('legend');
    const promptText = question.type === 'STRESS_CHOICE' ? 'Chọn trọng âm chính của từ:' : question.prompt;
    legend.append(make('span', `Câu ${question.position}`, 'question-number'), document.createTextNode(` ${promptText}`));
    field.append(legend);
    if (question.passage_text) {
      const passage = make('div');
      passage.append(make('h3', 'Nội dung bài đọc'), make('p', question.passage_text));
      panel.append(passage);
    }
    if (question.image_url) {
      const mediaBox = make('div', undefined, 'question-media-wrap');
      mediaBox.style.margin = '10px 0 16px 0';
      if (question.image_url.includes('_audio') || question.image_url.match(/\.(mp3|wav|ogg|m4a)($|\?)/i)) {
        const audio = document.createElement('audio');
        audio.controls = true;
        audio.preload = 'none';
        audio.src = question.image_url;
        audio.style.width = '100%';
        audio.style.maxWidth = '420px';
        mediaBox.append(audio);
      } else {
        const img = document.createElement('img');
        img.src = question.image_url;
        img.alt = `Hình minh họa câu ${question.position}`;
        img.className = 'question-illustration';
        img.loading = 'lazy';
        img.style.maxWidth = '100%';
        img.style.maxHeight = '360px';
        img.style.borderRadius = '8px';
        img.style.boxShadow = '0 2px 8px rgba(0,0,0,0.08)';
        img.style.display = 'block';
        mediaBox.append(img);
      }
      field.append(mediaBox);
    }
  }
  const state = {id: question.question_id, type: question.type, revision: question.response_revision, generation: 0, dirty: false, saving: false, error: false, conflict: false, field, input: null, timer: null, issue: make('div')};
  if (gameQuestion) {
    state.gameMode = true;
    state.gameReady = false;
    state.shot = question.shot || null;
    const host = make('div', undefined, 'pirate-host');
    host.textContent = 'Đang tải hoạt cảnh trò chơi…';
    field.append(host);
    createPirateGame({
      question,
      attemptId,
      csrfToken: csrf,
      editable,
      questionIndex,
      totalQuestions,
      onPrevious: () => { if (!gameBusy()) showPracticeQuestion(questionIndex - 1); },
      onNext: () => showPracticeQuestion(questionIndex + 1),
      onFinish: () => submitButton.click(),
      onRecorded: receipt => {
        state.shot = receipt;
        state.revision = receipt.response_revision;
        attemptRevision = Math.max(attemptRevision, receipt.attempt_revision);
        root.dataset.revision = String(attemptRevision);
        state.dirty = state.error = state.conflict = false;
        updateStatus();
      }
    }).then(game => {
      state.game = game;
      state.gameReady = game.ready;
      host.replaceChildren(game.element);
    }).catch(err => {
      console.error(err);
      host.textContent = 'Game chưa sẵn sàng. Em hãy liên hệ giáo viên.';
      const exit = make('a', '← Thoát', 'pirate-exit-btn');
      exit.href = '/student/';
      host.append(exit);
    });
  } else if (question.type === 'SINGLE_CHOICE' || question.type === 'MULTIPLE_CHOICE') {
    const instantFeedbackEnabled = root.dataset.instantFeedback === 'true' || Boolean(question.correct_option_ids?.length);
    const optionLabels = new Map();
    for (const option of question.options) {
      const label = make('label', undefined, 'option');
      const input = make('input');
      input.type = question.type === 'SINGLE_CHOICE' ? 'radio' : 'checkbox';
      input.name = `question_${question.question_id}`;
      input.value = option.id;
      label.append(input, make('span', option.content));
      field.append(label);
      optionLabels.set(option.id, label);
    }

    function applyInstantFeedback(selectedIds, animate = false) {
      if (!instantFeedbackEnabled || !question.correct_option_ids) return false;
      const correctSet = new Set(question.correct_option_ids);
      const isCorrect = selectedIds.length > 0 && selectedIds.every(id => correctSet.has(id)) && (question.type === 'SINGLE_CHOICE' ? true : selectedIds.length === correctSet.size);

      for (const [optId, optLabel] of optionLabels) {
        optLabel.classList.remove('option--instant-correct', 'option--instant-wrong', 'option--instant-highlight-target');
        optLabel.querySelectorAll('.instant-feedback-badge').forEach(b => b.remove());
      }

      if (selectedIds.length === 0) return false;

      if (isCorrect) {
        for (const optId of selectedIds) {
          const optLabel = optionLabels.get(optId);
          if (optLabel) {
            optLabel.classList.add('option--instant-correct');
            const badge = make('span', '✓ Đúng', 'instant-feedback-badge badge--correct');
            optLabel.append(badge);
            if (animate) spawnConfetti(optLabel);
          }
        }
        if (animate) playCorrectSound();
      } else {
        for (const optId of selectedIds) {
          const optLabel = optionLabels.get(optId);
          if (optLabel) {
            if (correctSet.has(optId)) {
              optLabel.classList.add('option--instant-correct');
            } else {
              optLabel.classList.add('option--instant-wrong');
              const badge = make('span', '✗ Sai', 'instant-feedback-badge badge--wrong');
              optLabel.append(badge);
              if (animate) triggerShake(optLabel);
            }
          }
        }
        for (const corrId of correctSet) {
          const corrLabel = optionLabels.get(corrId);
          if (corrLabel && !corrLabel.classList.contains('option--instant-correct')) {
            corrLabel.classList.add('option--instant-highlight-target');
            const badge = make('span', '★ Đáp án đúng', 'instant-feedback-badge badge--correct-target');
            corrLabel.append(badge);
          }
        }
        if (animate) playWrongSound();
      }
      return isCorrect;
    }

    field.addEventListener('change', () => {
      changed(state);
      if (instantFeedbackEnabled) {
        const checkedInputs = [...field.querySelectorAll('input:checked')];
        const selectedIds = checkedInputs.map(i => i.value);
        applyInstantFeedback(selectedIds, true);
      }
    });

    if (instantFeedbackEnabled && question.selected_options?.length) {
      applyInstantFeedback(question.selected_options, false);
    }
  } else if (question.type === 'MATCH_IMAGE') {
    const instruction = make('p', 'Kéo hoặc chạm vào tranh và từ để nối.');
    const board = make('div', undefined, 'match-board');
    const lines = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    lines.classList.add('match-lines');
    lines.setAttribute('aria-hidden', 'true');
    const imageColumn = make('div', undefined, 'match-column match-images');
    const wordColumn = make('div', undefined, 'match-column match-words');
    const matchStatus = make('p', '', 'hint');
    matchStatus.setAttribute('aria-live', 'polite');
    board.append(lines, imageColumn, wordColumn);
    state.matches = new Map();
    let selected = null;
    let drag = null;
    const nodes = new Map();
    const removeButtons = new Map();
    const findDropTarget = (clientX, clientY, startNode) => {
      if (!startNode) return null;
      const x = Math.max(2, Math.min(window.innerWidth - 2, clientX));
      const y = Math.max(2, Math.min(window.innerHeight - 2, clientY));
      const target = document.elementFromPoint(x, y)?.closest('.match-node');
      if (target && board.contains(target) && target.dataset.kind !== startNode.dataset.kind) return target;
      return null;
    };
    const syncDragHighlight = () => {
      for (const node of nodes.values()) {
        node.classList.toggle('is-drag-source', Boolean(drag && drag.node === node));
        node.classList.toggle('is-drag-target', Boolean(drag && drag.hoverTarget === node));
      }
    };
    let autoScrollFrame = null;
    const stopAutoScroll = () => {
      if (autoScrollFrame !== null) {
        cancelAnimationFrame(autoScrollFrame);
        autoScrollFrame = null;
      }
    };
    const getAutoScrollDelta = clientY => {
      const edge = 90;
      const maxStep = 18;
      if (clientY < edge) {
        const ratio = Math.min(1, (edge - clientY) / edge);
        return -Math.max(4, Math.round(ratio * maxStep));
      }
      if (clientY > window.innerHeight - edge) {
        const ratio = Math.min(1, (clientY - (window.innerHeight - edge)) / edge);
        return Math.max(4, Math.round(ratio * maxStep));
      }
      return 0;
    };
    const tickAutoScroll = () => {
      autoScrollFrame = null;
      if (!drag || !drag.moved) return;
      const delta = getAutoScrollDelta(drag.y);
      if (!delta) return;
      const prevY = window.scrollY;
      window.scrollBy(0, delta);
      if (window.scrollY !== prevY) {
        drag.hoverTarget = findDropTarget(drag.x, drag.y, drag.node);
        syncDragHighlight();
        state.drawMatchLines();
      }
      autoScrollFrame = requestAnimationFrame(tickAutoScroll);
    };
    const addLine = (from, to, temporary = false) => {
      const boardRect = board.getBoundingClientRect();
      const fromRect = from.getBoundingClientRect();
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', String(fromRect.left + fromRect.width / 2 - boardRect.left));
      line.setAttribute('y1', String(fromRect.top + fromRect.height / 2 - boardRect.top));
      if (to instanceof Element) {
        const toRect = to.getBoundingClientRect();
        line.setAttribute('x2', String(toRect.left + toRect.width / 2 - boardRect.left));
        line.setAttribute('y2', String(toRect.top + toRect.height / 2 - boardRect.top));
      } else {
        line.setAttribute('x2', String(to.x - boardRect.left));
        line.setAttribute('y2', String(to.y - boardRect.top));
      }
      if (temporary) line.classList.add('match-line-pending');
      lines.append(line);
    };
    state.drawMatchLines = () => {
      lines.replaceChildren();
      if (!board.getClientRects().length) return;
      for (const [imageId, wordId] of state.matches) {
        const image = nodes.get(`image:${imageId}`), word = nodes.get(`word:${wordId}`);
        if (image && word) addLine(image, word);
      }
      if (drag?.moved) addLine(drag.node, {x: drag.x, y: drag.y}, true);
    };
    state.updateMatchDisplay = () => {
      for (const [key, node] of nodes) node.setAttribute('aria-pressed', String(selected?.key === key));
      for (const [wordId, remove] of removeButtons) {
        const matched = [...state.matches.values()].includes(wordId);
        remove.hidden = !editable || !matched;
      }
      matchStatus.textContent = selected ? `Đã chọn ${selected.label}. Hãy chọn ${selected.kind === 'image' ? 'một từ' : 'một tranh'}.` : `Đã nối ${state.matches.size} / ${question.match_images.length} cặp.`;
      requestAnimationFrame(state.drawMatchLines);
    };
    function choose(node) {
      if (!editable || !node) return;
      const endpoint = {key: `${node.dataset.kind}:${node.dataset.id}`, kind: node.dataset.kind, id: node.dataset.id, label: node.dataset.label};
      if (!selected || selected.kind === endpoint.kind) {
        selected = selected?.key === endpoint.key ? null : endpoint;
      } else {
        const imageId = selected.kind === 'image' ? selected.id : endpoint.id;
        const wordId = selected.kind === 'word' ? selected.id : endpoint.id;
        for (const [existingImage, existingWord] of state.matches) if (existingWord === wordId) state.matches.delete(existingImage);
        state.matches.set(imageId, wordId);
        selected = null;
        changed(state);
      }
      state.updateMatchDisplay();
    }
    function setupNode(node, kind, id, label) {
      node.type = 'button';
      node.dataset.kind = kind;
      node.dataset.id = id;
      node.dataset.label = label;
      node.setAttribute('aria-label', label);
      node.setAttribute('aria-pressed', 'false');
      nodes.set(`${kind}:${id}`, node);
      node.addEventListener('click', event => { if (event.detail === 0) choose(node); });
      node.addEventListener('pointerdown', event => {
        if (!editable || event.button !== 0) return;
        event.preventDefault();
        node.focus();
        drag = {node, pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, x: event.clientX, y: event.clientY, moved: false, hoverTarget: null};
        node.setPointerCapture(event.pointerId);
        syncDragHighlight();
      });
      node.addEventListener('pointermove', event => {
        if (!drag || drag.pointerId !== event.pointerId) return;
        drag.x = event.clientX; drag.y = event.clientY;
        drag.hoverTarget = findDropTarget(event.clientX, event.clientY, drag.node);
        drag.moved = drag.moved || Boolean(drag.hoverTarget) || Math.hypot(drag.x - drag.startX, drag.y - drag.startY) > 8;
        syncDragHighlight();
        state.drawMatchLines();
        if (drag.moved && getAutoScrollDelta(drag.y) !== 0 && autoScrollFrame === null) {
          autoScrollFrame = requestAnimationFrame(tickAutoScroll);
        } else if (!getAutoScrollDelta(drag.y)) {
          stopAutoScroll();
        }
      });
      node.addEventListener('pointerup', event => {
        if (!drag || drag.pointerId !== event.pointerId) return;
        const wasDrag = drag.moved;
        const start = drag.node;
        const target = drag.hoverTarget || findDropTarget(event.clientX, event.clientY, start);
        drag = null;
        stopAutoScroll();
        syncDragHighlight();
        state.drawMatchLines();
        if (wasDrag && target) {
          selected = {key: `${start.dataset.kind}:${start.dataset.id}`, kind: start.dataset.kind, id: start.dataset.id, label: start.dataset.label};
          choose(target);
        } else if (!wasDrag) choose(start);
      });
      node.addEventListener('pointercancel', () => {
        drag = null;
        stopAutoScroll();
        syncDragHighlight();
        state.drawMatchLines();
      });
    }
    question.match_images.forEach((image, index) => {
      const node = make('button', undefined, 'match-node match-image-node');
      const picture = make('img');
      picture.src = image.url;
      picture.alt = '';
      picture.loading = 'lazy';
      picture.width = 180; picture.height = 180;
      node.append(picture);
      setupNode(node, 'image', image.id, `Tranh ${index + 1}`);
      imageColumn.append(node);
    });
    question.match_words.forEach(word => {
      const node = make('button', word.text, 'match-node match-word-node');
      setupNode(node, 'word', word.id, word.text);
      const row = make('div', undefined, 'match-word-row');
      const remove = make('button', '×', 'match-remove');
      remove.type = 'button';
      remove.hidden = true;
      remove.setAttribute('aria-label', `Bỏ nối từ ${word.text}`);
      remove.addEventListener('click', () => {
        for (const [imageId, wordId] of state.matches) {
          if (wordId === word.id) state.matches.delete(imageId);
        }
        selected = null;
        changed(state);
        state.updateMatchDisplay();
      });
      removeButtons.set(word.id, remove);
      row.append(node, remove);
      wordColumn.append(row);
    });
    if (globalThis.ResizeObserver) new ResizeObserver(() => state.drawMatchLines()).observe(board);
    window.addEventListener('resize', state.drawMatchLines);
    field.append(instruction, board, matchStatus);
  } else if (question.type === 'STRESS_CHOICE') {
    const instantFeedbackEnabled = root.dataset.instantFeedback === 'true' || Boolean(question.correct_option_ids?.length);
    const syllableLabels = new Map();
    const block = make('div', undefined, 'stress-target-block');
    const wordLine = make('div', undefined, 'stress-word-line');
    const wordAnchor = make('div', undefined, 'stress-word-anchor');
    const syllables = make('div', undefined, 'stress-syllables');
    for (const option of question.options) {
      const label = make('label', undefined, 'stress-syllable');
      const input = make('input');
      input.type = 'radio';
      input.name = `question_${question.question_id}`;
      input.value = option.id;
      label.append(input, make('span', option.content));
      syllables.append(label);
      syllableLabels.set(option.id, label);
    }
    const guide = make('div', undefined, 'stress-hand-guide');
    const handIcon = make('span', '👆', 'stress-hand-icon');
    handIcon.setAttribute('aria-hidden', 'true');
    guide.append(handIcon, make('span', 'Ấn vào đây để chọn vị trí trọng âm', 'stress-hand-text'));
    wordAnchor.append(syllables, guide);
    wordLine.append(wordAnchor);
    block.append(wordLine);
    field.append(block);

    function applyStressFeedback(selectedId, animate = false) {
      if (!instantFeedbackEnabled || !question.correct_option_ids?.length || !selectedId) return;
      const correctId = question.correct_option_ids[0];
      for (const [sId, sLabel] of syllableLabels) {
        sLabel.classList.remove('option--instant-correct', 'option--instant-wrong', 'option--instant-highlight-target');
      }
      const chosenLabel = syllableLabels.get(selectedId);
      if (selectedId === correctId) {
        if (chosenLabel) {
          chosenLabel.classList.add('option--instant-correct');
          if (animate) spawnConfetti(chosenLabel);
        }
        if (animate) playCorrectSound();
      } else {
        if (chosenLabel) {
          chosenLabel.classList.add('option--instant-wrong');
          if (animate) triggerShake(chosenLabel);
        }
        const correctLabel = syllableLabels.get(correctId);
        if (correctLabel) {
          correctLabel.classList.add('option--instant-highlight-target');
        }
        if (animate) playWrongSound();
      }
    }

    field.addEventListener('change', () => {
      changed(state);
      if (instantFeedbackEnabled) {
        const checked = field.querySelector('input:checked');
        if (checked) applyStressFeedback(checked.value, true);
      }
    });

    if (instantFeedbackEnabled && question.selected_options?.length) {
      applyStressFeedback(question.selected_options[0], false);
    }
  } else if (question.type === 'WORD_ORDER') {
    const instruction = make('p', 'Kéo hoặc chạm vào các từ để xếp câu.');
    const answer = make('div', undefined, 'word-answer');
    const bank = make('div', undefined, 'word-bank');
    answer.setAttribute('aria-label', 'Câu em đang sắp xếp');
    bank.setAttribute('aria-label', 'Các từ để chọn');
    state.answer = answer;
    state.bank = bank;
    let dragged = null;
    let preview = null;
    const clearPreview = () => { preview?.remove(); preview = null; };
    const showPreview = (tile, zone, x, y) => {
      if (!editable || !tile || !zone || !field.contains(zone)) { clearPreview(); return; }
      if (!preview) {
        preview = make('span', tile.textContent, 'word-tile-preview');
        preview.setAttribute('aria-hidden', 'true');
        const rect = tile.getBoundingClientRect();
        preview.style.width = `${rect.width}px`;
        preview.style.minHeight = `${rect.height}px`;
      }
      const tiles = [...zone.querySelectorAll(':scope > .word-tile')].filter(item => item !== tile);
      if (!tiles.length) { zone.append(preview); return; }
      const positions = tiles.map(item => ({item, rect: item.getBoundingClientRect()}));
      const nearest = positions.reduce((best, pos) =>
        Math.abs(y - (pos.rect.top + pos.rect.bottom) / 2) < Math.abs(y - (best.rect.top + best.rect.bottom) / 2) ? pos : best);
      const row = positions.filter(pos => Math.abs((pos.rect.top + pos.rect.bottom) / 2 - (nearest.rect.top + nearest.rect.bottom) / 2) < 8);
      const before = row.find(pos => x < (pos.rect.left + pos.rect.right) / 2);
      const lastIndex = tiles.indexOf(row[row.length - 1].item);
      zone.insertBefore(preview, before ? before.item : (tiles[lastIndex + 1] || null));
    };
    const commitPreview = (tile, zone) => {
      if (!editable || !tile || !preview || preview.parentElement !== zone) { clearPreview(); return; }
      zone.insertBefore(tile, preview);
      clearPreview();
      changed(state);
    };
    const zoneAt = (x, y) => document.elementFromPoint(x, y)?.closest('.word-answer, .word-bank');
    for (const option of question.options) {
      const tile = make('button', option.content, 'word-tile');
      tile.type = 'button';
      tile.draggable = editable;
      tile.dataset.optionId = option.id;
      tile.addEventListener('click', () => {
        if (!editable) return;
        (answer.contains(tile) ? bank : answer).append(tile);
        changed(state);
      });
      tile.addEventListener('dragstart', event => { dragged = tile; event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', option.id); });
      tile.addEventListener('dragend', () => { clearPreview(); dragged = null; });
      let touchStart = null;
      let touchMoved = false;
      tile.addEventListener('touchstart', event => { const t = event.touches[0]; touchStart = {x: t.clientX, y: t.clientY}; touchMoved = false; }, {passive: true});
      tile.addEventListener('touchmove', event => {
        if (!editable || !touchStart) return;
        const t = event.touches[0];
        if (!touchMoved && Math.hypot(t.clientX - touchStart.x, t.clientY - touchStart.y) <= 12) return;
        touchMoved = true;
        event.preventDefault();
        showPreview(tile, zoneAt(t.clientX, t.clientY), t.clientX, t.clientY);
      }, {passive: false});
      tile.addEventListener('touchend', event => {
        if (!touchStart) return;
        const t = event.changedTouches[0];
        const moved = touchMoved || Math.hypot(t.clientX - touchStart.x, t.clientY - touchStart.y) > 12;
        touchStart = null;
        if (!moved) return;
        event.preventDefault();
        const zone = zoneAt(t.clientX, t.clientY);
        showPreview(tile, zone, t.clientX, t.clientY);
        commitPreview(tile, zone);
      }, {passive: false});
      tile.addEventListener('touchcancel', () => { touchStart = null; clearPreview(); });
      bank.append(tile);
    }
    for (const zone of [answer, bank]) {
      zone.addEventListener('dragover', event => {
        if (!dragged) return;
        event.preventDefault();
        showPreview(dragged, zone, event.clientX, event.clientY);
      });
      zone.addEventListener('dragleave', event => {
        if (!zone.contains(event.relatedTarget)) clearPreview();
      });
      zone.addEventListener('drop', event => {
        event.preventDefault();
        showPreview(dragged, zone, event.clientX, event.clientY);
        commitPreview(dragged, zone);
        dragged = null;
      });
    }
    field.append(instruction, make('span', 'Câu của em', 'word-label'), answer, make('span', 'Các từ để chọn', 'word-label'), bank);
  } else if (question.type === 'SENTENCE_TRANSFORM') {
    const id = `answer-${question.question_id}`;
    const instruction = make('p', 'Viết lại câu hoàn chỉnh theo đúng yêu cầu biến đổi:');
    const label = make('label', 'Câu đã đổi của em:');
    label.htmlFor = id;
    const input = make('input');
    input.id = id;
    input.type = 'text';
    input.placeholder = 'Nhập câu đã chuyển đổi hoàn chỉnh của em vào đây...';
    input.maxLength = 2000;
    input.style.fontSize = '15px';
    input.style.padding = '10px 14px';
    input.style.width = '100%';
    input.addEventListener('input', () => changed(state));
    field.append(instruction, label, input);
    state.input = input;
  } else if (question.type === 'TEXT') {
    const id = `answer-${question.question_id}`;
    const label = make('label', 'Câu trả lời của em');
    label.htmlFor = id;
    const input = make('textarea');
    input.id = id;
    input.rows = 6;
    input.maxLength = 10000;
    input.addEventListener('input', () => changed(state));
    field.append(label, input);
    state.input = input;
  } else {
    field.append(make('p', 'Chưa hỗ trợ ghi âm. Em hãy liên hệ giáo viên.'));
  }
  panel.append(field, state.issue);
  states.set(state.id, state);
  if (state.type !== 'AUDIO') writeInput(state, question);
  return panel;
}

retry.addEventListener('click', () => {
  for (const state of states.values()) {
    if (state.error && !state.conflict) { state.error = false; save(state); }
  }
});
window.addEventListener('online', () => {
  if ([...states.values()].some(s => s.error)) notify('Đã có mạng. Em bấm “Thử lưu lại”.');
});
window.addEventListener('beforeunload', event => {
  if (pendingSubmission || [...states.values()].some(s => s.dirty || s.saving || s.conflict || s.game?.hasPending())) {
    event.preventDefault();
    event.returnValue = '';
  }
});

try {
  if (!attemptId) throw new Error('Không tìm thấy lượt làm bài. Em hãy quay lại danh sách bài tập.');
  const attempt = await fetchAttempt();
  const editable = attempt.status === 'IN_PROGRESS';
  practiceEditable = editable;
  if (editable) {
    initFullscreenEnforcement();
  }
  const isGame = root.dataset.mode === 'PRACTICE' && attempt.game_feedback_enabled === true;
  if (root.dataset.mode === 'PRACTICE') practiceNavigation.append(submitButton);
  for (const [qIndex, question] of attempt.questions.entries()) {
    const qNode = renderQuestion(question, editable, isGame, qIndex, attempt.questions.length);
    if (isGame && qIndex !== 0) {
      qNode.hidden = true;
      qNode.style.setProperty('display', 'none', 'important');
    }
    container.append(qNode);
  }
  if (root.dataset.mode === 'PRACTICE' && attempt.questions.length) {
    const unanswered = isGame && editable ? [...states.values()].findIndex(isBlank) : 0;
    showPracticeQuestion(unanswered < 0 ? attempt.questions.length - 1 : unanswered);
  }
  container.setAttribute('aria-busy', 'false');
  empty.hidden = attempt.questions.length !== 0;
  if (!editable) notify('Lượt làm này đã đóng, em chỉ có thể xem câu trả lời.');
  else {
    if (root.dataset.mode !== 'PRACTICE' && submitButton) submitButton.hidden = false;
    if (attempt.questions.some(q => q.type === 'AUDIO')) {
      submitButton.disabled = true;
      notify('Bài có câu ghi âm chưa được hỗ trợ. Em hãy liên hệ giáo viên trước khi nộp.');
    }
  }
  updateStatus();
} catch (err) {
  root.dataset.gameEnabled = 'false';
  document.body.classList.remove('is-pirate-game-mode');
  container.setAttribute('aria-busy', 'false');
  status.dataset.state = 'error';
  status.textContent = 'Không tải được';
  notify(err.message, true);
}


function lockAnswers(locked) {
  container.querySelectorAll('fieldset').forEach(field => { field.disabled = locked; });
}

function isBlank(state) {
  if (state.type === 'TEXT' || state.type === 'SENTENCE_TRANSFORM') return !state.input.value.trim();
  if (state.gameMode) return !state.shot;
  if (state.type === 'WORD_ORDER') return !state.answer.querySelector(':scope > .word-tile');
  if (state.type === 'MATCH_IMAGE') return state.matches.size === 0;
  return !state.field.querySelector('input:checked');
}

async function flushSaves() {
  const deadline = Date.now() + 25000;
  for (const state of states.values()) {
    clearTimeout(state.timer);
    while (state.saving && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 50));
    if (state.saving) throw new Error('Đang chờ lưu câu trả lời. Em thử nộp lại sau.');
    if (state.conflict) throw new Error('Em cần giải quyết câu trả lời bị thay đổi trước khi nộp.');
    if (state.dirty) { state.error = false; await save(state); }
    if (state.error || state.dirty || state.conflict) throw new Error('Có câu chưa lưu. Em kiểm tra và thử lại.');
  }
}

async function doSubmit(force = false) {
  if (submitting || (submitButton.disabled && !force)) return;
  if (gameBusy()) { notify('Hãy chờ game lưu lựa chọn hoặc kiểm tra hình ảnh.', true); return; }
  if (!force && !pendingSubmission) {
    const blank = [...states.values()].filter(isBlank).length;
    submitting = true;
    const confirmed = await window.sunnyDialog.confirm(blank
      ? `Em chưa hoàn thành toàn bộ bài tập (còn ${blank} câu chưa trả lời). Em có muốn nộp bài không? Sau khi nộp, em sẽ không thể sửa lại.`
      : 'Em sẽ không sửa được sau khi nộp. Nộp bài nhé?');
    submitting = false;
    if (!confirmed) return;
  }
  submitting = true;
  submitButton.disabled = true;
  lockAnswers(true);
  try {
    if (!pendingSubmission) {
      await flushVisibility();
      await flushSaves();
      if (!globalThis.crypto?.randomUUID) throw new Error('Trình duyệt chưa hỗ trợ nộp bài an toàn. Em hãy dùng trình duyệt mới hơn.');
      pendingSubmission = {key: crypto.randomUUID(), body: JSON.stringify({expected_attempt_revision: attemptRevision})};
    }
    status.textContent = 'Đang nộp…';
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    let response;
    try {
      response = await fetch(`${api}submit/`, {
      method: 'POST', credentials: 'same-origin', signal: controller.signal,
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf, 'Idempotency-Key': pendingSubmission.key},
      body: pendingSubmission.body
      });
    } finally { clearTimeout(timeout); }
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      if ([400, 403, 404, 409, 422].includes(response.status)) {
        if (response.status === 409) requiresReload = true;
        pendingSubmission = null;
        lockAnswers(false);
      }
      throw new Error(requiresReload ? 'Bài đã thay đổi. Hãy tải lại trang và kiểm tra câu trả lời trước khi nộp.' : (payload.error?.message || 'Chưa xác nhận được bài đã nộp. Em hãy thử nộp lại.'));
    }
    if (!payload.data?.submitted_at) throw new Error('Chưa xác nhận được bài đã nộp. Em hãy thử nộp lại.');
    pendingSubmission = null;
    visibilityActive = false;
    practiceEditable = false;
    cleanupFullscreen();
    try { sessionStorage.removeItem(visibilityKey); } catch {}
    status.textContent = 'Đã nộp';
    submitButton.hidden = true;
    retry.hidden = true;
    const submittedText = `Đã nộp lúc ${new Date(payload.data.submitted_at).toLocaleString('vi-VN')}.`;
    if (receipt && receiptText) {
      receiptText.textContent = submittedText;
      receipt.hidden = false;
      root.dataset.gameEnabled = 'false';
      document.body.classList.remove('is-pirate-game-mode');
      practiceNavigation.hidden = true;
      if (root.dataset.mode === 'PRACTICE') form.hidden = true;
    } else {
      notify(submittedText);
    }
    return;
  } catch (err) {
    if (!pendingSubmission) lockAnswers(false);
    notify(err.message || 'Chưa xác nhận được bài đã nộp. Em hãy thử nộp lại.', true);
    if (pendingSubmission) {
      submitButton.textContent = 'Thử nộp lại';
      status.textContent = 'Chưa xác nhận nộp';
    } else {
      submitButton.textContent = 'Nộp bài';
      updateStatus();
    }
  } finally {
    submitting = false;
    if (!submitButton.hidden) submitButton.disabled = requiresReload;
  }
}

submitButton.addEventListener('click', () => doSubmit(false));
