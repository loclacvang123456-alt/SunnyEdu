(() => {
  'use strict';
  const root = document.querySelector('#pronunciation-practice');
  if (!root) return;
  const form = document.querySelector('#pronunciation-form');
  const input = document.querySelector('#pronunciation-reference');
  const consent = document.querySelector('#pronunciation-consent');
  const record = document.querySelector('#pronunciation-record');
  const stop = document.querySelector('#pronunciation-stop');
  const send = document.querySelector('#pronunciation-send');
  const status = document.querySelector('#pronunciation-status');
  const result = document.querySelector('#pronunciation-result');
  const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
  let context = null, stream = null, processor = null, source = null, silentGain = null;
  let chunks = [], samples = 0, timer = null, wav = null, recordingReference = '', recordingConsent = false;
  const notify = text => { status.textContent = text; };
  const prompts = ['Hello, how are you?', 'I love my family.', 'The cat is under the table.', 'What is your favorite color?', 'I would like an apple.', 'Today is a beautiful day.'];
  let promptIndex = 0;
  const nextPrompt = document.querySelector('#speaking-next');
  const listen = document.querySelector('#speaking-listen');
  nextPrompt.addEventListener('click', () => {
    promptIndex = (promptIndex + 1) % prompts.length;
    input.value = prompts[promptIndex];
    input.dispatchEvent(new Event('input'));
  });
  listen.addEventListener('click', () => {
    const text = input.value.trim();
    if (!text) { notify('Em hãy chọn hoặc nhập một câu trước nhé.'); return; }
    if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) { notify('Trình duyệt chưa hỗ trợ đọc mẫu.'); return; }
    const voices = speechSynthesis.getVoices();
    const voice = voices.find(item => /^en-US/i.test(item.lang)) || voices.find(item => /^en(-|_)/i.test(item.lang));
    if (!voice) { notify('Thiết bị chưa có giọng tiếng Anh để đọc mẫu.'); return; }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = voice.lang; utterance.voice = voice; utterance.rate = 0.85;
    utterance.onerror = () => notify('Chưa phát được giọng đọc mẫu. Em hãy thử lại.');
    speechSynthesis.cancel(); speechSynthesis.speak(utterance);
  });
  if (root.dataset.available !== 'yes') return;
  input.addEventListener('input', () => {
    if (!wav) return;
    wav = null; recordingConsent = false; consent.checked = false; send.disabled = true;
    result.replaceChildren(); record.textContent = 'Bắt đầu ghi âm';
    notify('Câu đã thay đổi. Em hãy xác nhận và ghi âm lại nhé.');
  });

  function release() {
    clearTimeout(timer); timer = null;
    if (processor) { processor.onaudioprocess = null; processor.disconnect(); processor = null; }
    if (source) { source.disconnect(); source = null; }
    if (silentGain) { silentGain.disconnect(); silentGain = null; }
    if (stream) { stream.getTracks().forEach(track => track.stop()); stream = null; }
    if (context) { context.close().catch(() => {}); context = null; }
  }

  function toWav(inputSamples, sourceRate) {
    const outputCount = Math.floor(inputSamples.length * 16000 / sourceRate);
    if (sourceRate < 16000 || outputCount < 1) throw new Error('Thiết bị không hỗ trợ định dạng ghi âm cần thiết.');
    const buffer = new ArrayBuffer(44 + outputCount * 2);
    const view = new DataView(buffer);
    const write = (at, text) => [...text].forEach((char, i) => view.setUint8(at + i, char.charCodeAt(0)));
    write(0, 'RIFF'); view.setUint32(4, 36 + outputCount * 2, true); write(8, 'WAVE');
    write(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
    view.setUint16(22, 1, true); view.setUint32(24, 16000, true); view.setUint32(28, 32000, true);
    view.setUint16(32, 2, true); view.setUint16(34, 16, true); write(36, 'data'); view.setUint32(40, outputCount * 2, true);
    // Average source samples over each destination interval before quantizing to PCM16.
    for (let i = 0; i < outputCount; i++) {
      const begin = Math.floor(i * sourceRate / 16000);
      const end = Math.max(begin + 1, Math.floor((i + 1) * sourceRate / 16000));
      let sum = 0;
      for (let j = begin; j < end; j++) sum += inputSamples[j];
      const value = Math.max(-1, Math.min(1, sum / (end - begin)));
      view.setInt16(44 + i * 2, value < 0 ? Math.round(value * 32768) : Math.round(value * 32767), true);
    }
    return new Blob([buffer], {type: 'audio/wav'});
  }

  function finish() {
    if (!context) return;
    const rate = context.sampleRate;
    const joined = new Float32Array(samples);
    let pos = 0;
    for (const chunk of chunks) { joined.set(chunk, pos); pos += chunk.length; }
    release(); chunks = []; samples = 0;
    record.disabled = false; stop.disabled = true; input.disabled = false; nextPrompt.disabled = false;
    try {
      wav = toWav(joined, rate);
      send.disabled = false;
      notify('Đã ghi âm. Em có thể gửi hoặc ghi lại.');
      record.textContent = 'Ghi lại';
    } catch (error) { wav = null; send.disabled = true; notify(error.message); }
  }

  record.addEventListener('click', async () => {
    if (wav) {
      wav = null; recordingConsent = false; send.disabled = true; consent.checked = false;
      result.replaceChildren(); notify('Hãy xác nhận đồng ý cho bản ghi mới.');
      return;
    }
    const text = input.value.trim();
    if (!/^[A-Za-z][A-Za-z\s.,!?'-]{0,199}$/.test(text)) { notify('Hãy nhập từ hoặc câu mẫu tiếng Anh hợp lệ.'); return; }
    if (!consent.checked) { notify('Hãy xác nhận đồng ý cho bản ghi này.'); return; }
    if (!navigator.mediaDevices?.getUserMedia || !(window.AudioContext || window.webkitAudioContext)) {
      notify('Trình duyệt này chưa hỗ trợ ghi âm. Hãy thử trình duyệt khác.'); return;
    }
    record.disabled = true; send.disabled = true; result.replaceChildren();
    try {
      stream = await navigator.mediaDevices.getUserMedia({audio: {channelCount: 1}});
      context = new (window.AudioContext || window.webkitAudioContext)();
      if (context.sampleRate < 16000) throw new Error('Thiết bị không hỗ trợ tần số ghi âm cần thiết.');
      source = context.createMediaStreamSource(stream);
      processor = context.createScriptProcessor(4096, 1, 1);
      silentGain = context.createGain(); silentGain.gain.value = 0;
      recordingReference = text; recordingConsent = true; chunks = []; samples = 0;
      input.disabled = true; nextPrompt.disabled = true;
      processor.onaudioprocess = event => {
        const channel = event.inputBuffer.getChannelData(0);
        const remaining = Math.max(0, Math.floor(context.sampleRate * 15) - samples);
        const chunk = channel.slice(0, remaining);
        chunks.push(chunk); samples += chunk.length;
        if (remaining <= channel.length) finish();
      };
      source.connect(processor); processor.connect(silentGain); silentGain.connect(context.destination);
      await context.resume();
      stop.disabled = false; notify('Đang ghi âm. Tối đa 15 giây.');
      timer = setTimeout(finish, 15000);
    } catch (error) {
      release(); recordingConsent = false; record.disabled = false; stop.disabled = true; input.disabled = false; nextPrompt.disabled = false;
      notify(error.message || 'Không thể mở micro. Hãy kiểm tra quyền truy cập.');
    }
  });
  stop.addEventListener('click', finish);
  window.addEventListener('pagehide', () => { release(); wav = null; chunks = []; });

  function add(parent, tag, text) {
    const el = document.createElement(tag); el.textContent = text; parent.append(el); return el;
  }
  function scoreItem(parent, text, needsPractice) {
    const el = add(parent, needsPractice ? 'mark' : 'span', text);
    if (needsPractice) { el.style.color = '#991b1b'; el.style.background = '#fee2e2'; }
    return el;
  }
  function showFeedback(data) {
    result.replaceChildren();
    if (!data.recognition) { add(result, 'p', 'Chưa nhận diện được lời nói. Em hãy ghi lại ở nơi yên tĩnh.'); return; }
    add(result, 'h2', 'Gợi ý phát âm');
    add(result, 'p', 'Từ hoặc âm màu đỏ có thể cần luyện thêm. Giáo viên sẽ đánh giá.');
    const list = document.createElement('ul'); result.append(list);
    const threshold = data.threshold;
    for (const word of data.words || []) {
      const item = document.createElement('li'); list.append(item);
      const weak = (word.score !== null && word.score < threshold) || word.error_type === 'Omission' || word.error_type === 'Mispronunciation';
      scoreItem(item, word.word, weak);
      add(item, 'span', word.score === null ? ' (chưa có điểm âm)' : ` (${word.score}/100)`);
      if (word.error_type === 'Omission') add(item, 'span', ' — có thể bỏ sót');
      if (word.error_type === 'Insertion') add(item, 'span', ' — từ được nhận diện thêm');
      const phones = word.phonemes || [];
      if (phones.length) {
        const line = document.createElement('div'); item.append(line); add(line, 'span', 'Âm IPA tham khảo: /');
        phones.forEach((phone, i) => { if (i) add(line, 'span', ' '); scoreItem(line, phone.ipa, phone.score !== null && phone.score < threshold); });
        add(line, 'span', '/');
      } else add(item, 'div', 'Chưa có thông tin âm IPA cho từ này.');
    }
    add(result, 'p', 'Chữ cái và âm không phải lúc nào cũng tương ứng một-một; âm IPA chỉ giúp em biết âm nào cần luyện.');
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!wav || !recordingConsent || !consent.checked) { notify('Hãy xác nhận và ghi âm trước khi gửi.'); return; }
    if (input.value.trim() !== recordingReference) { notify('Câu mẫu đã thay đổi. Hãy ghi âm lại cho câu mới.'); return; }
    const payload = new FormData(); payload.set('reference', recordingReference); payload.set('consent', 'yes');
    payload.set('audio', wav, 'practice.wav');
    record.disabled = true; send.disabled = true; input.disabled = true; nextPrompt.disabled = true;
    const controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      notify('Đang gửi bản ghi để kiểm tra…');
      const response = await fetch(root.dataset.endpoint, {method: 'POST', credentials: 'same-origin', headers: {'X-CSRFToken': csrf}, body: payload, signal: controller.signal});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || 'Chưa thể kiểm tra phát âm.');
      showFeedback(data.data); notify('Đã có kết quả gợi ý.');
      wav = null; recordingConsent = false; consent.checked = false; record.textContent = 'Ghi âm lại';
    } catch (error) { notify(error.name === 'AbortError' ? 'Kiểm tra mất quá lâu. Em có thể thử gửi lại.' : (error.message || 'Chưa thể kiểm tra phát âm.')); }
    finally { clearTimeout(timeout); record.disabled = false; send.disabled = !wav; input.disabled = false; nextPrompt.disabled = false; }
  });
})();
