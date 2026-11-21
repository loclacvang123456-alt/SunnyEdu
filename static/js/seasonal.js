(() => {
  const root = document.getElementById('seasonal-decor');
  if (!root) return;
  const theme = root.dataset.theme;

  // Add asset filenames here after the illustrations are supplied.
  const assets = {
    christmas: {cornerLeft: 'Image noel 1.png', cornerRight: 'Image noel 4.png', slider: 'Image noel 2.png', login: 'Image noel 3.png'}, 'teachers-day': {cornerLeft: '20-11 1.png'}, halloween: {}, tet: {}, 'mid-autumn': {}
  };
  const selected = assets[theme];
  if (!selected) return;

  function place(parent, slot, filename) {
    if (!parent || !filename) return;
    const image = document.createElement('img');
    image.className = `seasonal-asset seasonal-${slot}`;
    image.alt = '';
    const base = theme === 'christmas' ? root.dataset.christmasRoot
      : theme === 'teachers-day' ? root.dataset.teachersDayRoot
      : `${root.dataset.staticRoot}${theme}/`;
    image.src = `${base}${filename}?v=2`;
    parent.appendChild(image);
  }
  place(root, 'corner-left', selected.cornerLeft);
  place(root, 'corner-right', selected.cornerRight);
  for (const [selector, slot] of [
    ['[data-slider-region]', 'slider'],
    ['.login-card, .owner-auth-card', 'login'],
    ['.student-main .panel, .catalog-main .panel', 'panel']
  ]) {
    if (!selected[slot]) continue;
    document.querySelectorAll(selector).forEach(element => {
      element.classList.add('seasonal-anchor');
      place(element, slot, selected[slot]);
    });
  }

  if (theme === 'teachers-day') {
    const slides = document.querySelectorAll('[data-slider] .hero-img');
    ['20-11 3.png', '200-11 4.png'].forEach((filename, index) => {
      if (slides[index]) slides[index].src = `${root.dataset.teachersDayRoot}${filename}`;
    });
  }

  if ((theme === 'christmas' || theme === 'teachers-day') &&
      !matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const isSnow = theme === 'christmas';
    for (let i = 0; i < (isSnow ? 28 : 20); i++) {
      const particle = document.createElement('span');
      particle.className = isSnow ? 'seasonal-snowflake' : 'seasonal-flower';
      particle.textContent = isSnow ? (i % 3 === 0 ? '\u2726' : '\u2744') : (i % 2 ? '\u273f' : '\u2740');
      particle.style.setProperty('--x', `${(i * 37 + 7) % 100}%`);
      particle.style.setProperty('--size', `${(isSnow ? 18 : 14) + (i * 7) % (isSnow ? 20 : 19)}px`);
      particle.style.setProperty('--duration', `${12 + (i * 3) % 12}s`);
      particle.style.setProperty('--delay', `${-(i * 1.7)}s`);
      root.appendChild(particle);
    }
  }
})();
