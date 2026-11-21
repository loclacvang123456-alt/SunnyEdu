/* Explanations for common teacher-defined error labels. */
(() => {
  const known = {
    'pronunciation': 'Phát âm: dùng khi học sinh phát âm sai âm, từ hoặc cách nhấn trong bài nói.',
    'phát âm': 'Phát âm: dùng khi học sinh phát âm sai âm, từ hoặc cách nhấn trong bài nói.',
    'fluency': 'Độ trôi chảy: dùng khi học sinh nói ngập ngừng hoặc ngắt quãng nhiều.',
    'độ trôi chảy': 'Độ trôi chảy: dùng khi học sinh nói ngập ngừng hoặc ngắt quãng nhiều.',
    'grammar': 'Ngữ pháp: dùng khi câu dùng sai cấu trúc hoặc quy tắc ngữ pháp.',
    'ngữ pháp': 'Ngữ pháp: dùng khi câu dùng sai cấu trúc hoặc quy tắc ngữ pháp.',
    'chia động từ': 'Chia động từ: dùng khi động từ chưa phù hợp với chủ ngữ hoặc thì của câu.',
    'verb tense': 'Thì động từ: dùng khi học sinh chọn thì không phù hợp với ngữ cảnh.',
    'thì động từ': 'Thì động từ: dùng khi học sinh chọn thì không phù hợp với ngữ cảnh.',
    'spelling': 'Chính tả: dùng khi học sinh viết sai chữ trong một từ.',
    'chính tả': 'Chính tả: dùng khi học sinh viết sai chữ trong một từ.',
    'vocabulary': 'Từ vựng: dùng khi học sinh chọn hoặc dùng từ chưa phù hợp với ý muốn diễn đạt.',
    'từ vựng': 'Từ vựng: dùng khi học sinh chọn hoặc dùng từ chưa phù hợp với ý muốn diễn đạt.',
    'word order': 'Trật tự từ: dùng khi các từ được sắp xếp sai thứ tự trong câu.',
    'trật tự từ': 'Trật tự từ: dùng khi các từ được sắp xếp sai thứ tự trong câu.',
    'word stress': 'Trọng âm: dùng khi học sinh xác định hoặc phát âm sai âm tiết được nhấn.',
    'trọng âm': 'Trọng âm: dùng khi học sinh xác định hoặc phát âm sai âm tiết được nhấn.',
    'punctuation': 'Dấu câu: dùng khi học sinh dùng dấu câu chưa phù hợp.',
    'dấu câu': 'Dấu câu: dùng khi học sinh dùng dấu câu chưa phù hợp.',
    'reading comprehension': 'Đọc hiểu: dùng khi câu trả lời cho thấy học sinh chưa hiểu nội dung đoạn đọc.',
    'đọc hiểu': 'Đọc hiểu: dùng khi câu trả lời cho thấy học sinh chưa hiểu nội dung đoạn đọc.',
    'listening comprehension': 'Nghe hiểu: dùng khi câu trả lời cho thấy học sinh chưa hiểu nội dung bài nghe.',
    'nghe hiểu': 'Nghe hiểu: dùng khi câu trả lời cho thấy học sinh chưa hiểu nội dung bài nghe.'
  };
  const general = 'Nhãn lỗi giúp phân loại khó khăn để theo dõi trong báo cáo. Khi tạo câu hỏi, gắn nhãn cho lỗi câu đó có thể kiểm tra; khi chấm, chọn nhãn phù hợp với lỗi thực tế của học sinh. Nhãn tự động chỉ là dấu hiệu cần giáo viên kiểm tra.';
  const explain = name => {
    const text = (name || '').trim();
    if (!text) return general;
    return known[text.toLocaleLowerCase('vi')] || `“${text}” là nhãn do giáo viên đặt. Dùng khi lỗi thực tế của học sinh phù hợp với ý nghĩa mà giáo viên quy ước cho nhãn này; nhãn được tổng hợp trong báo cáo.`;
  };
  let bubble, active;
  function hide() {
    if (active) active.setAttribute('aria-expanded', 'false');
    active = null;
    if (bubble) bubble.hidden = true;
  }
  function show(button, target) {
    if (!bubble) {
      bubble = document.createElement('div');
      bubble.className = 'error-help-bubble';
      bubble.id = 'error-help-bubble';
      bubble.setAttribute('role', 'tooltip');
      document.body.append(bubble);
    }
    if (active && active !== button) active.setAttribute('aria-expanded', 'false');
    active = button;
    button.setAttribute('aria-expanded', 'true');
    bubble.textContent = explain(target.dataset.errorHelp);
    bubble.hidden = false;
    const rect = button.getBoundingClientRect();
    const width = Math.min(320, window.innerWidth - 24);
    bubble.style.width = `${width}px`;
    bubble.style.left = `${Math.max(12, Math.min(rect.left + rect.width / 2 - width / 2, window.innerWidth - width - 12))}px`;
    const above = rect.top - bubble.offsetHeight - 10;
    bubble.style.top = `${above >= 12 ? above : Math.min(rect.bottom + 10, window.innerHeight - bubble.offsetHeight - 12)}px`;
  }
  function enhance(root) {
    const targets = [];
    if (root.matches?.('[data-error-help]')) targets.push(root);
    root.querySelectorAll?.('[data-error-help]').forEach(node => targets.push(node));
    targets.forEach(target => {
      if (target.dataset.errorHelpReady) return;
      target.dataset.errorHelpReady = '1';
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'error-help-trigger';
      button.textContent = '?';
      button.setAttribute('aria-label', 'Giải thích nhãn lỗi');
      button.setAttribute('aria-describedby', 'error-help-bubble');
      button.setAttribute('aria-expanded', 'false');
      target.insertAdjacentElement('afterend', button);
      button.addEventListener('mouseenter', () => show(button, target));
      button.addEventListener('mouseleave', () => { if (document.activeElement !== button) hide(); });
      button.addEventListener('focus', () => show(button, target));
      button.addEventListener('blur', hide);
      button.addEventListener('click', () => show(button, target));
    });
  }
  document.addEventListener('DOMContentLoaded', () => {
    enhance(document);
    new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(node => {
      if (node.nodeType === Node.ELEMENT_NODE) enhance(node);
    }))).observe(document.body, {childList: true, subtree: true});
    document.addEventListener('keydown', event => { if (event.key === 'Escape') hide(); });
    document.addEventListener('click', event => { if (active && !active.contains(event.target)) hide(); });
    window.addEventListener('scroll', hide, true);
    window.addEventListener('resize', hide);
  });
})();
