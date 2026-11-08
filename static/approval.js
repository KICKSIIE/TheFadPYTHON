/* Approval remains verified on the server for every management POST. */
(function () {
  const dialog = document.getElementById('form-approval-modal');
  if (!dialog || !document.body.classList.contains('staff')) return;
  const approval = document.getElementById('form-approval');
  const pin = document.getElementById('form-approval-pin');
  const username = document.getElementById('form-approval-username');
  const title = document.getElementById('form-approval-title');
  const message = document.getElementById('form-approval-message');
  const confirm = document.getElementById('form-approval-confirm');
  const excluded = new Set(['/login', '/logout', '/account', '/attendance/clock-in', '/attendance/clock-out', '/attendance/overtime-in', '/attendance/overtime-out']);
  const bypass = new WeakSet();
  let pending = null;

  function protectedForm(form) {
    if (!(form instanceof HTMLFormElement) || form.closest('dialog') || (form.getAttribute('method') || 'get').toLowerCase() !== 'post') return false;
    const path = new URL(form.getAttribute('action') || location.pathname, location.href).pathname;
    return !excluded.has(path) && /^\/(admin\/|inventory\/|attendance\/)/.test(path);
  }

  document.addEventListener('submit', function (event) {
    const form = event.target;
    if (!protectedForm(form) || event.defaultPrevented) return;
    if (bypass.has(form)) { bypass.delete(form); return; }
    event.preventDefault();
    if (dialog.open) return;
    const submitter = event.submitter;
    const label = submitter?.textContent.trim() || submitter?.value || 'Save changes';
    pending = { form, submitter };
    title.textContent = form.dataset.approvalTitle || 'Admin approval';
    message.textContent = form.dataset.approvalMessage || `Approve: ${label}.`;
    confirm.textContent = form.dataset.approvalLabel || label;
    confirm.className = 'btn ' + (form.dataset.approvalDanger === '1' ? 'btn-danger-solid' : '');
    approval.reset();
    dialog.showModal();
    (username || pin).focus();
  });

  approval.addEventListener('submit', function (event) {
    event.preventDefault();
    if (!pending || !approval.reportValidity()) return;
    const { form, submitter } = pending;
    const temporary = [];
    function add(name, value) {
      const input = document.createElement('input');
      input.type = 'hidden'; input.name = name; input.value = value;
      form.append(input); temporary.push(input);
    }
    add('approval_pin', pin.value);
    if (username) add('approval_username', username.value.trim());
    pending = null;
    dialog.close();
    bypass.add(form);
    try {
      if (submitter && submitter.form === form) form.requestSubmit(submitter);
      else form.requestSubmit();
    } finally {
      bypass.delete(form);
      temporary.forEach(input => input.remove());
    }
  });
  dialog.querySelector('[data-approval-cancel]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', function () { pending = null; approval.reset(); });
})();
