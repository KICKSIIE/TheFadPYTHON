/* Server-side verification is required for every management POST. */
(function () {
  const excluded = new Set(['/login', '/logout', '/account', '/attendance/clock-in', '/attendance/clock-out', '/attendance/overtime-in', '/attendance/overtime-out']);
  const admin = document.body.dataset.role === 'Admin';
  if (!document.body.classList.contains('staff')) return;

  document.querySelectorAll('form[method="post"]').forEach(function (form, index) {
    if (form.closest('dialog')) return;                    // confirmation modals carry their own PIN field
    // getAttribute, not form.action: a field named "action" (inventory forms) would shadow the URL.
    const target = form.getAttribute('action') || location.pathname;
    const path = new URL(target, location.href).pathname;
    if (excluded.has(path) || !/^\/(admin\/|inventory\/|attendance\/)/.test(path)) return;

    const section = document.createElement('div');
    section.className = 'approval-section';
    section.setAttribute('role', 'group');
    section.setAttribute('aria-label', 'Admin approval');
    const heading = document.createElement('h3');
    heading.textContent = 'Admin approval';
    section.append(heading);

    const row = document.createElement('div');
    row.className = 'approval-fields';
    section.append(row);

    function field(name, title, type) {
      const id = 'approval-' + index + '-' + name;
      const wrap = document.createElement('div');
      wrap.className = 'field';
      const labelRow = document.createElement('div');
      labelRow.className = 'field-label-row';
      const label = document.createElement('label');
      label.htmlFor = id;
      label.textContent = title;
      labelRow.append(label);
      const input = document.createElement('input');
      input.id = id;
      input.name = name;
      input.type = type;
      input.required = true;
      input.autocomplete = 'off';
      if (name === 'approval_username') {
        input.placeholder = 'Admin username';
      } else {
        input.inputMode = 'numeric';
        input.pattern = '[0-9]{6,12}';
        input.placeholder = '6-12 digits';
        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'reveal';
        toggle.textContent = 'Show';
        toggle.setAttribute('aria-pressed', 'false');
        toggle.addEventListener('click', function () {
          const show = input.type === 'password';
          input.type = show ? 'text' : 'password';
          toggle.textContent = show ? 'Hide' : 'Show';
          toggle.setAttribute('aria-pressed', String(show));
        });
        labelRow.append(toggle);
      }
      wrap.append(labelRow, input);
      row.append(wrap);
    }

    if (!admin) field('approval_username', 'Approving admin', 'text');
    field('approval_pin', 'Approval PIN', 'password');

    if (form.closest('.table')) {
      form.append(section);                                 // table rows keep a compact inline block
    } else {
      const anchor = form.querySelector('.form-actions') || form.querySelector('button[type="submit"]');
      form.insertBefore(section, anchor);
    }
  });
})();
