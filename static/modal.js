/* Destructive actions open a confirmation modal that collects the approval PIN. */
(function () {
  const dialog = document.getElementById('approval-modal');
  if (!dialog) return;
  const form = document.getElementById('approval-form');
  const title = document.getElementById('approval-modal-title');
  const copy = document.getElementById('approval-modal-copy');
  const pin = document.getElementById('modal-pin');
  const confirm = document.getElementById('approval-confirm');
  const extras = document.getElementById('approval-extra');

  document.querySelectorAll('[data-confirm]').forEach(function (button) {
    button.addEventListener('click', function () {
      form.setAttribute('action', button.dataset.action);
      title.textContent = button.dataset.title || 'Confirm';
      copy.textContent = button.dataset.message || '';
      confirm.textContent = button.dataset.confirmLabel || 'Confirm';
      confirm.className = 'btn ' + (button.dataset.danger === '1' ? 'btn-danger-solid' : '');
      extras.innerHTML = '';
      let fields = {};
      try { fields = JSON.parse(button.dataset.fields || '{}'); } catch (e) { fields = {}; }
      Object.keys(fields).forEach(function (name) {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = name;
        input.value = fields[name];
        extras.append(input);
      });
      pin.value = '';
      dialog.showModal();
      pin.focus();
    });
  });

  dialog.querySelectorAll('[data-close]').forEach(function (button) {
    button.addEventListener('click', function () { dialog.close(); });
  });
})();
