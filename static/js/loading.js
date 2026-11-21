(() => {
  const topup = document.getElementById('sunny-topup');
  if (topup) {
    const syncTopup = () => { topup.hidden = window.scrollY < 240; };
    window.addEventListener('scroll', syncTopup, { passive: true });
    syncTopup();
    topup.addEventListener('click', () => {
      const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
      window.scrollTo({ top: 0, behavior });
    });
  }
  const overlay = document.getElementById('sunny-loading');
  if (!overlay) return;
  let pending = 0;
  let navigating = false;
  let delay;
  let fallback;
  function show() {
    overlay.hidden = false;
    clearTimeout(fallback);
    fallback = setTimeout(hide, navigating ? 4000 : 20000);
  }
  function hide() {
    clearTimeout(delay);
    clearTimeout(fallback);
    navigating = false;
    overlay.hidden = true;
  }
  window.addEventListener('pageshow', hide);
  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('a[href]');
    if (!link || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
    const target = new URL(link.href, location.href);
    if (target.origin !== location.origin || !/^https?:$/.test(target.protocol)) return;
    if (target.pathname === location.pathname && target.search === location.search) return;
    navigating = true;
    show();
  });
  document.addEventListener('submit', event => {
    const form = event.target;
    if (!event.defaultPrevented && (!form.target || form.target === '_self')) { navigating = true; show(); }
  });
  const originalFetch = window.fetch;
  window.fetch = function(input, options) {
    const url = new URL(input instanceof Request ? input.url : input, location.href);
    // Answer autosaves and game shots already have inline feedback and must not interrupt typing.
    if (url.origin !== location.origin || url.pathname.includes('/responses/')) return originalFetch.call(this, input, options);
    pending++;
    if (pending === 1) delay = setTimeout(show, 300);
    return originalFetch.call(this, input, options).finally(() => {
      pending--;
      if (!pending && !navigating) hide();
    });
  };
})();
