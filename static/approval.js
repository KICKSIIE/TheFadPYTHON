/* Server-side verification is required for every management POST. */
(function () {
  const excluded = new Set(['/login', '/logout', '/account', '/attendance/clock-in', '/attendance/clock-out', '/attendance/overtime-in', '/attendance/overtime-out']);
  const admin = document.body.dataset.role === 'Admin';
  if (!document.body.classList.contains('staff')) return;
  document.querySelectorAll('form[method="post"]').forEach(function (form, index) {
    const path = new URL(form.action, location.href).pathname;
    if (excluded.has(path) || !/^\/(admin\/|inventory\/|attendance\/)/.test(path)) return;
    const fields = document.createElement('fieldset'); fields.className = 'approval-fields';
    const legend = document.createElement('legend'); legend.textContent = 'Admin approval'; fields.append(legend);
    function field(name, title, type) {
      const id = 'approval-' + index + '-' + name;
      const label = document.createElement('label'); label.htmlFor = id; label.textContent = title;
      const input = document.createElement('input'); input.id = id; input.name = name; input.type = type;
      input.required = true; input.autocomplete = 'off';
      if (type === 'password') { input.inputMode = 'numeric'; input.pattern = '[0-9]{6,12}'; }
      fields.append(label, input);
    }
    if (!admin) field('approval_username', 'Approving admin username', 'text');
    field('approval_pin', 'Approval PIN', 'password');
    const actions = form.querySelector('.form-actions');
    form.insertBefore(fields, actions || null);
  });
})();
