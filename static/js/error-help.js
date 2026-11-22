/* Explanations for common teacher-defined error labels. */
(() => {
  const known = {
    'từ vựng: từ đồng nghĩa': 'Dùng cho câu hỏi tìm từ có nghĩa giống hoặc gần giống nhau. Ví dụ: “important” và “significant”.',
    'từ vựng: từ trái nghĩa': 'Dùng cho câu hỏi tìm từ có nghĩa trái ngược nhau. Ví dụ: “hot” và “cold”.',
    'từ vựng: nghĩa của từ': 'Dùng cho câu hỏi kiểm tra nghĩa của từ tiếng Anh.',
    'từ vựng: nối tranh và từ': 'Dùng cho bài nối hình ảnh với từ tương ứng. Ví dụ: hình con mèo và từ “cat”.',
    'đọc hiểu: thông tin trong bài': 'Dùng khi học sinh cần đọc nội dung bài và tìm thông tin để trả lời câu hỏi.',
    'nghe hiểu: thông tin trong bài': 'Dùng khi học sinh cần nghe và tìm thông tin để trả lời câu hỏi.',
    'ngữ pháp: danh từ số nhiều': 'Dùng cho câu hỏi về danh từ chỉ nhiều người hoặc vật. Ví dụ: “book” và “books”.',
    'ngữ pháp: thì hiện tại đơn': 'Dùng cho câu hỏi về hành động thường xuyên hoặc sự thật ở hiện tại.',
    'ngữ pháp: thì quá khứ đơn': 'Dùng cho câu hỏi về hành động đã xảy ra và kết thúc trong quá khứ.',
    'ngữ pháp: câu bị động': 'Dùng cho câu hỏi về câu bị động, ví dụ “The book was written by Lan”.',
    'ngữ pháp: câu tường thuật': 'Dùng cho câu hỏi chuyển lời nói trực tiếp thành lời kể gián tiếp.',
    'sắp xếp câu: trật tự từ': 'Dùng cho câu hỏi yêu cầu sắp xếp các từ thành câu đúng.',
    'viết lại câu': 'Dùng cho câu hỏi yêu cầu viết lại câu theo yêu cầu của đề.',
    'phát âm: trọng âm của từ': 'Dùng cho câu hỏi chọn âm tiết được nhấn mạnh trong từ.',
    'phát âm: phân biệt âm': 'Dùng cho câu hỏi phân biệt cách phát âm của các từ.',
    'viết: diễn đạt nội dung': 'Đây là bài viết. Đọc câu trả lời trước khi chọn lỗi cụ thể; nhãn này chỉ mô tả dạng bài.',
    'nói: diễn đạt và phát âm': 'Đây là bài nói. Nghe câu trả lời trước khi chọn lỗi cụ thể; nhãn này chỉ mô tả dạng bài.',
    'pronunciation': 'Dùng khi học sinh đọc sai âm hoặc từ. Ví dụ: đọc “ship” thành “sheep”.',
    'phát âm': 'Dùng khi học sinh đọc sai âm hoặc từ. Ví dụ: đọc “ship” thành “sheep”.',
    'fluency': 'Dùng khi học sinh nói còn ngập ngừng hoặc dừng quá nhiều, khiến câu nói chưa liền mạch.',
    'độ trôi chảy': 'Dùng khi học sinh nói còn ngập ngừng hoặc dừng quá nhiều, khiến câu nói chưa liền mạch.',
    'grammar': 'Dùng khi học sinh viết hoặc nói sai cấu trúc câu. Ví dụ: “She go to school” thay vì “She goes to school”.',
    'ngữ pháp': 'Dùng khi học sinh viết hoặc nói sai cấu trúc câu. Ví dụ: “She go to school” thay vì “She goes to school”.',
    'chia động từ': 'Dùng khi học sinh dùng sai dạng động từ. Ví dụ: “She go” thay vì “She goes”.',
    'verb tense': 'Dùng khi học sinh dùng sai thì. Ví dụ: “Yesterday I go” thay vì “Yesterday I went”.',
    'thì động từ': 'Dùng khi học sinh dùng sai thì. Ví dụ: “Yesterday I go” thay vì “Yesterday I went”.',
    'spelling': 'Dùng khi học sinh viết sai chữ trong từ. Ví dụ: “becaus” thay vì “because”.',
    'chính tả': 'Dùng khi học sinh viết sai chữ trong từ. Ví dụ: “becaus” thay vì “because”.',
    'vocabulary': 'Dùng khi học sinh chọn sai từ hoặc dùng từ không đúng nghĩa muốn nói.',
    'từ vựng': 'Dùng khi học sinh chọn sai từ hoặc dùng từ không đúng nghĩa muốn nói.',
    'word order': 'Dùng khi học sinh xếp từ sai thứ tự. Ví dụ: “I English like” thay vì “I like English”.',
    'trật tự từ': 'Dùng khi học sinh xếp từ sai thứ tự. Ví dụ: “I English like” thay vì “I like English”.',
    'word stress': 'Dùng khi học sinh chọn hoặc nhấn sai trọng âm của từ. Ví dụ: từ “teacher” nhấn âm đầu: TEA-cher.',
    'trọng âm': 'Dùng khi học sinh chọn hoặc nhấn sai trọng âm của từ. Ví dụ: từ “teacher” nhấn âm đầu: TEA-cher.',
    'punctuation': 'Dùng khi học sinh dùng sai hoặc thiếu dấu câu, ví dụ thiếu dấu hỏi ở cuối câu hỏi.',
    'dấu câu': 'Dùng khi học sinh dùng sai hoặc thiếu dấu câu, ví dụ thiếu dấu hỏi ở cuối câu hỏi.',
    'reading comprehension': 'Dùng khi học sinh trả lời sai vì chưa hiểu nội dung bài đọc.',
    'đọc hiểu': 'Dùng khi học sinh trả lời sai vì chưa hiểu nội dung bài đọc.',
    'listening comprehension': 'Dùng khi học sinh trả lời sai vì chưa hiểu nội dung bài nghe.',
    'nghe hiểu': 'Dùng khi học sinh trả lời sai vì chưa hiểu nội dung bài nghe.'
  };
  const general = 'Nhãn lỗi giúp ghi lại học sinh thường sai ở đâu. Ví dụ: chọn “Chia động từ” khi học sinh viết “She go” thay vì “She goes”. Khi soạn câu hỏi, có thể thêm nhãn để phân loại nội dung; khi chấm bài, gắn nhãn nếu học sinh thực sự mắc lỗi đó. Xem báo cáo để theo dõi các lỗi thường gặp.';
  const explain = name => {
    const text = (name || '').trim();
    if (!text) return general;
    return known[text.toLocaleLowerCase('vi')] || `“${text}” là nhãn dùng để phân loại. Nếu đây là gợi ý theo câu hỏi, hãy xem bài làm trước khi gắn nhãn cho học sinh. Nội dung chi tiết của nhãn này chưa được mô tả.`;
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
    bubble.textContent = target.dataset.errorHelpText || explain(target.dataset.errorHelp);
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
      target.insertAdjacentElement('beforebegin', button);
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
