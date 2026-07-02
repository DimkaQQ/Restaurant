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
})();
