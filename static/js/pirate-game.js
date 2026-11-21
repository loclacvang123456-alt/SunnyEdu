/* Practice-only scene. The caller enables this only for an authorized exercise. */
const ROOT = '/static/img/game-tau-bien/';
const required = [
  'sea-sky.png', 'sea-water-back.png', 'sea-water-front.png', 'player-deck.png',
  'sailor-back.png', 'cannon-base.png', 'cannon-barrel.png', 'cannonball.png',
  'commander-master.png', 'flag-covered-cloud.png', 'reference/choice-ship-master.png', 'choice-ship-pirate.png',
  'cloud-big-1.png', 'cloud-big-2.png', 'cloud-big-3.png', 'cloud-big-4.png',
];

function create(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function image(name, className) {
  const img = create('img', className);
  img.src = ROOT + name + "?v=8";
  img.alt = '';
  img.draggable = false;
  return img;
}

function load(name) {
  return new Promise(resolve => {
    const img = new Image();
    img.onload = () => resolve(null);
    img.onerror = () => resolve(name);
    img.src = ROOT + name + "?v=8";
  });
}

let assetsPromise;
export function checkPirateGameAssets() {
  if (!assetsPromise) assetsPromise = Promise.all(required.map(load)).then(results => {
    const missing = results.filter(Boolean);
    if (missing.length) assetsPromise = undefined;
    return missing;
  });
  return assetsPromise;
}

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

/**
 * Return {element, ready, hasPending}.
 */
export async function createPirateGame({
  question,
  attemptId,
  csrfToken,
  onRecorded,
  editable = false,
  questionIndex = 0,
  totalQuestions = 1,
  onPrevious,
  onNext,
  onFinish
}) {
  const element = create('section', 'pirate-game');
  const missing = await checkPirateGameAssets();
  if (missing.length) {
    const note = create('p', 'pirate-unavailable', 'Game tàu biển chưa sẵn sàng vì còn thiếu hình minh họa. Em hãy liên hệ giáo viên.');
    note.setAttribute('role', 'status');
    const exit = create('a', 'pirate-exit-btn', '← Thoát');
    exit.href = '/student/';
    element.append(exit, note);
    return {element, ready: false, missing};
  }
  if (!attemptId || !question || question.type !== 'SINGLE_CHOICE' || !Array.isArray(question.options) || question.options.length < 2 || question.options.length > 6) {
    const exit = create('a', 'pirate-exit-btn', '← Thoát');
    exit.href = '/student/';
    element.append(exit, create('p', 'pirate-unavailable', 'Câu hỏi chưa sẵn sàng. Em hãy liên hệ giáo viên.'));
    return {element, ready: false, missing: []};
  }

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const scene = create('div', 'pirate-scene');

  // Exit button in scene
  const exitBtn = create('a', 'pirate-exit-btn', '← Thoát game');
  exitBtn.href = '/student/';
  scene.append(exitBtn);
  if (questionIndex > 0) {
    const previous = create('button', 'pirate-previous-btn', '← Câu trước');
    previous.type = 'button';
    previous.addEventListener('click', () => onPrevious?.());
    scene.append(previous);
  }

  // Background layers
  const sceneArt = create('div', 'pirate-art');
  sceneArt.setAttribute('aria-hidden', 'true');
  sceneArt.append(
    image('sea-sky.png', 'pirate-layer pirate-sky'),
    image('sea-water-back.png', 'pirate-layer pirate-water')
  );

  // Ship choices container
  const choices = create('div', 'pirate-choices');
  choices.setAttribute('role', 'group');
  choices.setAttribute('aria-label', 'Chọn một tàu để bắn');
  const ships = new Map();

  for (const [index, option] of question.options.entries()) {
    const wrap = create('div', 'pirate-choice');
    wrap.setAttribute('role', 'button');
    wrap.setAttribute('tabindex', editable ? '0' : '-1');
    wrap.setAttribute('aria-label', `Chọn đáp án ${String.fromCharCode(65 + index)}: ${option.content}`);

    const vessel = create('div', 'pirate-vessel');
    const body = create('div', 'pirate-vessel-body');
    const shipArt = image('reference/choice-ship-master.png', 'pirate-ship-part');
    body.append(shipArt);

    // Large fluffy cloud with centered letter and answer text
    const cloudWrap = create('div', 'pirate-cloud-wrap');
    const cloudImg = image(`cloud-big-${(index % 4) + 1}.png`, 'pirate-cloud-img');
    const cloudContent = create('div', 'pirate-cloud-content');
    const marker = create('span', 'pirate-marker', String.fromCharCode(65 + index));
    const optionText = create('span', 'pirate-option-text', option.content);
    cloudContent.append(marker, optionText);
    cloudWrap.append(cloudImg, cloudContent);

    const explosion = create('span', 'pirate-explosion', 'BÙM!');
    explosion.hidden = true;

    body.append(cloudWrap);
    vessel.append(body, explosion);
    wrap.append(vessel);
    choices.append(wrap);

    ships.set(String(option.id), {wrap, vessel, body, shipArt, cloudWrap, explosion, option});
  }

  // Foreground layers: water front, newly shifted deck, sailor, cannon, commander, cannonball
  sceneArt.append(
    image('sea-water-front.png', 'pirate-layer pirate-front-water'),
    image('player-deck.png', 'pirate-layer pirate-deck'),
    image('sailor-back.png', 'pirate-sailor')
  );

  const cannon = create('div', 'pirate-cannon');
  cannon.append(
    image('cannon-base.png', 'pirate-cannon-part'),
    image('cannon-barrel.png', 'pirate-cannon-part')
  );

  const cannonball = image('cannonball.png', 'pirate-ball');
  cannonball.hidden = true;

  const commander = image('commander-master.png', 'pirate-commander');
  sceneArt.append(cannon, commander, cannonball);
  scene.append(sceneArt, choices);

  // Speech bubble on commander
  const speechBubble = create('div', 'pirate-speech-bubble');
  const bubbleQNum = create('div', 'pirate-bubble-qnum', `CÂU ${question.position || (questionIndex + 1)}`);
  const bubblePrompt = create('div', 'pirate-bubble-prompt', question.prompt);
  const bubbleFeedback = create('div', 'pirate-bubble-feedback');
  bubbleFeedback.hidden = true;
  const bubbleAction = create('div', 'pirate-bubble-action');
  bubbleAction.hidden = true;
  speechBubble.append(bubbleQNum, bubblePrompt, bubbleFeedback, bubbleAction);
  scene.append(speechBubble);

  const feedback = create('p', 'pirate-feedback');
  feedback.setAttribute('role', 'status');
  feedback.setAttribute('aria-live', 'polite');
  const retry = create('button', 'button secondary pirate-retry', 'Thử gửi lại');
  retry.type = 'button';
  retry.hidden = true;
  element.append(scene, feedback);

  function showRetry() {
    retry.hidden = false;
    bubbleAction.hidden = false;
    bubbleAction.replaceChildren(retry);
  }

  let pending = null;
  let isSending = false;
  let finished = false;

  const freeze = () => {
    for (const ship of ships.values()) {
      ship.wrap.style.pointerEvents = 'none';
      ship.wrap.classList.add('is-disabled');
    }
  };

  function triggerCelebrationVFX(targetShip) {
    const container = create('div', 'pirate-confetti-container');
    const colors = ['#f59e0b', '#ef4444', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899', '#fbbf24', '#06b6d4'];
    const rect = targetShip.wrap.getBoundingClientRect();
    const sceneRect = scene.getBoundingClientRect();
    const originX = rect.left + rect.width / 2 - sceneRect.left;
    const originY = rect.top + rect.height / 2 - sceneRect.top;

    for (let i = 0; i < 48; i++) {
      const p = create('div', 'pirate-confetti-piece');
      const color = colors[i % colors.length];
      p.style.backgroundColor = color;
      p.style.left = `${originX}px`;
      p.style.top = `${originY}px`;
      const angle = (Math.PI * 2 * i) / 48 + (Math.random() * 0.3 - 0.15);
      const velocity = 80 + Math.random() * 240;
      const destX = Math.cos(angle) * velocity;
      const destY = Math.sin(angle) * velocity - 140;
      const rot = Math.random() * 720 - 360;
      const scale = 0.6 + Math.random() * 0.7;
      p.style.setProperty('--dx', `${destX}px`);
      p.style.setProperty('--dy', `${destY + 220}px`);
      p.style.setProperty('--rot', `${rot}deg`);
      p.style.setProperty('--scale', `${scale}`);
      p.style.animationDuration = `${1.2 + Math.random() * 0.8}s`;
      container.append(p);
    }
    scene.append(container);
    setTimeout(() => container.remove(), 2500);
  }

  function triggerMistakeVFX(targetShip) {
    const container = create('div', 'pirate-mistake-container');
    const splash = create('div', 'pirate-splash-ring', '💦');
    const smoke = create('div', 'pirate-smoke-puff', '💨');
    container.append(splash, smoke);
    targetShip.vessel.append(container);
    setTimeout(() => container.remove(), 2000);
  }

  async function showResult(receipt, animate) {
    const ship = ships.get(String(receipt.option_id));
    if (!ship || typeof receipt.correct !== 'boolean') throw new Error('Kết quả không hợp lệ.');
    freeze();
    finished = true;
    retry.hidden = true;

    const showResultLabel = () => {
      if (receipt.correct) {
        ship.shipArt.src = ROOT + 'choice-ship-pirate.png?v=8';
      }
      ship.cloudWrap.hidden = true;
      ship.wrap.classList.add('is-selected');
      if (receipt.correct) {
        if (animate) {
          triggerCelebrationVFX(ship);
          commander.classList.add('is-cheering');
          setTimeout(() => commander.classList.remove('is-cheering'), 1800);
        }
      } else {
        ship.wrap.classList.add('is-mistake');
        if (animate) {
          triggerMistakeVFX(ship);
          commander.classList.add('is-oops');
          setTimeout(() => commander.classList.remove('is-oops'), 1800);
        }
      }

      // Update commander's speech bubble with clear, fun feedback
      bubbleFeedback.hidden = false;
      bubbleFeedback.textContent = receipt.correct
        ? '🎉 Đúng rồi! Em đã bắn trúng thuyền hải tặc!'
        : '😅 Ồ chưa đúng! Đây là thuyền của phe mình!';
      bubbleFeedback.className = `pirate-bubble-feedback ${receipt.correct ? 'is-correct' : 'is-incorrect'}`;

      bubbleAction.hidden = false;
      bubbleAction.replaceChildren();

      if (questionIndex < totalQuestions - 1) {
        const nextButton = create('button', 'pirate-next-btn', 'Câu tiếp theo ➔');
        nextButton.type = 'button';
        nextButton.onclick = () => onNext?.();
        bubbleAction.append(nextButton);
      } else if (editable) {
        const finish = create('button', 'pirate-next-btn', 'Nộp bài');
        finish.type = 'button';
        finish.addEventListener('click', () => onFinish?.());
        bubbleAction.append(finish);
      } else {
        const exitAction = create('a', 'pirate-next-btn', '← Về bài của em');
        exitAction.href = '/student/';
        bubbleAction.append(exitAction);
      }
    };

    if (!animate || reduced.matches) {
      showResultLabel();
      return;
    }

    bubbleFeedback.hidden = false;
    bubbleFeedback.textContent = 'Pháo đang nhắm bắn… 🎯';
    bubbleFeedback.className = 'pirate-bubble-feedback is-aiming';

    const sceneRect = sceneArt.getBoundingClientRect();
    const muzzle = cannon.getBoundingClientRect();
    const target = ship.wrap.getBoundingClientRect();
    const startX = muzzle.left + muzzle.width * .5 - sceneRect.left;
    const startY = muzzle.top + muzzle.height * .2 - sceneRect.top;
    const endX = target.left + target.width * .5 - sceneRect.left;
    const endY = target.top + target.height * .42 - sceneRect.top;

    cannonball.hidden = false;
    cannonball.style.left = `${startX}px`;
    cannonball.style.top = `${startY}px`;

    if (typeof cannonball.animate === 'function') {
      await cannonball.animate([
        {transform: 'translate(-50%, -50%) scale(1)'},
        {transform: `translate(calc(-50% + ${endX - startX}px), calc(-50% + ${endY - startY}px)) scale(.35)`}
      ], {duration: 700, easing: 'ease-out'}).finished.catch(() => {});
    } else {
      await delay(700);
    }

    cannonball.hidden = true;
    if (receipt.correct) {
      ship.shipArt.src = ROOT + 'choice-ship-pirate.png?v=8';
    }
    ship.explosion.hidden = false;
    await delay(650);
    ship.explosion.hidden = true;
    showResultLabel();
  }

  async function send() {
    if (!pending || isSending || finished) return;
    isSending = true;
    freeze();
    retry.hidden = true;
    bubbleFeedback.hidden = false;
    bubbleFeedback.textContent = 'Đang chuẩn bị bắn pháo…';
    bubbleFeedback.className = 'pirate-bubble-feedback is-aiming';

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(`/api/v1/attempts/${encodeURIComponent(attemptId)}/responses/${encodeURIComponent(question.question_id)}/shot/`, {
        method: 'POST', credentials: 'same-origin', signal: controller.signal,
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken, 'Idempotency-Key': pending.key},
        body: pending.body,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        if ([400, 403, 404, 409, 422].includes(response.status)) {
          pending = null;
          bubbleFeedback.textContent = payload.error?.message || 'Không thể xác nhận lựa chọn.';
          bubbleFeedback.className = 'pirate-bubble-feedback is-incorrect';
        } else {
          showRetry();
          bubbleFeedback.textContent = 'Chưa lưu được. Em hãy thử lại.';
          bubbleFeedback.className = 'pirate-bubble-feedback is-incorrect';
        }
        return;
      }
      const receipt = payload.data;
      if (!receipt || String(receipt.option_id) !== pending.optionId || typeof receipt.correct !== 'boolean' || !Number.isInteger(receipt.response_revision) || !Number.isInteger(receipt.attempt_revision)) {
        showRetry();
        bubbleFeedback.textContent = 'Chưa lưu được. Em hãy thử lại.';
        bubbleFeedback.className = 'pirate-bubble-feedback is-incorrect';
        return;
      }
      pending = null;
      onRecorded?.(receipt);
      await showResult(receipt, true);
    } catch (_) {
      showRetry();
      bubbleFeedback.textContent = 'Chưa kết nối được máy chủ.';
      bubbleFeedback.className = 'pirate-bubble-feedback is-incorrect';
    } finally {
      clearTimeout(timeout);
      isSending = false;
    }
  }

  for (const [id, ship] of ships) {
    const trigger = () => {
      if (pending || isSending || finished || !editable) return;
      if (!globalThis.crypto?.randomUUID) {
        bubbleFeedback.hidden = false;
        bubbleFeedback.textContent = 'Trình duyệt chưa hỗ trợ.';
        return;
      }
      pending = {key: crypto.randomUUID(), optionId: id, body: JSON.stringify({option_id: id, expected_revision: question.response_revision})};
      send();
    };

    ship.wrap.addEventListener('click', trigger);
    ship.wrap.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        trigger();
      }
    });
  }

  retry.addEventListener('click', send);

  if (question.shot) {
    await showResult(question.shot, false);
  } else if (!editable) {
    freeze();
    bubbleFeedback.hidden = false;
    bubbleFeedback.textContent = 'Bài này đã kết thúc.';
    bubbleFeedback.className = 'pirate-bubble-feedback';
  }

  return {element, ready: true, hasPending: () => Boolean(pending || isSending)};
}
