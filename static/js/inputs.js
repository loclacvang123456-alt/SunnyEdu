(() => {
  function enhance(root) {
    root.querySelectorAll('.field-group').forEach(group => {
      if (group.classList.contains('input-group-float')) return;
      const labels = group.querySelectorAll(':scope > label');
      const inputs = group.querySelectorAll(':scope > input');
      if (labels.length !== 1 || inputs.length !== 1) return;
      const input = inputs[0], label = labels[0];
      if (!input.id || label.htmlFor !== input.id || !['text', 'email', 'password', 'tel', 'url'].includes(input.type)) return;
      if (!input.hasAttribute('placeholder')) input.placeholder = ' ';
      group.classList.add('input-group-float');
    });
  }
  document.addEventListener('DOMContentLoaded', () => {
    enhance(document);
    new MutationObserver(records => records.forEach(record => record.addedNodes.forEach(node => {
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      if (node.matches('.field-group')) enhance(node.parentElement);
      else enhance(node);
    }))).observe(document.body, {childList: true, subtree: true});
  });
})();
