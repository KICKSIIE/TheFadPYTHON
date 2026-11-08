/* Shared staff controls. Forms and links keep their native behavior. */
(() => {
  document.querySelectorAll('.table-wrap').forEach((wrap, index) => {
    wrap.tabIndex = 0;
    wrap.setAttribute('role', 'region');
    wrap.setAttribute('aria-label', `Scrollable table ${index + 1}`);
    const table = wrap.querySelector(':scope > table');
    const body = table?.tBodies[0];
    if (!body || table.dataset.pagination === 'server' || body.rows.length <= 10 || wrap.closest('.receipt')) return;
    const rows = Array.from(body.rows);
    const nav = document.createElement('nav');
    nav.className = 'table-pagination';
    nav.setAttribute('aria-label', `Table ${index + 1} pages`);
    const status = document.createElement('span');
    status.setAttribute('role', 'status');
    const select = document.createElement('select');
    select.setAttribute('aria-label', 'Rows per page');
    [10, 25, 50, 100].forEach(n => select.add(new Option(`${n} rows`, n)));
    const previous = document.createElement('button');
    const next = document.createElement('button');
    [previous, next].forEach(button => { button.type = 'button'; button.className = 'btn btn-sm btn-quiet'; });
    previous.textContent = 'Previous'; next.textContent = 'Next';
    let page = 1;
    function render() {
      const size = Number(select.value), count = Math.ceil(rows.length / size);
      page = Math.min(page, count);
      rows.forEach((row, i) => { row.hidden = i < (page - 1) * size || i >= page * size; });
      status.textContent = `${(page - 1) * size + 1}–${Math.min(page * size, rows.length)} of ${rows.length} · Page ${page} of ${count}`;
      previous.disabled = page === 1; next.disabled = page === count;
      wrap.scrollTop = 0;
    }
    previous.addEventListener('click', () => { page--; render(); });
    next.addEventListener('click', () => { page++; render(); });
    select.addEventListener('change', () => { page = 1; render(); });
    nav.append(status, select, previous, next); wrap.after(nav); render();
  });

  const form = document.getElementById('product-editor');
  if (form) {
    const text = (id, value) => { document.getElementById(id).textContent = value; };
    const value = name => form.elements.namedItem(name)?.value.trim() || '';
    const chips = (id, source) => {
      const target = document.getElementById(id); target.replaceChildren();
      (source.split(',').map(v => v.trim()).filter(Boolean).slice(0, 30)).forEach(v => {
        const chip = document.createElement('span'); chip.className = 'chip'; chip.textContent = v; target.append(chip);
      });
      if (!target.childElementCount) target.textContent = '—';
    };
    function update() {
      text('preview-name', value('product_name') || 'Product name');
      const price = Number(value('base_price').replaceAll(',', ''));
      text('preview-price', new Intl.NumberFormat('en-PH', {style:'currency', currency:'PHP'}).format(Number.isFinite(price) ? price : 0));
      text('preview-description', value('description') || 'Your product description will appear here.');
      text('preview-category', form.elements.category_id.selectedOptions[0]?.textContent || 'Category');
      chips('preview-colors', value('colors') || value('color')); chips('preview-sizes', value('sizes') || value('size'));
    }
    form.addEventListener('input', update); update();
    let photoUrl;
    form.elements.photos?.addEventListener('change', event => {
      if (photoUrl) URL.revokeObjectURL(photoUrl);
      const file = event.target.files[0], cover = document.getElementById('preview-cover');
      cover.replaceChildren();
      if (!file || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
        cover.textContent = 'Choose a JPG, PNG or WebP photo'; return;
      }
      const img = document.createElement('img'); photoUrl = URL.createObjectURL(file);
      img.src = photoUrl; img.alt = 'Selected product photo'; cover.append(img);
    });
    window.addEventListener('pagehide', () => { if (photoUrl) URL.revokeObjectURL(photoUrl); });
  }
  const promo = document.getElementById('promo-editor');
  if (promo) {
    function update() {
      const values = promo.elements;
      document.getElementById('promo-preview-name').textContent = values.discount_name.value.trim() || 'Your next promotion';
      document.getElementById('promo-preview-rate').textContent = `${values.discount_percentage.value || '0'}%`;
      document.getElementById('promo-preview-dates').textContent = `${values.start_date.value || 'Start date'} → ${values.end_date.value || 'End date'}`;
      values.end_date.min = values.start_date.value;
      const scope = values.scope;
      if (scope) document.getElementById('promo-preview-scope').textContent = scope.selectedOptions[0].textContent;
    }
    promo.addEventListener('input', update); update();
  }
})();
