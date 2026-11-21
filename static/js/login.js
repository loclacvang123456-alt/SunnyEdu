(() => {
  const form = document.querySelector('#student-login');
  if (!form) return;
  const code = form.querySelector('#code');
  const toggle = document.querySelector('#toggle-code');
  const error = document.querySelector('#login-error');
  const submit = form.querySelector('[type="submit"]');
  const initialHtml = submit.innerHTML;
  const fragment = new URLSearchParams(location.hash.slice(1));
  if (fragment.has('code')) { code.value = fragment.get('code'); history.replaceState(null, '', location.pathname + location.search); }
  toggle.addEventListener('click', () => { const show = code.type === 'password'; code.type = show ? 'text' : 'password'; toggle.textContent = show ? 'Ẩn' : 'Hiện'; toggle.setAttribute('aria-pressed', String(show)); });
  form.addEventListener('submit', async event => {
    event.preventDefault(); error.hidden = true; submit.disabled = true; submit.textContent = 'Đang vào học…';
    try {
      const response = await fetch(form.action, {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json','X-CSRFToken':form.querySelector('[name=csrfmiddlewaretoken]').value}, body:JSON.stringify({code:code.value, remember_device:form.elements.remember_device.checked})});
      if (response.ok) { const next = form.dataset.next; location.assign(next.startsWith('/') && !next.startsWith('//') ? next : '/student/'); return; }
      const retry = response.headers.get('Retry-After');
      error.textContent = response.status === 429 ? `Em thử lại sau ${retry || 'một lúc'}${retry ? ' giây' : ''} nhé.` : 'Mã chưa đúng hoặc đã được đổi. Em kiểm tra lại hoặc nhờ thầy cô.';
    } catch { error.textContent = 'Chưa kết nối được. Em kiểm tra mạng và thử lại nhé.'; }
    error.hidden = false; submit.disabled = false; submit.innerHTML = initialHtml;
  });
})();
