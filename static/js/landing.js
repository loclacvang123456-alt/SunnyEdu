(() => {
  const region = document.querySelector('[data-slider-region]') || document;
  const slider = region.querySelector('[data-slider]');
  if (!slider) return;
  const slides = [...slider.querySelectorAll('[data-slide]')];
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let current = 0;
  let moving = false;

  async function show(direction) {
    if (moving || slides.length < 2) return;
    const next = (current + direction + slides.length) % slides.length;
    const outgoing = slides[current];
    const incoming = slides[next];
    if (!incoming || !outgoing) return;
    moving = true;
    incoming.hidden = false;
    outgoing.inert = true;

    try {
      if (!reducedMotion.matches && typeof incoming.animate === 'function') {
        const options = {duration: 850, easing: 'ease-in-out', fill: 'both'};
        const animations = [
          outgoing.animate([{transform: 'translateX(0)'}, {transform: `translateX(${-direction * 100}%)`}], options),
          incoming.animate([{transform: `translateX(${direction * 100}%)`}, {transform: 'translateX(0)'}], options),
        ];
        await Promise.all(animations.map(animation => animation.finished.catch(() => {})));
        outgoing.hidden = true;
        animations.forEach(animation => animation.cancel());
      } else {
        outgoing.hidden = true;
      }
      current = next;
    } finally {
      slides.forEach((slide, i) => { slide.hidden = i !== current; slide.inert = false; });
      moving = false;
    }
  }

  region.querySelector('[data-prev]')?.addEventListener('click', () => show(-1));
  region.querySelector('[data-next]')?.addEventListener('click', () => show(1));

  const controlsWrap = region.querySelector('.slide-controls');
  controlsWrap?.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      show(-1);
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      show(1);
    }
  });

  window.setInterval(() => {
    if (!document.hidden && !reducedMotion.matches && !region.matches(':hover') && !region.contains(document.activeElement)) {
      show(1);
    }
  }, 6000);
})();
