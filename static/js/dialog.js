(() => {
  const dialog = document.createElement('dialog');
  dialog.className = 'sunny-dialog';
  dialog.setAttribute('aria-labelledby', 'sunny-dialog-title');
  dialog.setAttribute('aria-describedby', 'sunny-dialog-message');
  dialog.innerHTML = `<div class="sunny-dialog-content"><img class="sunny-dialog-icon" alt=""><h2 id="sunny-dialog-title"></h2><p id="sunny-dialog-message"></p><input class="sunny-dialog-input" type="text" aria-label="Lý do"><div class="sunny-dialog-actions"><button type="button" class="sunny-dialog-cancel">Hủy</button><button type="button" class="sunny-dialog-ok">Đồng ý</button></div></div>`;
  const icon = dialog.querySelector('img');
  const title = dialog.querySelector('h2');
  const message = dialog.querySelector('p');
  const input = dialog.querySelector('input');
  const cancel = dialog.querySelector('.sunny-dialog-cancel');
  const ok = dialog.querySelector('.sunny-dialog-ok');
  let queue = Promise.resolve();
  function show(text, type) {
    const task = () => new Promise(resolve => {
      const previousFocus = document.activeElement;
      icon.src = type === 'success' ? document.body.dataset.dialogSuccess : document.body.dataset.dialogWarning;
      title.textContent = type === 'success' ? 'Thành công' : 'Lưu ý';
      message.textContent = text;
      input.hidden = type !== 'prompt';
      input.value = '';
      cancel.hidden = type === 'success' || type === 'notice';
      ok.textContent = type === 'confirm' ? 'Xác nhận' : type === 'prompt' ? 'Tiếp tục' : 'Đã hiểu';
      const finish = value => {
        dialog.close();
        previousFocus?.focus();
        resolve(value);
      };
      ok.onclick = () => finish(type === 'prompt' ? input.value : true);
      cancel.onclick = () => finish(type === 'prompt' ? null : false);
      dialog.oncancel = event => { event.preventDefault(); finish(type === 'prompt' ? null : false); };
      input.onkeydown = event => { if (event.key === 'Enter') { event.preventDefault(); ok.click(); } };
      dialog.showModal();
      (type === 'prompt' ? input : ok).focus();
    });
    const result = queue.then(task);
    queue = result.catch(() => {});
    return result;
  }
  window.sunnyDialog = {
    confirm: text => show(text, 'confirm'),
    prompt: text => show(text, 'prompt'),
    success: text => show(text, 'success'),
    notice: text => show(text, 'notice'),
  };
  document.addEventListener('DOMContentLoaded', () => {
    document.body.append(dialog);
    document.querySelectorAll('[data-sunny-message]').forEach(element => {
      const tags = element.dataset.sunnyMessage.split(/\s+/);
      const text = element.textContent.trim();
      if (!text) return;
      element.hidden = true;
      show(text, tags.includes('success') ? 'success' : 'notice');
    });
  });
  const approved = new WeakSet();
  document.addEventListener('submit', async event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.dataset.confirm) return;
    if (approved.has(form)) { approved.delete(form); return; }
    event.preventDefault();
    if (await window.sunnyDialog.confirm(form.dataset.confirm)) {
      approved.add(form);
      form.requestSubmit(event.submitter || undefined);
      approved.delete(form);
    }
  });
})();
