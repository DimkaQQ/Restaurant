// Single owner of hex→rgb math (accent handling + chart colors).
window.hexToRgba = function (hex, a) {
  hex = hex.replace('#', '');
  if (hex.length === 3) hex = hex.split('').map(function (c) { return c + c; }).join('');
  var n = parseInt(hex, 16);
  return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
};

window.applyAccent = function (hex) {
  var r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
  var s = document.documentElement.style;
  s.setProperty('--gold', hex);
  s.setProperty('--gold-dim', window.hexToRgba(hex, 0.15));
  // WCAG-ish luminance decides whether black or white text sits on the accent
  s.setProperty('--on-accent', (0.2126 * r + 0.7152 * g + 0.0722 * b) > 150 ? '#0D0D0D' : '#FFFFFF');
};

// Chart.js paints on <canvas> and can't read CSS variables/color-mix — this
// resolves the theme tokens to concrete colors once, for every chart page.
window.chartTheme = function () {
  var root = getComputedStyle(document.documentElement);
  var pick = function (n, fb) { return (root.getPropertyValue(n).trim() || fb); };
  var muted = pick('--muted', '#8A857E');
  return {
    accent: pick('--gold', '#C8A84B'),
    text: pick('--white', '#F7F5F0'),
    muted: muted,
    ok: pick('--ok', '#4ade80'),
    bad: pick('--bad', '#f87171'),
    grid: window.hexToRgba(muted, 0.18),
  };
};
window.clearAccent = function () {
  var s = document.documentElement.style;
  s.removeProperty('--gold'); s.removeProperty('--gold-dim'); s.removeProperty('--on-accent');
};

/* Theme boot — runs at parse time (script is in <head>) so the page paints
 * in the right theme with no flash. Preferences are per device:
 * localStorage.ui_theme  = dark | black | light   (dark = the :root default)
 * localStorage.ui_accent = #rrggbb                (overrides --gold) */
(function () {
  try {
    var t = localStorage.getItem('ui_theme');
    if (t === 'black' || t === 'light') document.documentElement.setAttribute('data-theme', t);
    var a = localStorage.getItem('ui_accent');
    if (a && /^#[0-9a-fA-F]{6}$/.test(a)) window.applyAccent(a);
  } catch (e) {}
})();

/* Shared toast + confirm dialog — replaces raw browser alert()/confirm()
 * popups app-wide with something that matches the rest of the UI instead
 * of looking like a 2005-era JS error. Self-contained (injects its own
 * markup/styles on first use), no dependencies. */
(function () {
  function ensureHost() {
    let host = document.getElementById('notify-toast-host');
    if (!host) {
      host = document.createElement('div');
      host.id = 'notify-toast-host';
      document.body.appendChild(host);
    }
    return host;
  }

  function toast(message, kind) {
    const host = ensureHost();
    const el = document.createElement('div');
    el.className = 'notify-toast notify-' + (kind || 'info');
    const icon = kind === 'error' ? '⚠️' : kind === 'success' ? '✅' : 'ℹ️';
    el.innerHTML = '<span class="notify-icon">' + icon + '</span><span class="notify-msg"></span>';
    el.querySelector('.notify-msg').textContent = message;
    host.appendChild(el);
    requestAnimationFrame(() => el.classList.add('notify-in'));
    setTimeout(() => {
      el.classList.remove('notify-in');
      el.addEventListener('transitionend', () => el.remove(), { once: true });
      setTimeout(() => el.remove(), 500); // fallback if transitionend doesn't fire
    }, kind === 'error' ? 5000 : 3200);
  }

  function confirmDialog(message, opts) {
    opts = opts || {};
    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.className = 'notify-confirm-overlay';
      overlay.innerHTML = `
        <div class="notify-confirm-box">
          <div class="notify-confirm-msg"></div>
          <div class="notify-confirm-actions">
            <button class="notify-confirm-cancel">${opts.cancelText || 'Отмена'}</button>
            <button class="notify-confirm-ok${opts.danger ? ' notify-confirm-danger' : ''}">${opts.okText || 'Подтвердить'}</button>
          </div>
        </div>`;
      overlay.querySelector('.notify-confirm-msg').textContent = message;
      document.body.appendChild(overlay);
      requestAnimationFrame(() => overlay.classList.add('notify-in'));

      function close(result) {
        overlay.classList.remove('notify-in');
        setTimeout(() => overlay.remove(), 200);
        resolve(result);
      }
      overlay.querySelector('.notify-confirm-ok').addEventListener('click', () => close(true));
      overlay.querySelector('.notify-confirm-cancel').addEventListener('click', () => close(false));
      overlay.addEventListener('click', (e) => { if (e.target === overlay) close(false); });
      document.addEventListener('keydown', function onKey(e) {
        if (e.key === 'Escape') { document.removeEventListener('keydown', onKey); close(false); }
      });
    });
  }

  window.notify = {
    info: (msg) => toast(msg, 'info'),
    success: (msg) => toast(msg, 'success'),
    error: (msg) => toast(msg, 'error'),
    confirm: confirmDialog,
  };

  // Shared HTML-escaper for JS-rendered markup (single source — templates
  // must not carry their own copies). Escapes quotes of both kinds so the
  // result is safe inside any quoted attribute. NOTE: this is for HTML
  // contexts only; never build JS string literals in onclick from user
  // data — pass ids/indexes and look the object up instead.
  window.esc = (s) => (s == null ? '' : String(s))
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
})();
