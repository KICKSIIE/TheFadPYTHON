/* Shared staff controls. Forms and links keep their native behavior. */
(() => {
  // Restore position only after a cart mutation, never after checkout or filtering.
  if (location.pathname === '/pos/') {
    const saved = sessionStorage.getItem('pos-scroll');
    sessionStorage.removeItem('pos-scroll');
    if (saved) { try { const position = JSON.parse(saved); requestAnimationFrame(() => { window.scrollTo(0, position.y); const cart = document.querySelector('.cart'); if (cart) cart.scrollTop = position.cart; }); } catch (_) {} }
    let cartBusy = false;
    document.addEventListener('submit', async event => {
      const form=event.target;
      if (!form.matches('form[action*="/pos/cart/"]')) return;
      event.preventDefault(); if (cartBusy) return; cartBusy=true;
      const position={y:window.scrollY,cart:document.querySelector('.cart')?.scrollTop || 0};
      const fields={}; document.querySelectorAll('.cart form[action*="checkout"] input:not([type=hidden]), .cart select').forEach(input=>{fields[input.name]=input.value;});
      const data=new FormData(form, event.submitter);
      try {
        const response=await fetch(form.action,{method:'POST',body:data,credentials:'same-origin'});
        if (new URL(response.url).pathname !== '/pos/') { location.assign(response.url); return; }
        const page=new DOMParser().parseFromString(await response.text(),'text/html');
        const content=page.querySelector('.pos'); if (!response.ok || !content) throw new Error('refresh');
        document.querySelector('.pos').replaceWith(content);
        document.querySelectorAll('.flash').forEach(flash=>flash.remove());
        page.querySelectorAll('.flash').forEach(flash=>document.querySelector('.pos').before(flash));
        document.querySelectorAll('.cart input:not([type=hidden]), .cart select').forEach(input=>{if(input.name in fields) input.value=fields[input.name];});
        window.scrollTo(0,position.y); document.querySelector('.cart').scrollTop=position.cart;
      } catch (_) {
        const notice=document.createElement('p'); notice.className='flash error';notice.setAttribute('role','alert');notice.textContent='Could not refresh the cart. Reload to check its current contents before adding again.';document.querySelector('.pos').before(notice);
      } finally { cartBusy=false; }
    });
  }
  document.querySelectorAll('.table-wrap').forEach((wrap, index) => {
    wrap.tabIndex = 0; wrap.setAttribute('role', 'region'); wrap.setAttribute('aria-label', `Scrollable table ${index + 1}`);
    const table = wrap.querySelector(':scope > table'), body = table?.tBodies[0];
    if (!body || !table.tHead || wrap.closest('.receipt')) return;
    let rows = Array.from(body.rows);
    if (!rows.length || rows.some(row => row.cells.length !== table.tHead.rows[0].cells.length)) return;
    const headings = Array.from(table.tHead.rows[0].cells);
    const number = document.createElement('th'); number.textContent = '#'; number.scope = 'col'; table.tHead.rows[0].prepend(number);
    const offset = Number(table.dataset.offset || 0);
    rows.forEach((row, i) => { const cell = row.insertCell(0); cell.textContent = offset + i + 1; cell.className = 'row-number'; });
    if (table.tFoot) Array.from(table.tFoot.rows).forEach(row => { row.cells[0].colSpan += 1; });
    let page = 1, size = 10;
    const server = table.dataset.pagination === 'server';
    let status, previous, next;
    function render() {
      const count = Math.max(1, Math.ceil(rows.length / size)); page = Math.min(page, count);
      rows.forEach((row, i) => { row.hidden = !server && (i < (page - 1) * size || i >= page * size); body.append(row); row.cells[0].textContent = offset + i + 1; });
      if (status) { status.textContent = `${(page - 1) * size + 1}–${Math.min(page * size, rows.length)} of ${rows.length} · Page ${page} of ${count}`; previous.disabled = page === 1; next.disabled = page === count; }
    }
    function sortValue(cell) {
      const raw = cell.dataset.sort || cell.innerText.trim();
      if (/^[₱\d−+.,%\s-]+$/.test(raw)) { const n = Number(raw.replace(/[₱,%\s]/g, '').replace('−','-')); if (Number.isFinite(n)) return n; }
      if (/^[A-Z][a-z]{2} \d/.test(raw)) { const timestamp = Date.parse(raw.replace(' · ', ' ')); if (Number.isFinite(timestamp)) return timestamp; }
      return raw;
    }
    headings.forEach((heading, column) => {
      if (!heading.textContent.trim() || /actions/i.test(heading.textContent)) return;
      const label = heading.textContent.trim(), button = document.createElement('button'); button.type = 'button'; button.className = 'table-sort'; button.textContent = label + ' ↕';
      button.title = server ? 'Sort events on this page' : `Sort by ${label}`;
      let ascending = false;
      button.addEventListener('click', () => {
        ascending = !ascending; headings.forEach(h => h.removeAttribute('aria-sort')); heading.setAttribute('aria-sort', ascending ? 'ascending' : 'descending');
        rows.sort((a,b) => { const x=sortValue(a.cells[column+1]), y=sortValue(b.cells[column+1]); const result=typeof x==='number' && typeof y==='number' ? x-y : String(x).localeCompare(String(y), undefined, {numeric:true,sensitivity:'base'}); return ascending ? result : -result; });
        button.textContent = label + (ascending ? ' ↑' : ' ↓'); page=1; render();
      }); heading.replaceChildren(button);
    });
    if (!server && rows.length > 10) {
      const nav=document.createElement('nav'); nav.className='table-pagination'; nav.setAttribute('aria-label', `Table ${index+1} pages`);
      status=document.createElement('span'); status.setAttribute('role','status');
      const select=document.createElement('select'); select.setAttribute('aria-label','Rows per page'); [10,25,50,100].forEach(n => select.add(new Option(`${n} rows`,n)));
      previous=document.createElement('button'); next=document.createElement('button');
      [previous,next].forEach(b => { b.type='button'; b.className='btn btn-sm btn-quiet'; }); previous.textContent='Previous'; next.textContent='Next';
      previous.addEventListener('click',()=>{page--;render();wrap.scrollTop=0;}); next.addEventListener('click',()=>{page++;render();wrap.scrollTop=0;}); select.addEventListener('change',()=>{size=Number(select.value);page=1;render();});
      nav.append(status,select,previous,next); wrap.after(nav);
    } else size=rows.length;
    render();
  });

  // File selections accumulate across picker openings. First photo is the cover.
  const photos = document.querySelector('input[type="file"][name="photos"]');
  if (photos) {
    const gallery=document.createElement('div'); gallery.className='upload-previews'; photos.after(gallery);
    let selected=[], urls=[];
    function redraw() {
      urls.forEach(url=>URL.revokeObjectURL(url)); urls=[]; gallery.replaceChildren();
      const transfer=new DataTransfer(); selected.forEach(file=>transfer.items.add(file)); photos.files=transfer.files;
      selected.forEach((file,i)=>{
        const card=document.createElement('div'), image=document.createElement('img'), remove=document.createElement('button'), label=document.createElement('span');
        const url=URL.createObjectURL(file); urls.push(url); image.src=url; image.alt=file.name;
        label.textContent=i===0?'Cover':`Photo ${i+1}`; remove.type='button'; remove.className='btn btn-sm btn-quiet'; remove.textContent='Remove'; remove.setAttribute('aria-label',`Remove ${file.name}`);
        remove.addEventListener('click',()=>{selected.splice(i,1);redraw();photos.dispatchEvent(new Event('input',{bubbles:true}));}); card.append(image,label,remove);gallery.append(card);
      });
      const cover=document.querySelector('#preview-cover'); if (cover) { cover.replaceChildren(); if (selected.length) {const img=document.createElement('img'); img.src=urls[0]; img.alt='Selected cover'; cover.append(img);} else cover.textContent='Choose a photo to preview your product'; }
    }
    photos.addEventListener('change',()=>{ for(const file of photos.files) if (!selected.some(f=>f.name===file.name && f.size===file.size && f.lastModified===file.lastModified)) selected.push(file); redraw(); });
    window.addEventListener('pagehide',()=>urls.forEach(url=>URL.revokeObjectURL(url)));
  }

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

  }
  const promo = document.getElementById('promo-editor');
  if (promo) {
    const dates = () => { promo.elements.end_date.min = promo.elements.start_date.value; };
    promo.addEventListener('input', dates); dates();
  }
  document.querySelectorAll('[data-promo-scope]').forEach(scope => {
    const product = scope.closest('.promo-products-panel').querySelector('.promo-product-field');
    const sync = () => { product.hidden = scope.value !== 'PRODUCT'; };
    scope.addEventListener('change', sync); sync();
  });

})();
