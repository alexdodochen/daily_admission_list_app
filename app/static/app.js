// ========================================================================
// Small vanilla JS app. No framework — keeps the local bundle zero-deps.
// ========================================================================

// ---------- Help modal (runs on every page) ----------
(function () {
  const link = document.getElementById('help-link');
  const modal = document.getElementById('help-modal');
  const close = document.getElementById('help-close');
  if (!link || !modal) return;
  // Auto-pick tab based on current page when opening
  const pickInitialTab = () => {
    const path = window.location.pathname;
    if (path.startsWith('/sched')) return 'sched';
    if (path.startsWith('/keyin')) return 'keyin';
    return 'admission';  // default + /admission + /
  };
  const showTab = (name) => {
    modal.querySelectorAll('button.help-tab').forEach(b =>
      b.classList.toggle('active', b.dataset.tab === name));
    modal.querySelectorAll('.help-tab-pane').forEach(p =>
      p.classList.toggle('active', p.dataset.tab === name));
  };
  link.addEventListener('click', (e) => {
    e.preventDefault();
    showTab(pickInitialTab());
    modal.hidden = false;
  });
  modal.querySelectorAll('button.help-tab').forEach(btn => {
    btn.addEventListener('click', () => showTab(btn.dataset.tab));
  });
  if (close) close.addEventListener('click', () => { modal.hidden = true; });
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.hidden = true; });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.hidden) modal.hidden = true;
  });
})();


// ---------- Bug report modal (runs on every page) ----------
(function () {
  const link   = document.getElementById('bug-link');
  const modal  = document.getElementById('bug-modal');
  const close  = document.getElementById('bug-close');
  if (!link || !modal) return;
  const $$ = (id) => document.getElementById(id);
  const msg = $$('bug-msg');
  let issueUrl = '';

  const hideActions = () => {
    ['bug-issue-btn', 'bug-save-btn', 'bug-copy-btn'].forEach(i => {
      const b = $$(i); if (b) b.hidden = true;
    });
    const pv = $$('bug-preview'); if (pv) { pv.hidden = true; pv.textContent = ''; }
  };
  const open = () => {
    // Auto-fill the error box with the last red error seen this session.
    const errBox = $$('bug-error');
    if (errBox && !errBox.value && window.__lastError) errBox.value = window.__lastError;
    if (msg) msg.textContent = '';
    hideActions();
    modal.hidden = false;
  };
  const dismiss = () => {
    modal.hidden = true;
    selectedImages = [];
    const ii = $$('bug-images'); if (ii) ii.value = '';
    renderImages();
  };

  link.addEventListener('click', (e) => { e.preventDefault(); open(); });
  if (close) close.addEventListener('click', dismiss);
  modal.addEventListener('click', (e) => { if (e.target === modal) dismiss(); });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.hidden) dismiss();
  });

  function form() {
    const fd = new FormData();
    fd.append('step',  ($$('bug-step')  || {}).value || '');
    fd.append('note',  ($$('bug-note')  || {}).value || '');
    fd.append('error', ($$('bug-error') || {}).value || '');
    return fd;
  }

  // --- screenshot attachments (private .zip only — never the public issue) ---
  const MAX_IMAGES = 10;
  const MAX_IMG_BYTES = 10 * 1024 * 1024;  // 10 MB / image
  let selectedImages = [];

  function renderImages() {
    const list = $$('bug-image-list');
    if (!list) return;
    list.innerHTML = selectedImages.map((f, i) => {
      const nm = f.name.length > 18 ? f.name.slice(0, 16) + '…' : f.name;
      return `<div class="bug-thumb"><img src="${URL.createObjectURL(f)}" alt="">` +
             `<button type="button" data-i="${i}" title="移除這張">✕</button>` +
             `<span>${nm}</span></div>`;
    }).join('') + (selectedImages.length
      ? `<p class="bug-img-count">已選 ${selectedImages.length} / ${MAX_IMAGES} 張</p>` : '');
    list.querySelectorAll('button[data-i]').forEach(b => {
      b.addEventListener('click', () => {
        selectedImages.splice(parseInt(b.dataset.i, 10), 1);
        renderImages();
      });
    });
  }

  const imgInput = $$('bug-images');
  if (imgInput) {
    imgInput.addEventListener('change', () => {
      for (const f of Array.from(imgInput.files || [])) {
        if (selectedImages.length >= MAX_IMAGES) {
          if (msg) { msg.className = 'msg err';
            msg.textContent = `✗ 最多 ${MAX_IMAGES} 張，多出來的已略過。`; }
          break;
        }
        if (!f.type.startsWith('image/')) continue;
        if (f.size > MAX_IMG_BYTES) {
          if (msg) { msg.className = 'msg err';
            msg.textContent = `✗ ${f.name} 超過 10MB，已略過。`; }
          continue;
        }
        if (selectedImages.some(x => x.name === f.name && x.size === f.size)) continue;
        selectedImages.push(f);
      }
      imgInput.value = '';  // let the user re-pick the same file later
      renderImages();
    });
  }

  $$('bug-preview-btn').addEventListener('click', async () => {
    if (msg) { msg.className = 'hint'; msg.textContent = '產生中…'; }
    try {
      const r = await fetch('/api/bug-report/preview', { method: 'POST', body: form() })
        .then(x => x.json());
      if (!r.ok) throw new Error(r.error || '產生失敗');
      issueUrl = r.issue_url || '';
      const pv = $$('bug-preview');
      pv.textContent = r.markdown || '';
      pv.hidden = false;
      ['bug-issue-btn', 'bug-save-btn', 'bug-copy-btn'].forEach(i => {
        const b = $$(i); if (b) b.hidden = false;
      });
      if (msg) { msg.className = 'msg ok';
        msg.textContent = '✓ 內容已產生（已隱藏病歷號/姓名/金鑰）。請看下方預覽，確認沒有病人資料再送出。'; }
    } catch (err) {
      if (msg) { msg.className = 'msg err'; msg.textContent = '✗ ' + err.message; }
    }
  });

  $$('bug-issue-btn').addEventListener('click', () => {
    if (!issueUrl) return;
    if (!confirm('即將開啟 GitHub 公開回報頁。請再次確認預覽內容沒有任何病人姓名/病歷號。確定？')) return;
    window.open(issueUrl, '_blank', 'noopener');
  });

  $$('bug-save-btn').addEventListener('click', async () => {
    if (msg) { msg.className = 'hint'; msg.textContent = '存檔中…'; }
    try {
      const fd = form();
      selectedImages.forEach(f => fd.append('images', f, f.name));
      const r = await fetch('/api/bug-report/save', { method: 'POST', body: fd })
        .then(x => x.json());
      if (!r.ok) throw new Error(r.error || '存檔失敗');
      const imgNote = r.images ? `（含 ${r.images} 張截圖，已打包成 zip）` : '';
      if (msg) { msg.className = 'msg ok';
        msg.textContent = '✓ 已存到：' + r.path + imgNote +
          '　把這個檔私下傳（LINE/email）給陳常胤醫師即可。'; }
    } catch (err) {
      if (msg) { msg.className = 'msg err'; msg.textContent = '✗ ' + err.message; }
    }
  });

  $$('bug-copy-btn').addEventListener('click', async () => {
    const pv = $$('bug-preview');
    try {
      await navigator.clipboard.writeText(pv ? pv.textContent : '');
      if (msg) { msg.className = 'msg ok'; msg.textContent = '✓ 已複製，可貼到任何地方傳給開發者。'; }
    } catch (_) {
      if (msg) { msg.className = 'msg err'; msg.textContent = '✗ 瀏覽器不允許自動複製，請手動選取預覽內容。'; }
    }
  });
})();


// ---------- Scroll-to-top button (runs on every page) ----------
(function () {
  const btn = document.getElementById('scroll-to-top');
  if (!btn) return;
  const update = () => {
    btn.classList.toggle('visible', window.scrollY > 240);
  };
  window.addEventListener('scroll', update, { passive: true });
  btn.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
  update();
})();


// ---------- Sheet viewer modal (runs on every page) ----------
(function () {
  const link    = document.getElementById('viewer-link');
  const modal   = document.getElementById('viewer-modal');
  const close   = document.getElementById('viewer-close');
  const select  = document.getElementById('viewer-date-select');
  const refresh = document.getElementById('viewer-refresh');
  const delBtn  = document.getElementById('viewer-delete-btn');
  const msg     = document.getElementById('viewer-msg');
  const body    = document.getElementById('viewer-body');
  if (!link || !modal) return;

  const MAIN_HEADER  = ['實際住院日','開刀日','科別','主治醫師','主診斷(ICD)','姓名','性別','年齡','病歷號碼','病床號','入院提示','住急'];
  const ORDER_HEADER = ['序號','主治醫師','病人姓名','備註(住服)','備註','病歷號','術前診斷','預計心導管','改期'];
  const SUB_HEADER   = ['姓名','病歷號','EMR','EMR摘要','手動設定入院序','術前診斷','預計心導管','註記','備註(住服)'];

  // Track the currently-loaded sheet name so cell writes know where to land.
  let currentSheet = '';

  const esc = (s) => String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  function setMsg(text, kind) {
    msg.textContent = text;
    msg.className = 'msg ' + (kind || '');
  }

  function isYmd(s) { return /^\d{8}$/.test(String(s || '')); }

  function todayYmd() {
    const now = new Date();
    const tp = new Date(now.getTime() + (now.getTimezoneOffset() + 480) * 60000);
    return `${tp.getFullYear()}${String(tp.getMonth()+1).padStart(2,'0')}${String(tp.getDate()).padStart(2,'0')}`;
  }

  // editableCell(row, col, value): renders a <td> with contenteditable=true
  // and data-row/data-col so the blur handler can POST a write. col is
  // 1-indexed; row is the absolute sheet row number.
  function editableCell(row, col, value) {
    return `<td contenteditable="true" data-row="${row}" data-col="${col}" data-orig="${esc(value)}">${esc(value)}</td>`;
  }

  function renderTable(headers, rows, startRow, colOffset) {
    if (!rows.length) return '<p class="viewer-empty">（無資料）</p>';
    const thead = '<tr><th></th>' + headers.map(h => `<th>${esc(h)}</th>`).join('') + '</tr>';
    const tbody = rows.map((r, i) => {
      const cells = headers.map((_, c) =>
        editableCell(startRow + i, colOffset + c, r[c] || '')
      ).join('');
      return `<tr><td class="viewer-rowidx">${startRow + i}</td>${cells}</tr>`;
    }).join('');
    return `<table>
      <thead>${thead}</thead><tbody>${tbody}</tbody>
    </table>`;
  }

  function renderSub(sub) {
    const mismatchTag = (sub.declared != null && sub.actual_count !== sub.declared)
      ? ` <span class="viewer-count-mismatch">（標題 ${sub.declared} ≠ 實際 ${sub.actual_count}）</span>`
      : '';
    const title = `<h4>${esc(sub.doctor || '(未命名)')}（${sub.declared ?? '?'} 人）${mismatchTag}</h4>`;
    // `sub.rows` from /api/sheet/read is PATIENT ROWS ONLY (server-side strip
    // of title + subheader rows — they were ghost-rendered as the 2nd row of
    // each block's table before this fix, looking like duplicate subheaders).
    // first_patient_row → start row for inline edit; fall back to title_row+2.
    const startRow = sub.first_patient_row || ((sub.title_row || 1) + 2);
    return `<div class="viewer-sub">${title}${renderTable(SUB_HEADER, sub.rows || [], startRow, 1)}</div>`;
  }

  function render(data) {
    const mainRows  = (data.main  || []).slice(1);   // strip header row
    const orderRows = (data.ordering || []).slice(1);
    const main  = `<div class="viewer-section"><h3>主資料 A-L（${mainRows.length} 列）</h3>${renderTable(MAIN_HEADER, mainRows, 2, 1)}</div>`;
    // Ordering block lives at columns N..W = 14..23. Pass colOffset=14.
    const order = `<div class="viewer-section"><h3>入院序 N-V（${orderRows.length} 列）</h3>${renderTable(ORDER_HEADER, orderRows, 2, 14)}</div>`;
    const subsHtml = (data.subs && data.subs.length)
      ? `<div class="viewer-section"><h3>子表格（${data.subs.length} 位醫師）</h3>${data.subs.map(renderSub).join('')}</div>`
      : '<div class="viewer-section"><h3>子表格</h3><p class="viewer-empty">（無子表格）</p></div>';
    body.innerHTML = `<p class="hint" style="margin:6px 0 12px;color:#555">編輯方式：點任一儲存格直接打字，按 Enter 或點別處即儲存回 Google Sheet。</p>` +
      main + order + subsHtml;
  }

  function renderRaw(data) {
    const rows = data.rows || [];
    const cols = data.cols || 0;
    if (!rows.length || !cols) {
      body.innerHTML = '<p class="viewer-empty">（此分頁無資料）</p>';
      return;
    }
    const colLetter = (i) => {
      let n = i; let s = '';
      do { s = String.fromCharCode(65 + (n % 26)) + s; n = Math.floor(n / 26) - 1; } while (n >= 0);
      return s;
    };
    const headCols = Array.from({ length: cols }, (_, i) =>
      `<th class="viewer-rawcol">${colLetter(i)}</th>`).join('');
    const tbody = rows.map((r, i) => {
      const cells = Array.from({ length: cols }, (_, c) =>
        editableCell(i + 1, c + 1, r[c] || '')
      ).join('');
      return `<tr><td class="viewer-rowidx">${i + 1}</td>${cells}</tr>`;
    }).join('');
    body.innerHTML = `<p class="hint" style="margin:6px 0 12px;color:#555">編輯方式：點任一儲存格直接打字，按 Enter 或點別處即儲存回 Google Sheet。</p>
      <div class="viewer-section"><h3>${esc(data.name)}（${rows.length} 列 × ${cols} 欄）</h3>
      <table><thead><tr><th></th>${headCols}</tr></thead><tbody>${tbody}</tbody></table></div>`;
  }

  // Cell-edit listener — single delegated handler so all <td contenteditable>
  // cells fire a write on blur (or on Enter, which we redirect to blur).
  async function commitCell(td) {
    const row  = td.getAttribute('data-row');
    const col  = td.getAttribute('data-col');
    const orig = td.getAttribute('data-orig') || '';
    const next = (td.innerText || '').replace(/\r/g, '').replace(/\n+$/, '');
    if (!currentSheet || !row || !col) return;
    if (next === orig) return;  // no change
    td.classList.add('viewer-cell-saving');
    try {
      // currentSheet may be "<source>:<name>" or bare name (legacy)
      const { src, name } = decodeKey(currentSheet);
      const fd = new FormData();
      fd.append('sheet', name);
      fd.append('source', src);
      fd.append('row', row);
      fd.append('col', col);
      fd.append('value', next);
      const resp = await fetch('/api/sheet/write_cell', { method: 'POST', body: fd });
      if (!resp.ok) throw new Error(await resp.text());
      const r = await resp.json().catch(() => ({}));
      td.setAttribute('data-orig', next);
      td.classList.remove('viewer-cell-saving');
      td.classList.add('viewer-cell-saved');
      setTimeout(() => td.classList.remove('viewer-cell-saved'), 1200);
      // Live-mirror: 備註↔註記 / 術前診斷 / 預計心導管 — if the server
      // copied this edit to its twin cell, reflect it in the open viewer too.
      const mr = r && r.mirror;
      if (mr && mr.mirrored && mr.target_row && mr.target_col) {
        const twin = body.querySelector(
          `td[data-row="${mr.target_row}"][data-col="${mr.target_col}"]`);
        if (twin) {
          twin.innerText = next;
          twin.setAttribute('data-orig', next);
          twin.classList.add('viewer-cell-saved');
          setTimeout(() => twin.classList.remove('viewer-cell-saved'), 1200);
        }
        setMsg('✓ 已儲存，並同步到' + (mr.target || '對應欄位'), 'ok');
      }
    } catch (err) {
      td.classList.remove('viewer-cell-saving');
      td.classList.add('viewer-cell-error');
      td.innerText = orig;
      setMsg('✗ 寫入失敗：' + (err.message || err), 'err');
      setTimeout(() => td.classList.remove('viewer-cell-error'), 2000);
    }
  }

  body.addEventListener('focusout', (e) => {
    const td = e.target.closest('td[contenteditable="true"]');
    if (td) commitCell(td);
  });
  body.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      const td = e.target.closest('td[contenteditable="true"]');
      if (td) { e.preventDefault(); td.blur(); }
    }
  });

  // Encode/decode "<source>:<name>" so we can route the read API call
  function encodeKey(src, name) { return src + ':' + name; }
  function decodeKey(key) {
    const i = (key || '').indexOf(':');
    if (i < 0) return { src: 'admission', name: key || '' };
    return { src: key.slice(0, i), name: key.slice(i + 1) };
  }

  // Cache the raw list response so switching source tabs doesn't re-hit the API
  let _sheetListCache = null;
  let _currentSrc = 'admission';

  function populateSelectForSource(src) {
    if (!_sheetListCache) return;
    const r = _sheetListCache;
    const today = todayYmd();
    const opts = ['<option value="">— 選擇分頁 —</option>'];
    if (src === 'admission') {
      const adm = (r.admission || r.sheets || []).slice();
      const others = adm.filter(s => !isYmd(s));
      const dates  = adm.filter(isYmd).sort((a, b) => b.localeCompare(a));
      // 其他工作表 FIRST per user preference, date sheets after
      if (others.length) {
        opts.push('<optgroup label="📋 其他工作表">');
        opts.push(...others.map(s => `<option value="${encodeKey('admission', s)}">${s}</option>`));
        opts.push('</optgroup>');
      }
      if (dates.length) {
        opts.push('<optgroup label="📆 每天的工作表 (YYYYMMDD)">');
        opts.push(...dates.map(d => {
          const k = encodeKey('admission', d);
          return `<option value="${k}"${d === today ? ' selected' : ''}>${d}</option>`;
        }));
        opts.push('</optgroup>');
      }
      setMsg(`入院 — 其他 ${others.length}、日期分頁 ${dates.length}`, 'ok');
    } else if (src === 'schedule') {
      const sched = (r.schedule || []).slice();
      const monthTabs = sched.filter(s => /^\d{6}$/.test(s)).sort((a, b) => b.localeCompare(a));
      const otherTabs = sched.filter(s => !/^\d{6}$/.test(s));
      if (otherTabs.length) {
        opts.push('<optgroup label="📋 其他工作表">');
        opts.push(...otherTabs.map(s => `<option value="${encodeKey('schedule', s)}">${s}</option>`));
        opts.push('</optgroup>');
      }
      if (monthTabs.length) {
        opts.push('<optgroup label="📆 月份分頁 (YYYYMM)">');
        opts.push(...monthTabs.map(s => `<option value="${encodeKey('schedule', s)}">${s}</option>`));
        opts.push('</optgroup>');
      }
      setMsg(`排班 — 其他 ${otherTabs.length}、月份 ${monthTabs.length}`, 'ok');
    }
    select.innerHTML = opts.join('');
  }

  async function loadSheets() {
    setMsg('讀取分頁清單…', 'ok');
    try {
      _sheetListCache = await api('/api/sheet/list');
      populateSelectForSource(_currentSrc);
      // Auto-select today's date sheet ONLY when admission source + today exists
      if (_currentSrc === 'admission') {
        const today = todayYmd();
        const adm = (_sheetListCache.admission || _sheetListCache.sheets || []);
        if (adm.includes(today)) loadSheet(encodeKey('admission', today));
      }
    } catch (err) {
      setMsg('✗ ' + err.message, 'err');
    }
  }

  // Wire source tab clicks
  document.querySelectorAll('.viewer-src-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      const src = btn.dataset.src;
      _currentSrc = src;
      document.querySelectorAll('.viewer-src-tab').forEach(b =>
        b.classList.toggle('active', b === btn));
      body.innerHTML = `<p class="hint">已切換到 ${src === 'schedule' ? '📅 排班' : '📥 每日入院清單'}，請選分頁。</p>`;
      currentSheet = '';
      // 批次刪除只支援入院 Sheet 的日期分頁
      if (delBtn) delBtn.style.display = (src === 'admission') ? '' : 'none';
      if (_sheetListCache) populateSelectForSource(src);
      else loadSheets();
    });
  });

  async function loadSheet(key) {
    if (!key) { body.innerHTML = '<p class="hint">選一個分頁開始查閱。</p>'; return; }
    const { src, name } = decodeKey(key);
    setMsg('讀取 ' + name + ' …', 'ok');
    body.innerHTML = '<p class="hint">載入中…</p>';
    currentSheet = key;  // store full key so writes know the source
    try {
      // Date-shaped admission tab → structured viewer (main + ordering + sub-tables)
      if (src === 'admission' && isYmd(name)) {
        const r = await api(`/api/sheet/read?date=${encodeURIComponent(name)}`);
        if (r.error) { setMsg('✗ ' + r.error, 'err'); body.innerHTML = `<p class="viewer-empty">${esc(r.error)}</p>`; return; }
        render(r);
      } else {
        const r = await api(`/api/sheet/raw?name=${encodeURIComponent(name)}&source=${src}`);
        if (r.error) { setMsg('✗ ' + r.error, 'err'); body.innerHTML = `<p class="viewer-empty">${esc(r.error)}</p>`; return; }
        renderRaw(r);
      }
      const srcLabel = src === 'schedule' ? '📅 排班' : '📥 入院';
      setMsg(`✓ ${srcLabel} / ${name}（可直接編輯儲存格）`, 'ok');
    } catch (err) {
      setMsg('✗ ' + err.message, 'err');
      body.innerHTML = '<p class="viewer-empty">讀取失敗。</p>';
    }
  }

  link.addEventListener('click', (e) => {
    e.preventDefault();
    modal.hidden = false;
    if (!select.options.length || select.options[0].value === '') loadSheets();
  });
  if (close) close.addEventListener('click', () => { modal.hidden = true; });
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.hidden = true; });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.hidden) modal.hidden = true;
  });
  select.addEventListener('change', () => loadSheet(select.value));
  refresh.addEventListener('click', () => loadSheets());

  // ---- batch-delete date worksheets (admission YYYYMMDD only) ----
  function renderDeletePanel() {
    const adm = (_sheetListCache &&
      (_sheetListCache.admission || _sheetListCache.sheets)) || [];
    const dates = adm.filter(isYmd).sort((a, b) => b.localeCompare(a));
    if (!dates.length) {
      body.innerHTML = '<p class="viewer-empty">入院 Sheet 目前沒有可刪除的日期分頁。</p>';
      return;
    }
    const today = todayYmd();
    const rows = dates.map(d =>
      `<label class="del-row"><input type="checkbox" class="del-chk" value="${d}">` +
      `<span>${d}${d === today ? '　← 今天' : ''}</span></label>`).join('');
    body.innerHTML = `
      <div class="viewer-section del-panel">
        <h3>🗑 批次刪除日期分頁（入院 Sheet）</h3>
        <p class="del-warn">⚠ 刪除後<b>無法復原</b> — 整個日期分頁的入院名單、入院序、子表格都會一起消失。
          這裡只列出 YYYYMMDD 日期分頁；設定類分頁（抽籤表 / 下拉選單 / 值班總數統計…）與排班 Sheet 不會被刪。</p>
        <div class="del-tools">
          <button type="button" id="del-all">全選</button>
          <button type="button" id="del-none">全不選</button>
          <button type="button" id="del-go" class="btn-warn">🗑 刪除勾選的分頁</button>
        </div>
        <div class="del-list">${rows}</div>
      </div>`;
    const chks = () => Array.from(body.querySelectorAll('.del-chk'));
    body.querySelector('#del-all').addEventListener('click',
      () => chks().forEach(c => { c.checked = true; }));
    body.querySelector('#del-none').addEventListener('click',
      () => chks().forEach(c => { c.checked = false; }));
    body.querySelector('#del-go').addEventListener('click', async () => {
      const chosen = chks().filter(c => c.checked).map(c => c.value);
      if (!chosen.length) { setMsg('沒有勾選任何分頁', 'err'); return; }
      const preview = chosen.length > 12
        ? chosen.slice(0, 12).join('、') + ` …（共 ${chosen.length} 個）`
        : chosen.join('、');
      if (!confirm(`確定刪除這 ${chosen.length} 個日期分頁嗎？此動作無法復原：\n\n${preview}`)) return;
      if (chosen.includes(todayYmd()) &&
          !confirm('⚠ 你勾選的分頁包含「今天」，確定要連今天一起刪掉？')) return;
      setMsg('刪除中…', 'ok');
      try {
        const fd = new FormData();
        fd.append('names_json', JSON.stringify(chosen));
        const r = await api('/api/sheet/delete', { method: 'POST', body: fd });
        const okN = (r.deleted || []).length;
        const fails = r.failed || [];
        _sheetListCache = null;        // force a fresh tab list
        await loadSheets();
        renderDeletePanel();           // re-render the now-shorter list
        if (fails.length) {
          const why = fails.map(f => `${f.name}（${f.reason}）`).join('；');
          setMsg(`✓ 已刪 ${okN} 個；✗ ${fails.length} 個未刪：${why}`, 'err');
        } else {
          setMsg(`✓ 已刪除 ${okN} 個日期分頁`, 'ok');
        }
      } catch (err) {
        setMsg('✗ ' + err.message, 'err');
      }
    });
    setMsg(`批次刪除：共 ${dates.length} 個日期分頁可選`, 'ok');
  }

  if (delBtn) {
    delBtn.addEventListener('click', () => {
      if (_currentSrc !== 'admission') {
        setMsg('批次刪除只支援入院 Sheet 的日期分頁', 'err');
        return;
      }
      if (_sheetListCache) renderDeletePanel();
      else loadSheets().then(renderDeletePanel);
    });
  }
})();


// ---------- Multi-source upstream check (runs on every page) ----------
// 3 個來源：self（本 App）/ admission（入院清單上游）/ schedule（排班+Key 班上游）
// 啟動時打 /api/update/check_all → 渲染 topbar 的 upstream panel；任一來源
// 有更新時顯示 toggle 按鈕；點同步按鈕後在背景跑 /api/update/sync/<name>。
(async function () {
  const bar = document.getElementById('upstream-bar');
  if (!bar) return;
  const toggleBtn = document.getElementById('upstream-toggle');
  const countEl   = document.getElementById('upstream-count');
  const panel     = document.getElementById('upstream-panel');

  toggleBtn.addEventListener('click', () => {
    panel.hidden = !panel.hidden;
  });

  function setRowStatus(name, htmlFrag, hasUpdate, info) {
    const row = bar.querySelector(`.upstream-row[data-source="${name}"]`);
    if (!row) return;
    const status = row.querySelector('.upstream-status');
    const btn    = row.querySelector('.upstream-sync');
    status.innerHTML = htmlFrag;
    if (hasUpdate) {
      btn.hidden = false;
      btn.title = (info && info.remote && info.remote.message) || '';
      row.classList.add('has-update');
    } else {
      btn.hidden = true;
      row.classList.remove('has-update');
    }
  }

  function describe(info) {
    if (!info) return '檢查中…';
    if (info.error) return `<span class="upstream-err">無法檢查：${info.error}</span>`;
    const cur = (info.current && info.current.short) || (info.current && info.current.source === 'uncloned' ? '未下載' : '?');
    const rem = (info.remote && info.remote.short) || '?';
    if (info.available) {
      const n = (info.new_commits || []).length;
      const msg = (info.remote && info.remote.message) || '';
      return `<span class="upstream-new">🔔 ${cur} → ${rem}${n ? ` (${n} 個新 commit)` : ''}</span>` +
             (msg ? `<div class="upstream-msg">${escapeHtml(msg)}</div>` : '');
    }
    return `<span class="upstream-ok">✓ 已是最新 (${cur})</span>`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;',
    }[c]));
  }

  async function refresh() {
    try {
      const r = await fetch('/api/update/check_all').then(x => x.json());
      if (!r.ok || !r.sources) return;
      let updates = 0;
      for (const name of ['self', 'admission', 'schedule']) {
        const info = r.sources[name];
        setRowStatus(name, describe(info), !!(info && info.available), info);
        if (info && info.available) updates++;
      }
      if (updates > 0) {
        countEl.textContent = String(updates);
        toggleBtn.hidden = false;
      } else {
        toggleBtn.hidden = true;
      }
      return r.sources;
    } catch (_) {
      // offline / rate-limited — silent
      for (const name of ['self', 'admission', 'schedule']) {
        setRowStatus(name, '<span class="upstream-err">離線或限流</span>', false, null);
      }
    }
  }

  bar.addEventListener('click', async (ev) => {
    const btn = ev.target.closest('.upstream-sync');
    if (!btn) return;
    const name = btn.dataset.source;
    const labelEl = btn.parentElement.querySelector('.upstream-label');
    const friendly = labelEl ? labelEl.textContent : name;
    if (!confirm(`同步「${friendly}」？\n` +
                 (name === 'self'
                   ? '會在本 repo 跑 git pull --ff-only，需要乾淨工作樹。同步後 App 會自動重啟。'
                   : '會把該上游 clone/pull 到 external/ 資料夾，並把白名單裡的資料檔案 mirror 到 app/data/static/。')
    )) return;
    btn.disabled = true;
    const orig = btn.textContent;
    btn.textContent = '同步中…';
    try {
      const fd = new FormData();
      if (name === 'self') fd.append('restart', 'yes');
      const resp = await fetch(`/api/update/sync/${name}`, { method: 'POST', body: fd })
        .then(x => x.json());
      if (resp.ok) {
        if (name === 'self') {
          alert(`本 App 更新 ${resp.from || '?'} → ${resp.to || '?'} 成功，自動重啟中（2 秒後刷新）`);
          setTimeout(() => location.reload(), 2500);
        } else {
          const mirrored = (resp.mirrored || []).length;
          const np = (resp.needs_port || []).length;
          alert(`${friendly} 同步成功，HEAD = ${resp.to || '?'}\n` +
                `自動 mirror ${mirrored} 個資料檔；上游另有 ${np} 個檔案需要開發者手動 port（不影響執行）。`);
          await refresh();
        }
      } else {
        alert(`${friendly} 同步失敗：${resp.message || '未知錯誤'}`);
      }
    } catch (e) {
      // For self-sync, the server kills itself right after sending the
      // response. If fetch errors with "Failed to fetch" / "NetworkError",
      // that typically means update succeeded but the socket was reset
      // before the browser read the body. Treat as expected — offer reload.
      const msg = String(e && e.message || e);
      const isLikelyRestart = name === 'self' && /Failed to fetch|NetworkError|aborted|ERR_/i.test(msg);
      if (isLikelyRestart) {
        alert('本 App 更新流程已啟動，server 重啟中。\n' +
              '按確定後刷新頁面以載入新版（若無變化代表更新沒成功，請看下方訊息）。\n\n' +
              `原始錯誤：${msg}`);
        setTimeout(() => location.reload(), 1500);
      } else {
        alert(`${friendly} 同步失敗：${e}`);
      }
    } finally {
      btn.disabled = false;
      btn.textContent = orig;
    }
  });

  await refresh();
})();


const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

async function api(url, { method = 'GET', body = null } = {}) {
  const opts = { method };
  if (body instanceof FormData) opts.body = body;
  else if (body) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(url, opts);
  const j = await r.json().catch(() => ({ ok: false, detail: 'bad json' }));
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
}

function flash(el, msg, kind = 'ok') {
  if (!el) return;
  // Remember the most recent error so the 🐞 回報問題 modal can auto-fill it.
  if (kind === 'err' && msg) {
    try { window.__lastError = String(msg).slice(0, 2000); } catch (_) {}
  }
  el.textContent = msg;
  el.className = 'msg ' + kind;
  setTimeout(() => { if (el.textContent === msg) el.textContent = ''; }, 5000);
}

// Wrap an async block with button-loading state.
// Disables the button, swaps its label to `busyText` (with spinner via CSS),
// and restores everything (text + disabled state) when the work resolves/throws.
// Use inside click handlers AFTER any confirm() so cancelled confirms don't flicker.
async function withBusy(btn, busyText, fn) {
  if (!btn) return await fn();
  const origText = btn.textContent;
  const wasDisabled = btn.disabled;
  btn.disabled = true;
  btn.classList.add('busy');
  btn.textContent = busyText;
  try {
    return await fn();
  } finally {
    btn.textContent = origText;
    btn.disabled = wasDisabled;
    btn.classList.remove('busy');
  }
}

// ============================ settings page ============================

if (document.getElementById('settings-form')) {
  const PROVIDER_HELP = {
    anthropic: 'Claude API key 取得：https://console.anthropic.com/ → API Keys',
    openai:    'OpenAI API key 取得：https://platform.openai.com/api-keys',
    gemini:    'Gemini API key 取得（免費 tier 可用）：https://aistudio.google.com/app/apikey',
  };
  const sel = $('#llm_provider');
  const help = $('#provider-help');
  const geminiInfo = $('#gemini-info');
  const updateHelp = () => {
    help.textContent = PROVIDER_HELP[sel.value] || '';
    if (geminiInfo) geminiInfo.hidden = sel.value !== 'gemini';
  };
  sel.addEventListener('change', updateHelp);
  updateHelp();

  $('#settings-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await api('/api/settings', { method: 'POST', body: fd });
      flash($('#save-msg'), '✓ 已儲存', 'ok');
    } catch (err) {
      flash($('#save-msg'), '✗ ' + err.message, 'err');
    }
  });

  $('#test-btn').addEventListener('click', async () => {
    await withBusy($('#test-btn'), '測試中…', async () => {
      const out = $('#test-output');
      out.innerHTML = '<em>測試中…</em>';
      try {
        const r = await api('/api/settings/test');
        out.innerHTML = renderConnTest(r);
      } catch (err) {
        out.textContent = err.message;
      }
    });
  });
}

function renderConnTest(r) {
  const labels = { llm: 'LLM', sheet: '入院 Sheet', schedule_sheet: '排班 Sheet' };
  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const blocks = [];
  for (const [key, b] of Object.entries(r)) {
    if (!b) continue;
    const label = labels[key] || key;
    if (b.ok) {
      const detail = b.reply ? `（回應：${esc(b.reply)}）` : (b.msg ? '：' + esc(b.msg) : '');
      blocks.push(`<div class="conn-block ok"><strong>✓ ${esc(label)} 連線正常</strong>${detail}</div>`);
    } else {
      const err = b.msg || b.error || '(未知錯誤)';
      const h = b.hint;
      let body = '';
      if (h) {
        const sugg = (h.suggestions || []).map(s => `<li>${esc(s)}</li>`).join('');
        body = `
          <div class="conn-hint-title">💡 ${esc(h.title)}</div>
          <div class="conn-hint-cause">${esc(h.cause)}</div>
          <div class="conn-hint-fix">建議處理方式：</div>
          <ol class="conn-hint-list">${sugg}</ol>
          <details class="conn-raw"><summary>原始錯誤訊息（給開發者看的）</summary><pre>${esc(err)}</pre></details>
        `;
      } else {
        body = `<pre class="conn-raw-pre">${esc(err)}</pre>`;
      }
      blocks.push(`<div class="conn-block bad"><strong>✗ ${esc(label)} 連線失敗</strong>${body}</div>`);
    }
  }
  return blocks.join('');
}

// ============================ workflow page ============================

if (document.querySelector('.stepper')) {
  // step switcher
  $$('.step').forEach(s => s.addEventListener('click', () => {
    $$('.step').forEach(x => x.classList.remove('active'));
    s.classList.add('active');
    const i = s.dataset.step;
    $$('.panel').forEach(p => p.classList.toggle('hidden', p.dataset.panel !== i));
  }));

  // default date = today (Taipei), format YYYYMMDD
  const now = new Date();
  const tp = new Date(now.getTime() + (now.getTimezoneOffset() + 480) * 60000);
  const y = tp.getFullYear();
  const m = String(tp.getMonth() + 1).padStart(2, '0');
  const d = String(tp.getDate()).padStart(2, '0');
  $('#date-input').value = `${y}${m}${d}`;
  setupDateInputs();

  setupStep1();
  setupStep2();
  setupStep3();
  setupStep4();
  setupStep5();
  setupStep6();
  setupFormatCheck();
  setupFinalizeCheck();
  setupLoadExisting();
  setupRebuildSubtables();
}

// ---------- 🔧 Smart rebuild sub-tables (rescue path) ----------
function setupRebuildSubtables() {
  const btn = document.getElementById('rebuild-subtables-btn');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    const msg  = $('#rebuild-msg');
    if (!date) return flash(msg, '請先填日期（或載入既有日期）', 'err');
    if (!confirm(`確定要依主表 A-L 順序重建 ${date} 的所有子表格嗎？\n\n` +
                 `會做：去重複 doctor block、合併最完整資料、重排順序。\n` +
                 `保留：EMR / 術前診斷 / 預計心導管 / 註記 / 備註(住服) / 手動入院序。\n` +
                 `丟棄：不在主表 A-L 的子表病人（孤兒）。\n\n` +
                 `主表 A-L 完全不會動。`)) return;
    await withBusy(btn, '重建中…', async () => {
      try {
        const fd = new FormData();
        fd.append('date', date);
        const r = await api('/api/step2/rebuild_subtables', { method: 'POST', body: fd });
        const orphans = (r.dropped_orphans || []);
        let txt = `✓ 重建完成：${r.doctor_count} 位醫師 / ${r.patient_count} 位病人；` +
                  `${r.preserved_with_data} 位 EMR 資料保留`;
        if (orphans.length) txt += `；丟棄 ${orphans.length} 位孤兒（${orphans.slice(0, 3).join(',')}${orphans.length > 3 ? '…' : ''}）`;
        if (r.ordering_update && r.ordering_update.updated)
          txt += `；入院序同步 ${r.ordering_update.rows} 列`;
        flash(msg, txt, 'ok');
      } catch (err) {
        flash(msg, '✗ ' + err.message, 'err');
      }
    });
  });
}

// ---------- 📂 Load existing date sheet (skip OCR, hydrate from Sheet) ----------
function setupLoadExisting() {
  const sel  = $('#load-existing-select');
  const btn  = $('#load-existing-btn');
  const refr = $('#load-existing-refresh');
  const msg  = $('#load-existing-msg');
  if (!sel || !btn) return;

  async function refresh() {
    try {
      const r = await api('/api/sheet/list');
      const adm = (r.admission || r.sheets || [])
        .filter(s => /^\d{8}$/.test(s))
        .sort((a, b) => b.localeCompare(a));
      const today = (() => {
        const n = new Date();
        const tp = new Date(n.getTime() + (n.getTimezoneOffset() + 480) * 60000);
        return `${tp.getFullYear()}${String(tp.getMonth()+1).padStart(2,'0')}${String(tp.getDate()).padStart(2,'0')}`;
      })();
      sel.innerHTML = ['<option value="">— 選一個日期 —</option>']
        .concat(adm.map(d => `<option value="${d}"${d === today ? ' selected' : ''}>${d}</option>`))
        .join('');
      flash(msg, `${adm.length} 個日期分頁`, 'ok');
    } catch (err) {
      flash(msg, '✗ ' + err.message, 'err');
    }
  }

  // Map main A-L cells back into the OCR row shape so renderOcrTable can show
  // them in the editable Step 1 table. Order matches OCR_COLS / SUB_HEADER.
  function mainCellsToOcrRow(cells) {
    const arr = Array.isArray(cells) ? cells : [];
    const c = arr.concat(new Array(12).fill('')).slice(0, 12).map(x => (x == null ? '' : String(x)));
    return {
      admit_date:    c[0],  op_date:       c[1],
      department:    c[2],  doctor:        c[3],
      icd_diagnosis: c[4],  name:          c[5],
      gender:        c[6],  age:           c[7],
      chart_no:      c[8],  bed:           c[9],
      hint:          c[10], urgent:        c[11],
    };
  }

  // Reconstruct Step 3 EMR result cards from sub-table rows so 載入既有日期
  // also surfaces previously-fetched EMR text + auto-detected F/G. Each
  // sub-table row carries: [name, chart_no, c_text(EMR), summary?, manual,
  // diagnosis(F), cathlab(G), note(H), house(I)] in cols 0..8.
  // Note: `s.rows` from /api/sheet/read is now PATIENT ROWS ONLY (server-side
  // strip; see renderSub comment). first_patient_row is the sheet row of rows[0].
  function subsToEmrResults(subs) {
    const out = [];
    (subs || []).forEach(s => {
      const doc = s.doctor || '';
      const firstPatientRow = s.first_patient_row || ((s.title_row || 0) + 2);
      (s.rows || []).forEach((row, i) => {
        const c   = (row || []).map(x => (x == null ? '' : String(x)));
        const name   = c[0] || '';
        const chart  = c[1] || '';
        if (!name && !chart) return;  // skip blank patient rows
        const cText  = c[2] || '';
        const fDiag  = c[5] || '';
        const gCath  = c[6] || '';
        const hNote  = c[7] || '';   // H 註記
        const iHouse = c[8] || '';   // I 備註(住服)
        // Parse "<age> y/o <gender>\n..." prefix from c_text if present
        let age = null, gender = '';
        const m = cText.match(/^(\d+)\s+y\/o\s+([男女])\s*\n/);
        if (m) { age = parseInt(m[1]); gender = m[2]; }
        out.push({
          chart_no: chart, name: name, doctor: doc,
          c_text: cText, f: fDiag, g: gCath, note: hNote, house: iHouse,
          age: age, gender: gender, emr_name: '',
          has_record: !!cText && !cText.includes('查無') && !cText.includes('INPATIENT'),
          row: firstPatientRow + i,  // sheet row (1-indexed)
          error: '',
        });
      });
    });
    return out;
  }

  btn.addEventListener('click', async () => {
    const date = sel.value;
    if (!date) { flash(msg, '先選一個日期', 'err'); return; }
    await withBusy(btn, '載入中…', async () => {
      try {
        const r = await api(`/api/sheet/read?date=${encodeURIComponent(date)}`);
        if (r.error) { flash(msg, '✗ ' + r.error, 'err'); return; }

        // 1) Set date input + sync date picker + weekday auto-update
        $('#date-input').value = date;
        $('#date-input').dispatchEvent(new Event('change'));

        // 2) Step 1: render main A-L as editable OCR table
        const mainRows = (r.main || []).filter(row =>
          (row || []).some(c => (c || '').toString().trim()));
        ocrRows = mainRows.map(mainCellsToOcrRow);
        renderOcrTable(ocrRows);
        $('#write1-btn').disabled = ocrRows.length === 0;

        // 3) Step 3: rebuild EMR result cards from sub-table C/F/G so user
        //    can review/edit prior EMR work without re-fetching the browser.
        const emrResults = subsToEmrResults(r.subs || []);
        let renderedEmr = 0;
        if (emrResults.length && typeof renderEmrResults === 'function') {
          await renderEmrResults(emrResults, {});
          renderedEmr = emrResults.length;
          // Auto-feed the ② EMR panel preview + JSON textarea so re-run picks
          // the same list. (renderStep2AutofillPreview also syncs the textarea.)
          step2Ordered = emrResults.map(p => ({
            chart_no: p.chart_no, name: p.name, doctor: p.doctor,
          }));
          renderStep2AutofillPreview(step2Ordered);
        }

        // 4) Trigger sub-table read so the F/G editor populates the (possibly
        //    hidden) Step 4 panel. We do NOT switch tabs — per user request,
        //    loading should leave them on whichever step is currently active.
        if ($('#load4-btn')) {
          $('#load4-btn').click();
        }

        const subCount = (r.subs || []).length;
        const ordCount = (r.ordering || []).filter(row =>
          (row || []).some(c => (c || '').toString().trim())).length;
        const withEmr = emrResults.filter(p => p.c_text).length;
        flash(msg,
          `✓ 載入 ${date}：主表 ${ocrRows.length} 位、子表格 ${subCount} 位醫師、` +
          `EMR ${renderedEmr}/${withEmr} 位（已渲染/有資料）、入院序 ${ordCount} 列。`,
          'ok');
      } catch (err) {
        flash(msg, '✗ ' + err.message, 'err');
      }
    });
  });

  if (refr) refr.addEventListener('click', refresh);
  refresh();
}

// ---------- Date picker + auto weekday ----------
// Two synced inputs: a native <input type="date"> for the calendar
// picker and the existing text input for YYYYMMDD manual entry.
// Both drive the weekday <select>, which shows the *next day's*
// weekday (= 開刀日, the day the lottery table is keyed by).
function setupDateInputs() {
  const text   = $('#date-input');
  const picker = $('#date-picker');
  const week   = $('#weekday');
  if (!text || !picker || !week) return;

  const WEEK_LABELS = ['週日', '週一', '週二', '週三', '週四', '週五', '週六'];

  const ymdToIso  = (s) => /^\d{8}$/.test(s) ? `${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)}` : '';
  const isoToYmd  = (s) => /^\d{4}-\d{2}-\d{2}$/.test(s) ? s.replace(/-/g, '') : '';

  function nextDayWeekdayLabel(ymd) {
    if (!/^\d{8}$/.test(ymd)) return '';
    const y = Number(ymd.slice(0, 4));
    const m = Number(ymd.slice(4, 6)) - 1;
    const d = Number(ymd.slice(6, 8));
    const dt = new Date(Date.UTC(y, m, d + 1));
    if (isNaN(dt.getTime())) return '';
    return WEEK_LABELS[dt.getUTCDay()];
  }

  function syncFromText() {
    const ymd = text.value.trim();
    picker.value = ymdToIso(ymd);
    const label = nextDayWeekdayLabel(ymd);
    // Only set weekday if next day is Mon-Fri (dropdown has no Sat/Sun).
    week.value = ['週一','週二','週三','週四','週五'].includes(label) ? label : '';
  }

  function syncFromPicker() {
    const ymd = isoToYmd(picker.value);
    if (ymd) text.value = ymd;
    syncFromText();
  }

  text.addEventListener('input',  syncFromText);
  text.addEventListener('change', syncFromText);
  picker.addEventListener('change', syncFromPicker);

  // Initial: text input already populated to today's YYYYMMDD above;
  // mirror into picker + autofill weekday.
  syncFromText();
}


// ---------- Format check ----------
const FMT_LABELS = {
  main_header_missing:     '主資料 A-L 表頭錯誤',
  order_header_wrong:      '入院序 N-V 表頭錯誤',
  sub_header_wrong:        '子表格表頭錯誤（A-I 標題列）',
  subtable_count_mismatch: '子表格人數標題與實際不符',
  gap_too_small:           '子表格間空白行不足（< 2）',
  subtable_missing_title:  '子表格缺少標題（姓名列前沒有 X（N人））',
  chart_text_format:       '病歷號欄位格式',
  duplicate_doctor_block:        '同一位醫師有重複的子表格 block',
  subtable_orphan_chart:         '子表格病人不在主表 A-L',
  main_chart_missing_from_subtable: '主表 A-L 病人缺少對應子表格列',
  subtable_doctor_not_in_main:   '子表格醫師主表 A-L 沒有對應病人',
  subtable_doctor_mismatch:      '主表 vs 子表格 主治醫師不一致',
};

function setupFormatCheck() {
  let lastIssues = [];
  $('#fmt-check-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    if (!date) return flash($('#fmt-msg'), '請先填日期', 'err');
    await withBusy($('#fmt-check-btn'), '檢查中…', async () => {
    flash($('#fmt-msg'), '檢查中…', 'ok');
    try {
      const r = await api(`/api/format/check?date=${encodeURIComponent(date)}`);
      if (r.error) {
        flash($('#fmt-msg'), '✗ ' + r.error, 'err');
        $('#fmt-output').innerHTML = '';
        $('#fmt-fix-btn').disabled = true;
        return;
      }
      lastIssues = r.issues || [];
      renderFormatIssues(lastIssues);
      const fixable = lastIssues.filter(i => i.fixable);
      if (!lastIssues.length) {
        flash($('#fmt-msg'), '✓ 格式正常', 'ok');
      } else {
        flash($('#fmt-msg'),
          `發現 ${lastIssues.length} 項問題（可自動修正 ${fixable.length} 項）`,
          fixable.length ? 'ok' : 'err');
      }
      $('#fmt-fix-btn').disabled = fixable.length === 0;
    } catch (err) {
      flash($('#fmt-msg'), '✗ ' + err.message, 'err');
    }
    });
  });

  $('#fmt-fix-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    if (!date) return;
    const types = [...new Set(lastIssues.filter(i => i.fixable).map(i => i.type))];
    // Always include chart_text_format — it's safe repeatCell formatting
    if (!types.includes('chart_text_format')) types.push('chart_text_format');
    await withBusy($('#fmt-fix-btn'), '修正中…', async () => {
    flash($('#fmt-msg'), '修正中…', 'ok');
    const fd = new FormData();
    fd.append('date', date);
    fd.append('types', types.join(','));
    try {
      const r = await api('/api/format/fix', { method: 'POST', body: fd });
      flash($('#fmt-msg'),
        `✓ 修正 ${r.applied.length} 項，剩餘 ${r.remaining_issues.length} 項`,
        r.remaining_issues.length === 0 ? 'ok' : 'err');
      lastIssues = r.remaining_issues || [];
      renderFormatIssues(lastIssues);
      $('#fmt-fix-btn').disabled = lastIssues.filter(i => i.fixable).length === 0;
    } catch (err) {
      flash($('#fmt-msg'), '✗ ' + err.message, 'err');
    }
    });
  });
}

// ---------- Finalize (定案) readiness check ----------
function setupFinalizeCheck() {
  $('#final-check-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    if (!date) return flash($('#final-msg'), '請先填日期', 'err');
    await withBusy($('#final-check-btn'), '檢查中…', async () => {
      flash($('#final-msg'), '檢查中…', 'ok');
      try {
        const r = await api(`/api/finalize/check?date=${encodeURIComponent(date)}`);
        if (r.error) {
          flash($('#final-msg'), '✗ ' + r.error, 'err');
          $('#final-output').innerHTML = '';
          return;
        }
        renderFinalizeChecks(r.checks);
        flash($('#final-msg'),
          r.ready ? '✓ 全部通過，可以進 Step 5/6' : '✗ 尚未達到定案條件',
          r.ready ? 'ok' : 'err');
      } catch (err) {
        flash($('#final-msg'), '✗ ' + err.message, 'err');
      }
    });
  });
}

function renderFinalizeChecks(checks) {
  const esc = s => String(s || '').replace(/</g, '&lt;');
  const items = checks.map(c => {
    const icon = c.ok ? '✓' : '✗';
    const cls = c.ok ? 'final-ok' : 'final-fail';
    const detail = c.detail ? ` <span class="hint">— ${esc(c.detail)}</span>` : '';
    return `<li class="${cls}"><strong>${icon}</strong> ${esc(c.label)}${detail}</li>`;
  }).join('');
  $('#final-output').innerHTML = `<ul class="final-checks">${items}</ul>`;
}

function renderFormatIssues(issues) {
  const host = $('#fmt-output');
  if (!issues.length) { host.innerHTML = ''; return; }
  const esc = s => String(s || '').replace(/</g, '&lt;');
  const items = issues.map(i => {
    const label = FMT_LABELS[i.type] || i.type;
    const tag = i.fixable ? '' : ' <span class="hint">（需手動）</span>';
    let detail = '';
    if (i.type === 'subtable_count_mismatch') {
      detail = ` — ${esc(i.doctor)}（標題寫 ${i.declared}，實際 ${i.actual}，第 ${i.title_row} 列）`;
    } else if (i.type === 'gap_too_small') {
      detail = ` — ${esc(i.doctor)} 前 ${i.gap} 空白（第 ${i.title_row} 列，需補 ${i.need_insert}）`;
    } else if (i.type === 'subtable_missing_title') {
      detail = ` — 第 ${i.subheader_row} 列`;
    } else if (i.type === 'duplicate_doctor_block') {
      detail = ` — ${esc(i.doctor)} 出現 ${i.count} 次（第 ${(i.rows||[]).join('、')} 列）→ 用「🔧 重建子表格」合併`;
    } else if (i.type === 'subtable_orphan_chart') {
      detail = ` — ${esc(i.doctor)} / ${esc(i.name)} (${esc(i.chart_no)})，第 ${i.row} 列 → 用「🔧 重建子表格」自動丟掉`;
    } else if (i.type === 'main_chart_missing_from_subtable') {
      detail = ` — ${esc(i.doctor)} / ${esc(i.name)} (${esc(i.chart_no)})，主表第 ${i.row} 列 → 用「🔧 重建子表格」補進去`;
    } else if (i.type === 'subtable_doctor_not_in_main') {
      detail = ` — ${esc(i.doctor)}（第 ${i.title_row} 列）→ 用「🔧 重建子表格」移除`;
    } else if (i.type === 'subtable_doctor_mismatch') {
      detail = ` — ${esc(i.name)} (${esc(i.chart_no)}) 主表=${esc(i.main_doctor)} vs 子表=${esc(i.sub_doctor)} → 用「🔧 重建子表格」以主表為準`;
    } else if (i.type === 'sub_header_wrong') {
      detail = ` — ${esc(i.doctor)}（第 ${i.row} 列）`;
    }
    return `<li class="fmt-${i.fixable ? 'fixable' : 'manual'}">${label}${detail}${tag}</li>`;
  }).join('');
  host.innerHTML = `<ul class="fmt-issues">${items}</ul>`;
}

// ---------- Step 1: OCR ----------
let ocrRows = [];

// Parse "YYYY/MM/DD", "YYYY-MM-DD", "MM/DD" (current year) → "YYYYMMDD".
// Returns '' if input doesn't look like a date.
function normalizeAdmitDateToYmd(raw) {
  const s = (raw || '').trim();
  if (!s) return '';
  let m = s.match(/^(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})$/);
  if (m) {
    const [, y, mo, d] = m;
    return `${y}${mo.padStart(2, '0')}${d.padStart(2, '0')}`;
  }
  m = s.match(/^(\d{1,2})[\/\-](\d{1,2})$/);
  if (m) {
    const [, mo, d] = m;
    const y = new Date().getUTCFullYear();
    return `${y}${mo.padStart(2, '0')}${d.padStart(2, '0')}`;
  }
  m = s.match(/^(\d{8})$/);  // already YYYYMMDD
  if (m) return s;
  return '';
}

function pickMostCommonAdmitDate(rows) {
  const tally = {};
  for (const r of (rows || [])) {
    const ymd = normalizeAdmitDateToYmd(r && r.admit_date);
    if (ymd) tally[ymd] = (tally[ymd] || 0) + 1;
  }
  let best = '', bestCount = 0;
  for (const [k, v] of Object.entries(tally)) {
    if (v > bestCount) { best = k; bestCount = v; }
  }
  return best;
}

function setupStep1() {
  const dz = $('#drop-zone');
  const fi = $('#file-input');
  const preview = $('#preview');
  let currentFile = null;

  const showFile = (f) => {
    currentFile = f;
    const reader = new FileReader();
    reader.onload = (e) => { preview.src = e.target.result; preview.style.display = 'block'; };
    reader.readAsDataURL(f);
    $('#ocr-btn').disabled = false;
  };

  dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('active'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('active'));
  dz.addEventListener('drop', (e) => {
    e.preventDefault(); dz.classList.remove('active');
    const f = e.dataTransfer.files[0];
    if (f) showFile(f);
  });
  fi.addEventListener('change', () => { if (fi.files[0]) showFile(fi.files[0]); });
  // Paste support
  document.addEventListener('paste', (e) => {
    const it = [...e.clipboardData.items].find(i => i.type.startsWith('image/'));
    if (it) showFile(it.getAsFile());
  });

  $('#ocr-btn').addEventListener('click', async () => {
    if (!currentFile) return;
    await withBusy($('#ocr-btn'), '辨識中…', async () => {
      flash($('#ocr-msg'), 'LLM 辨識中（可能需 10-30 秒）…', 'ok');
      const fd = new FormData();
      fd.append('image', currentFile);
      try {
        const r = await api('/api/step1/ocr', { method: 'POST', body: fd });
        ocrRows = r.rows;
        renderOcrTable(ocrRows);
        // Auto-fill date-input from OCR admit_date (most-common value across
        // rows). User asked not to manually re-type the calendar each time.
        const autoDate = pickMostCommonAdmitDate(ocrRows);
        let dateNote = '';
        if (autoDate) {
          const dateText = $('#date-input');
          if (dateText) {
            dateText.value = autoDate;
            dateText.dispatchEvent(new Event('change'));
          }
          dateNote = `；日期自動填入 ${autoDate}`;
        }
        flash($('#ocr-msg'), `✓ 辨識到 ${ocrRows.length} 筆${dateNote}`, 'ok');
        $('#write1-btn').disabled = ocrRows.length === 0;
      } catch (err) {
        flash($('#ocr-msg'), '✗ ' + err.message, 'err');
      }
    });
  });

  $('#write1-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    if (!date) return flash($('#ocr-msg'), '請先填日期', 'err');
    const rows = collectOcrTable();
    // Snapshot the OCR/loaded baseline at submission time so manual edits
    // can be diffed server-side (cells where final ≠ baseline = user edits).
    const baseline = (ocrRows || []).map(r => ({...r}));
    await withBusy($('#write1-btn'), '比對中…', async () => {
      await step1Write(date, rows, /* allowOverwrite */ false, baseline);
    });
  });
}

// After any Step 1 write, re-read the freshest sub-table state from the sheet
// so step2Ordered (= Step 3 EMR's patient list) always reflects what's actually
// on the sheet — never a stale cache from an earlier write. Critical when the
// user fixes a wrong OCR value (chart_no / doctor / 姓名) in the OCR table
// before clicking 寫入: the previous step2Ordered carries the WRONG value;
// without this refresh, Step 3 would still query EMR with the wrong chart_no.
async function refreshStep2FromSheet(date) {
  if (!date) return;
  try {
    const st = await api('/api/step4/subtables?date=' + encodeURIComponent(date));
    const flat = [];
    for (const [doc, pts] of Object.entries(st.tables || {})) {
      for (const p of (pts || [])) {
        if ((p.chart_no || '').trim()) {
          flat.push({
            chart_no: p.chart_no.trim(),
            name: (p.name || '').trim(),
            doctor: doc,
          });
        }
      }
    }
    if (flat.length) {
      step2Ordered = flat;
      renderStep2AutofillPreview(flat);
    }
  } catch (_) { /* sheet read failed — leave preview as-is */ }
}

async function step1Write(date, rows, allowOverwrite, originalRows) {
  const fd = new FormData();
  fd.append('date', date);
  fd.append('rows', JSON.stringify(rows));
  fd.append('allow_overwrite', allowOverwrite ? 'yes' : 'no');
  if (originalRows) fd.append('original_rows', JSON.stringify(originalRows));
  try {
    const r = await api('/api/step1/write', { method: 'POST', body: fd });
    if (r.needs_confirm) {
      // Existing sheet — show diff preview and ask for confirmation
      const confirmed = await showStep1DiffAndConfirm(r);
      if (confirmed) {
        await step1Write(date, rows, true, originalRows);
      } else {
        flash($('#ocr-msg'), '取消寫入（已保留舊資料）', 'ok');
      }
    } else if (r.unchanged) {
      // Re-uploaded screenshot, same patients → nothing added/removed.
      // We deliberately wrote NOTHING so every keyed value is preserved.
      const dc = (r.diff && r.diff.doctor_changed) || [];
      const dcNote = dc.length
        ? `（偵測到 ${dc.length} 位主治醫師在新截圖不同，依設定維持原狀，未自動更動）`
        : '';
      flash($('#ocr-msg'),
        `✓ 名單沒有新增或減少 — 維持原狀，沒有覆蓋任何已輸入的資料${dcNote}`,
        'ok');
      // Still refresh step2Ordered — a previous session may have left a
      // stale list cached, and the user opening Step 3 next would query
      // EMR with whatever was cached, not what's actually on the sheet.
      await refreshStep2FromSheet(date);
    } else {
      // Membership changed (someone added / removed) OR manual edit overlay
      // applied. Kept patients' rows were preserved verbatim; only new rows
      // appended / removed dropped / overlay cells patched.
      // Try build_subtables (idempotent: server refuses if they already exist).
      let subNote = '';
      let buildOk = false;
      try {
        const fd2 = new FormData();
        fd2.append('date', date);
        const sr = await api('/api/step2/build_subtables', { method: 'POST', body: fd2 });
        const docCount = (sr.doctors || []).length;
        if (sr.patients && sr.patients.length) {
          step2Ordered = sr.patients;
          renderStep2AutofillPreview(sr.patients);
          buildOk = true;
        }
        if (docCount) subNote = `；子表格已建 ${docCount} 位醫師`;
      } catch (_) { /* sub-tables already exist or doctor list empty — fine */ }
      // ALWAYS reconcile step2Ordered against the live sheet after a write.
      // If the user fixed a wrong OCR value (chart_no / doctor / 姓名) in the
      // Step 1 table, the build_subtables response can be stale — re-read
      // from /api/step4/subtables which reflects the post-write state.
      if (!buildOk) await refreshStep2FromSheet(date);
      const nAdd = (r.diff && r.diff.added || []).length;
      const nDel = (r.diff && r.diff.removed || []).length;
      const parts = [];
      if (nAdd) parts.push(`新增 ${nAdd} 人`);
      if (nDel) parts.push(`移除 ${nDel} 人`);
      const chg = parts.length ? parts.join('、') : '已更新';
      flash($('#ocr-msg'),
        `✓ 名單已更新（${chg}）；其他病人原本輸入的資料保持不動${subNote}`,
        'ok');
    }
  } catch (err) {
    flash($('#ocr-msg'), '✗ ' + err.message, 'err');
  }
}

function showStep1DiffAndConfirm(diff) {
  // Render a mini diff table inside #ocr-msg-diff and return a Promise<boolean>
  const host = $('#ocr-msg-diff') || (() => {
    const div = document.createElement('div');
    div.id = 'ocr-msg-diff';
    $('#ocr-msg').insertAdjacentElement('afterend', div);
    return div;
  })();

  const esc = s => String(s || '').replace(/</g, '&lt;');
  const rowHtml = (cls, label, items) => {
    if (!items || !items.length) return '';
    const lis = items.map(p => {
      const extra = p.old && p.new
        ? ` <span class="hint">${esc(p.old)} → ${esc(p.new)}</span>`
        : (p.doctor ? ` <span class="hint">${esc(p.doctor)}</span>` : '');
      return `<li>${esc(p.chart_no)} ${esc(p.name || '')}${extra}</li>`;
    }).join('');
    return `<div class="diff-block ${cls}"><h4>${label}（${items.length}）</h4><ul>${lis}</ul></div>`;
  };

  host.innerHTML = `
    <div class="diff-wrap">
      <p><strong>⚠ 此日期 sheet 已有 ${diff.existing_count} 位病人，本次新截圖 ${diff.new_count} 位。</strong></p>
      ${rowHtml('added',   '新增',   diff.added)}
      ${rowHtml('removed', '取消',   diff.removed)}
      ${rowHtml('changed', '換醫師', diff.doctor_changed)}
      <p class="hint">確認後：A-L 主資料覆蓋為新清單；**子表格自動跟著動**（取消的列刪除、新增的病人掛到對應主治、換醫師的列搬到新醫師），新列 術前診斷 / 預計心導管 留白待 ② EMR 擷取填。<strong>入院序仍不會自動更新</strong> — 動到病人數量請手動重跑 ② EMR + ③ 入院序整合。</p>
      <button id="diff-confirm-btn" class="primary">確認覆蓋</button>
      <button id="diff-cancel-btn">取消</button>
    </div>
  `;

  return new Promise(resolve => {
    $('#diff-confirm-btn').addEventListener('click', () => {
      host.innerHTML = '';
      resolve(true);
    });
    $('#diff-cancel-btn').addEventListener('click', () => {
      host.innerHTML = '';
      resolve(false);
    });
  });
}

const OCR_COLS = [
  ['admit_date', '實際住院日'], ['op_date', '開刀日'],
  ['department', '科別'], ['doctor', '主治醫師'],
  ['icd_diagnosis', '主診斷ICD'], ['name', '姓名'],
  ['gender', '性別'], ['age', '年齡'],
  ['chart_no', '病歷號'], ['bed', '病床'],
  ['hint', '入院提示'], ['urgent', '住急'],
];

function renderOcrTable(rows) {
  const wrap = $('#ocr-table-wrap');
  if (!rows.length) { wrap.innerHTML = '<p class="hint">沒有資料</p>'; return; }
  const head = OCR_COLS.map(c => `<th>${c[1]}</th>`).join('');
  const body = rows.map((r, i) => '<tr>' + OCR_COLS.map(([k]) =>
    `<td><input data-row="${i}" data-col="${k}" value="${(r[k] || '').replace(/"/g, '&quot;')}"></td>`
  ).join('') + '</tr>').join('');
  wrap.innerHTML = `<table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function collectOcrTable() {
  const inputs = $$('#ocr-table-wrap input');
  const rows = [];
  inputs.forEach(inp => {
    const ri = +inp.dataset.row;
    rows[ri] = rows[ri] || {};
    rows[ri][inp.dataset.col] = inp.value;
  });
  return rows.filter(r => r && (r.name || '').trim());
}

// ---------- Step 2: Build sub-tables (no lottery here) ----------
let step2Ordered = [];  // flat patient list from main A-L, used as Step 3 EMR default

function setupStep2() {
  $('#build2-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    if (!date) return flash($('#s2-msg'), '請填日期', 'err');
    await withBusy($('#build2-btn'), '生成 subtable 中…', async () => {
      flash($('#s2-msg'), '依主表順序產生 subtable…', 'ok');
      const fd = new FormData();
      fd.append('date', date);
      try {
        const r = await api('/api/step2/build_subtables', { method: 'POST', body: fd });
        step2Ordered = r.patients || [];
        renderStep2Subtables(r.doctors || []);
        flash($('#s2-msg'),
          `✓ 已寫入 ${r.range}（${r.doctors.length} 位醫師、共 ${step2Ordered.length} 位病人）`, 'ok');
      } catch (err) {
        flash($('#s2-msg'), '✗ ' + err.message, 'err');
        $('#s2-output').innerHTML = '';
      }
    });
  });
}

function renderStep2Subtables(doctors) {
  const esc = s => String(s || '').replace(/</g, '&lt;');
  const html = doctors.map(d => {
    const rows = (d.patients || []).map((p, i) =>
      `<tr><td>${i + 1}</td><td>${esc(p.name)}</td><td>${esc(p.chart_no)}</td></tr>`).join('');
    return `<div class="doctor-block"><h3>${esc(d.doctor)}（${d.count}人）</h3>
      <table class="data"><thead><tr><th>#</th><th>姓名</th><th>病歷號</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
  }).join('');
  $('#s2-output').innerHTML = html || '<p class="hint">沒有可寫入的醫師資料</p>';
}

// Render the auto-fed patient preview shown above the ② EMR textarea so the
// user can eyeball who's about to be fetched without parsing the JSON.
// Also keeps the JSON textarea in sync so a re-run picks the same list.
function renderStep2AutofillPreview(patients) {
  const preview = document.getElementById('emr-patients-preview');
  const ta = document.getElementById('emr-patients');
  if (!preview) return;
  if (!patients || !patients.length) {
    preview.innerHTML = '';
    return;
  }
  // Also pin to the JSON textarea so #run3-btn click uses this exact list.
  if (ta) {
    ta.value = JSON.stringify(
      patients.map(p => ({
        chart_no: p.chart_no, name: p.name, doctor: p.doctor,
      })), null, 0);
  }
  const esc = s => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  const rows = patients.map((p, i) =>
    `<tr><td>${i + 1}</td><td>${esc(p.doctor || '')}</td>` +
    `<td>${esc(p.name || '')}</td><td>${esc(p.chart_no || '')}</td></tr>`
  ).join('');
  preview.innerHTML =
    `<div style="background:#ecfdf5;border:1px solid #10b981;color:#065f46;` +
    `padding:8px 12px;border-radius:6px;margin:8px 0;font-weight:600">` +
    `✓ 已自動帶入 ${patients.length} 位病人（按「開始擷取」即可開跑）` +
    `</div>` +
    `<div style="max-height:180px;overflow-y:auto;border:1px solid #e2e8f0;` +
    `border-radius:6px;margin-bottom:8px">` +
    `<table class="data" style="margin:0">` +
    `<thead><tr><th>#</th><th>主治</th><th>姓名</th><th>病歷號</th></tr></thead>` +
    `<tbody>${rows}</tbody></table></div>`;
}


// ---------- Step 3: EMR ----------
function setupStep3() {
  $('#run3-btn').addEventListener('click', async () => {
    const url = $('#session-url').value.trim();
    let patients;
    const raw = $('#emr-patients').value.trim();
    const date = $('#date-input').value.trim();
    if (raw) {
      try { patients = JSON.parse(raw); }
      catch { return flash($('#s3-msg'), '病人 JSON 格式錯誤', 'err'); }
    } else if (step2Ordered.length) {
      patients = step2Ordered;
    } else if (date) {
      // No explicit list and nothing cached from this session's Step 1 →
      // pull the patient list straight from the date's sub-tables on the
      // Sheet (Step 1 already built them). Covers page-reload / fresh entry.
      try {
        const st = await api('/api/step4/subtables?date=' + encodeURIComponent(date));
        const flat = [];
        for (const [doc, pts] of Object.entries(st.tables || {}))
          for (const p of (pts || []))
            if ((p.chart_no || '').trim())
              flat.push({ chart_no: p.chart_no.trim(),
                          name: (p.name || '').trim(), doctor: doc });
        patients = flat;
        step2Ordered = flat;   // cache for re-runs this session
      } catch (_) { /* fall through to the clearer errors below */ }
    }
    if (!url)
      return flash($('#s3-msg'), '請貼上 EMR session URL（先在瀏覽器登入 EMR 再把查詢頁網址貼過來）', 'err');
    if (!patients || !patients.length)
      return flash($('#s3-msg'), '找不到病人清單 — 請先完成 ① 匯入名單（會自動建子表格）', 'err');

    // Show cancel button while the long EMR batch runs.
    const cancelBtn = $('#cancel3-btn');
    const opId = `step3_${date || 'no-date'}`;
    let currentOpId = opId;
    if (cancelBtn) {
      cancelBtn.style.display = '';
      cancelBtn.onclick = async () => {
        cancelBtn.disabled = true;
        cancelBtn.textContent = '取消中…';
        try {
          const fd = new FormData();
          fd.append('op_id', currentOpId);
          await api('/api/op/cancel', { method: 'POST', body: fd });
          flash($('#s3-msg'), '已請求取消 — 等目前這位跑完後停止', 'ok');
        } catch (e) {
          cancelBtn.disabled = false;
          cancelBtn.textContent = '✕ 取消擷取';
        }
      };
    }
    await withBusy($('#run3-btn'), `EMR 擷取中… (${patients.length} 位)`, async () => {
      flash($('#s3-msg'), `擷取中… (${patients.length} 位)`, 'ok');
      const fd = new FormData();
      fd.append('session_url', url);
      fd.append('patients_json', JSON.stringify(patients));
      fd.append('date', date);
      fd.append('admission_date', date);
      try {
        const r = await api('/api/step3/run', { method: 'POST', body: fd });
        currentOpId = r.op_id || currentOpId;
        await renderEmrResults(r.results, r.main_fixes || {});
        const wb = r.writeback || {};
        const missing = (wb.missing || []).length;
        let skippedNote;
        let level = 'ok';
        if (wb.error) {
          skippedNote = `；⚠ 寫回失敗：${wb.error}`;
          level = 'err';
        } else if (wb.skipped) {
          skippedNote = '（未寫回 — 缺日期）';
        } else {
          const autoBuilt = wb.auto_built ? '（已自動建立子表格）' : '';
          const skippedFetchN = r.skipped_existing || 0;
          const skippedFetchNote = skippedFetchN
            ? `，跳過抓取 ${skippedFetchN} 位（Sheet 已有資料）` : '';
          skippedNote = `；寫回子表格 ${wb.written} 位${autoBuilt}${skippedFetchNote}` +
            (missing ? `，${missing} 位查無子表格` : '');
        }
        // Append main A-L 修正 summary
        const mf = r.main_fixes || {};
        if (mf.fixes && mf.fixes.length) {
          skippedNote += `；主表更正 ${mf.fixes.length} 處 (姓名/性別/年齡)`;
        }
        const cancelNote = r.canceled ? '（已取消，剩餘未跑）' : '';
        flash($('#s3-msg'),
          `✓ 完成 ${r.results.length} 位${cancelNote}${skippedNote}`,
          r.canceled ? 'err' : level);
      } catch (err) {
        flash($('#s3-msg'), '✗ ' + err.message, 'err');
      } finally {
        if (cancelBtn) {
          cancelBtn.style.display = 'none';
          cancelBtn.disabled = false;
          cancelBtn.textContent = '✕ 取消擷取';
        }
      }
    });
  });
}

async function renderEmrResults(results, mainFixes) {
  const escape = s => String(s == null ? '' : s).replace(/</g, '&lt;').replace(/"/g, '&quot;');
  const opts = await ensureFgOptions();
  // One shared datalist per page; render once at the top of the Step 3 area.
  const datalists = fgDatalist('fg-f-list', opts.f) + fgDatalist('fg-g-list', opts.g);

  // Main A-L 修正摘要區（EMR → 主治醫師/姓名/性別/年齡 autofix）
  const FIELD_LABELS = {doctor: '主治醫師', name: '姓名', gender: '性別', age: '年齡'};
  let fixesHtml = '';
  if (mainFixes && Array.isArray(mainFixes.fixes) && mainFixes.fixes.length) {
    const rows = mainFixes.fixes.map(f =>
      `<tr><td>${escape(f.chart_no)}</td><td>${escape(FIELD_LABELS[f.field] || f.field)}</td>` +
      `<td class="old">${escape(f.old) || '(空)'}</td>` +
      `<td>→</td><td class="new">${escape(f.new)}</td></tr>`).join('');
    fixesHtml = `<div class="emr-fix-list">
      <h4>📝 EMR 自動更正主表 (${mainFixes.fixes.length} 處)</h4>
      <table class="data"><thead><tr><th>病歷號</th><th>欄位</th><th>原</th><th></th><th>新</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
  } else if (mainFixes && mainFixes.skipped === false) {
    fixesHtml = `<p class="hint">📝 主表主治醫師/姓名/性別/年齡均符合 EMR，無需更正。</p>`;
  }

  const cards = results.map(r => {
    const demog = (r.age != null && r.gender) ? `${r.age} y/o ${r.gender}` : '';
    // 姓名 follows EMR; strip the OCR "?" uncertainty mark so it never shows.
    const ocrName = String(r.name || '').replace(/[?？]+\s*$/, '').trim();
    const dispName = (r.emr_name || '').trim() || ocrName;
    const emrName = r.emr_name && r.emr_name !== ocrName
      ? `<span class="emr-name-fix">(原名單：${escape(ocrName)})</span>` : '';
    const visit = r.visit_label ? `<span class="hint">[訪視: ${escape(r.visit_label)}]</span>` : '';
    const noRecord = r.has_record === false;
    // Long SOAP/病程 body is collapsible so the page isn't endless after
    // the user has read it. No-record message is short → left as-is.
    const body = noRecord
      ? `<p class="msg err" style="margin:6px 0">⚠ ${escape(r.c_text) || '查無 EMR'}</p>`
      : `<details class="emr-body" open>
           <summary>EMR 內容（點此收合 / 展開）</summary>
           <pre>${escape(r.c_text)}</pre>
         </details>`;
    // F/G editable: row comes from /api/step3/run enrichment (sub-table lookup).
    // If row is missing (patient not in any sub-table), still render read-only.
    const fgEditor = (r.row)
      ? `<span class="emr-fg-edit">
            術前診斷: ${fgInput(6, r.f, r.row, opts.f, 'fg-f-list')}
            預計心導管: ${fgInput(7, r.g, r.row, opts.g, 'fg-g-list')}
            註記: ${noteInput(r.note, r.row)}
            備註(住服): ${houseInput(r.house, r.row)}
         </span>`
      : `<span class="emr-fg">術前診斷=${escape(r.f) || '—'} / 預計心導管=${escape(r.g) || '—'} <span class="hint">(無 row, 不可編輯)</span></span>`;
    const isNew = !!r.is_new_this_session;
    const isSkipped = !!r.skipped_existing;
    const badge = isNew
      ? `<span class="emr-badge emr-badge-new" title="本次擷取新增的病人">🆕 本次新增</span>`
      : (isSkipped
         ? `<span class="emr-badge emr-badge-skip" title="Sheet 已有資料，未重新抓取 EMR">📄 沿用 Sheet 既有資料</span>`
         : '');
    const cardCls = 'emr-card'
      + (noRecord ? ' emr-no-record' : '')
      + (isNew ? ' emr-card-new' : '')
      + (isSkipped ? ' emr-card-skipped' : '');
    return `
    <div class="${cardCls}" data-chart="${escape(r.chart_no)}">
      <h3>${escape(r.doctor)} / ${escape(dispName)} ${emrName} (${escape(r.chart_no)}) ${badge} ${r.error ? '⚠' : ''}</h3>
      ${r.error ? `<p class="msg err">${escape(r.error)}</p>` : ''}
      <p class="hint">${escape(demog)} &nbsp; ${visit}</p>
      <div class="emr-fg-row">${fgEditor}</div>
      ${body}
    </div>`;
  }).join('');

  // 全部收合 / 展開 — lets the user fold every EMR body at once after
  // reviewing so the page stays short.
  const collapseBar = cards
    ? `<div class="emr-collapse-bar">
         <button type="button" id="emr-collapse-all">▸ 全部收合</button>
         <button type="button" id="emr-expand-all">▾ 全部展開</button>
       </div>`
    : '';
  $('#emr-results').innerHTML = datalists + fixesHtml + collapseBar + cards;
  const _setAllEmrBodies = (open) =>
    $('#emr-results').querySelectorAll('details.emr-body')
      .forEach(d => { d.open = open; });
  const _cAll = $('#emr-collapse-all'), _eAll = $('#emr-expand-all');
  if (_cAll) _cAll.addEventListener('click', () => _setAllEmrBodies(false));
  if (_eAll) _eAll.addEventListener('click', () => _setAllEmrBodies(true));

  // Bidirectional sync: when user saves F/G here, push the value into the
  // matching Step 4 sub-table input (by row+col) without refetching.
  wireFgInputsIn('#emr-results', '#s3-msg', (savedInp) => {
    const row = savedInp.dataset.row;
    const col = savedInp.dataset.col;
    const val = savedInp.value;
    document.querySelectorAll(
      `#subtables-wrap input.fg-input[data-row="${row}"][data-col="${col}"]`
    ).forEach(target => {
      target.value = val;
      target.dataset.original = val;
    });
  });
}

// ---------- Step 4: Ordering ----------
function setupStep4() {
  $('#load4-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    if (!date) return flash($('#s4-msg'), '請填日期', 'err');
    await withBusy($('#load4-btn'), '讀取中…', async () => {
      flash($('#s4-msg'), '讀取子表格中…', 'ok');
      try {
        const r = await api(`/api/step4/subtables?date=${date}`);
        renderSubtables(r.tables);
        flash($('#s4-msg'), `✓ ${Object.keys(r.tables).length} 位醫師子表格`, 'ok');
        $('#lottery4-btn').disabled = false;
        $('#integrate4-btn').disabled = false;
      } catch (err) {
        flash($('#s4-msg'), '✗ ' + err.message, 'err');
      }
    });
  });

  // After 抽籤 / 整合, read the written 入院序 (N-W) back from the Sheet and
  // show it on screen so the user can eyeball the order without opening the
  // Sheet or the 查閱 modal.
  const ORDER_COLS = ['序號','主治醫師','病人姓名','備註(住服)','備註',
                      '病歷號','術前診斷','預計心導管','改期'];
  async function renderOrderResult(date) {
    const box = $('#order-result');
    if (!box) return;
    box.innerHTML = '<p class="hint">讀取入院序…</p>';
    try {
      const r = await api(`/api/sheet/read?date=${encodeURIComponent(date)}`);
      // r.ordering[i] = sheet row i+1 (row 1 = header). Keep the absolute sheet
      // row so the editable 備註(住服) cell can write straight back.
      const rows = (r.ordering || [])
        .map((row, i) => ({ cells: row || [], sheetRow: i + 1 }))
        .slice(1)
        .filter(o => o.cells.some(c => (c || '').toString().trim()));
      if (!rows.length) { box.innerHTML = '<p class="hint">（入院序無資料）</p>'; return; }
      const esc = s => String(s == null ? '' : s)
        .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
      const thead = '<tr>' + ORDER_COLS.map(h => `<th>${esc(h)}</th>`).join('') + '</tr>';
      // 備註(住服) = ORDER_COLS index 3 → Sheet col Q (col 17). Editable + synced.
      const tbody = rows.map(o => '<tr>' + ORDER_COLS.map((_, c) => {
        const v = esc(o.cells[c] || '');
        if (c === 3) {
          return `<td class="ord-q-edit" contenteditable="true" data-row="${o.sheetRow}" `
               + `data-col="17" title="點一下可編輯，離開欄位自動存回 Google Sheet">${v}</td>`;
        }
        return `<td>${v}</td>`;
      }).join('') + '</tr>').join('');
      box.innerHTML =
        `<h3 style="margin:14px 0 6px">入院序結果（${rows.length} 位）` +
        `<span class="hint" style="font-weight:400;font-size:12px">　• 備註(住服) 可直接點擊修改，離開欄位即存回 Sheet</span></h3>` +
        `<div style="overflow-x:auto"><table class="data order-result-table">` +
        `<thead>${thead}</thead><tbody>${tbody}</tbody></table></div>`;
      // Wire the editable 備註(住服) cells → /api/step4/cell on blur / Enter.
      box.querySelectorAll('td.ord-q-edit').forEach(td => {
        let orig = td.textContent;
        const save = async () => {
          const val = td.textContent.trim();
          if (val === orig.trim()) return;
          td.classList.remove('saved', 'save-err');
          td.classList.add('saving');
          try {
            const fd = new FormData();
            fd.append('date', date);
            fd.append('row', td.dataset.row);
            fd.append('col', td.dataset.col);
            fd.append('value', val);
            await api('/api/step4/cell', { method: 'POST', body: fd });
            orig = val;
            td.classList.remove('saving'); td.classList.add('saved');
            setTimeout(() => td.classList.remove('saved'), 1500);
          } catch (err) {
            td.classList.remove('saving'); td.classList.add('save-err');
            flash($('#s4-msg'), '✗ 備註(住服) 存回失敗：' + err.message, 'err');
          }
        };
        td.addEventListener('blur', save);
        td.addEventListener('keydown', e => {
          if (e.key === 'Enter') { e.preventDefault(); td.blur(); }
        });
      });
    } catch (err) {
      box.innerHTML = `<p class="msg err">讀取入院序失敗：${err.message}</p>`;
    }
  }

  $('#lottery4-btn').addEventListener('click', async () => {
    const date    = $('#date-input').value.trim();
    const weekday = $('#weekday').value;
    if (!date) return flash($('#s4-msg'), '請填日期', 'err');
    const { patient_pins, doctor_pins } = pinsForPayload();
    if (!confirm(
      '這會用主治醫師抽籤表（依星期）+ pin 設定，重寫 N-V。\n' +
      '原 N-V 內容會被覆蓋（含 Q 住服、V 改期欄）。確定繼續？'
    )) return;
    await withBusy($('#lottery4-btn'), '抽籤中…', async () => {
      flash($('#s4-msg'), '抽籤 + 寫入 N-V…', 'ok');
      const fd = new FormData();
      fd.append('date', date);
      fd.append('weekday', weekday);
      fd.append('patient_pins_json', JSON.stringify(patient_pins));
      fd.append('doctor_pins_json',  JSON.stringify(doctor_pins));
      try {
        const r = await api('/api/step4/lottery', { method: 'POST', body: fd });
        const tix = (r.ticket_doctors || []).join('、') || '（無）';
        const groups = r.doctor_groups || {};
        const order = (r.doctor_order || []).map((d, i) => {
          const g = groups[d] === '時段組' ? '🟦 時段組' : '🟧 非時段組';
          return `${i + 1}. ${d} ${g}`;
        }).join(' / ');
        flash($('#s4-msg'),
          `✓ ${r.range}（病人 pin ${r.pinned_patients} / 醫師 pin ${r.pinned_doctors}；抽籤表 ${weekday}：${tix}）` +
          (order ? `\n醫師抽序：${order}` : ''), 'ok');
        await renderOrderResult(date);
        // Prepend a prominent warning banner above the result table if the
        // lottery couldn't read tickets for the given weekday. Done AFTER
        // renderOrderResult so the table render doesn't wipe it.
        if (r.warning) {
          const box = $('#order-result');
          if (box) {
            const banner = document.createElement('div');
            banner.style.cssText = 'background:#fef3c7;border:2px solid #f59e0b;' +
              'color:#92400e;padding:12px;margin:8px 0;font-weight:bold;border-radius:6px';
            banner.textContent = '⚠️ ' + r.warning;
            box.prepend(banner);
          }
        }
      } catch (err) {
        flash($('#s4-msg'), '✗ ' + err.message, 'err');
      }
    });
  });

  $('#integrate4-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    const fd = new FormData();
    fd.append('date', date);
    await withBusy($('#integrate4-btn'), '整合中…', async () => {
      flash($('#s4-msg'), '整合 N-W 中…', 'ok');
      try {
        const r = await api('/api/step4/integrate', { method: 'POST', body: fd });
        const appended = (r.appended || []);
        const addNote = appended.length
          ? `（補進 ${appended.length} 位原本不在入院序的病人：` +
            appended.map(a => `${a.doctor} ${a.name}`).join('、') + '）'
          : '';
        flash($('#s4-msg'), `✓ 已整合 ${r.rows} 筆到 ${r.range}${addNote}`, 'ok');
        await renderOrderResult(date);
      } catch (err) {
        flash($('#s4-msg'), '✗ ' + err.message, 'err');
      }
    });
  });
}

// ---------- Step 5: Cathlab ----------
function setupStep5() {
  const out = () => $('#s5-output');

  // attribute-safe escape for editable input values
  const esc = s => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');

  // Display-layer safety net: strip the OCR uncertainty mark / replacement
  // glyph so the user never sees 「翁潘淑琴?」 in Step 5, regardless of what
  // the sheet sub-table or an older build wrote. Backend already strips on
  // read (cathlab_service.read_patients) — this just guarantees the UI too.
  const cleanName = s => String(s == null ? '' : s)
    .replace(/[?？�⁇‽]+\s*$/u, '').trim();
  const escName = s => esc(cleanName(s));

  // Convert "YYYY/MM/DD" → "YYYY-MM-DD" for <input type="date">
  const toIsoDate = s => {
    const m = String(s || '').match(/^(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})/);
    return m ? `${m[1]}-${m[2].padStart(2,'0')}-${m[3].padStart(2,'0')}` : '';
  };
  const renderPlan = (plan, skipped) => {
    const blocks = Object.entries(plan).map(([d, pts]) => {
      const body = pts.map(p => {
        const diagCell = p.diag_id ? `${p.diag_label} <span class="hint">[${p.diag_id}]</span>` : `<span class="err">${p.diag || '—'}（無對應 ID）</span>`;
        const procCell = p.proc_id ? `${p.proc_label} <span class="hint">[${p.proc_id}]</span>` : (p.cath ? `<span class="err">${p.cath}（無對應 ID → 進備註）</span>` : '—');
        const isOff = (p.in_schedule === false || p.session === 'OFF');
        const curSess = isOff ? '非時段' : (p.session || '');
        const ov = f => `data-chart="${esc(p.chart)}" data-field="${f}" class="plan-ov"`;
        const opt = v => `<option${curSess === v ? ' selected' : ''}>${v}</option>`;
        // 排 checkbox — default checked (will key in). User unchecks to skip.
        const skipCell = `<label class="skip-cell" title="取消勾選＝這位病人不 key in 排程"><input type="checkbox" ${ov('skip_inverted')} checked> 排</label>`;
        // 導管日期 — editable so user can shift a single patient to a different day
        const cathDateCell = `<input type="date" ${ov('cath_date')} value="${esc(toIsoDate(p.cath_date))}" style="width:140px" title="想把這位病人改到別天 key in (例如隔兩日)，直接改這裡">`;
        const sessionCell = `<select ${ov('session')} data-doctor="${esc(p.doctor)}">${opt('AM')}${opt('PM')}${opt('非時段')}</select>`;
        const secondInput = secondDoctorCombobox(p.chart, p.second_doctor || '');
        const curRoom = (p.room || '').trim();
        const roomList = ['H1', 'H2', 'C1', 'C2'];
        const roomOpts = (roomList.includes(curRoom) || !curRoom ? roomList : [curRoom, ...roomList])
          .map(rm => `<option${rm === curRoom ? ' selected' : ''}>${esc(rm)}</option>`).join('');
        const roomCell = `<select ${ov('room')}>${roomOpts}</select>`;
        const timeCell = `<input ${ov('time')} value="${esc(p.time || '')}" style="width:54px">`;
        const noteCell = `<input ${ov('note_out')} value="${esc(p.note_out || '')}" style="width:100%;min-width:140px">`;
        return `<tr><td>${p.seq}</td><td>${skipCell}</td><td>${cathDateCell}</td><td>${esc(p.doctor)}<br>${secondInput}</td><td>${escName(p.name)}</td><td>${esc(p.chart)}</td><td>${sessionCell}</td><td>${roomCell}</td><td>${timeCell}</td><td>${diagCell}</td><td>${procCell}</td><td>${noteCell}</td></tr>`;
      }).join('');
      return `<h3>${d} — ${pts.length} 位</h3><table class="data plan-table"><thead><tr><th>#</th><th>排</th><th>導管日期</th><th>主治 / 第二主治</th><th>姓名</th><th>病歷</th><th>時段</th><th>房</th><th>時間</th><th>術前診斷</th><th>預計心導管</th><th>註記</th></tr></thead><tbody>${body}</tbody></table>`;
    }).join('');
    const skips = skipped.length ? `<h3>不排（跳過）${skipped.length} 位</h3><ul>${skipped.map(p => `<li>${esc(p.doctor)} ${escName(p.name)} (${esc(p.chart)}) — ${esc(p.note)}</li>`).join('')}</ul>` : '';
    const editHint = blocks ? `<p class="hint">✎ <b>排</b>欄取消勾選＝這位病人不 key in（例：本院醫師臨時要改日期）。<b>導管日期</b>可直接改成想 key 的那天（例：某位要排到隔兩日）。其他時段 / 房 / 時間 / 第二主治 / 註記 也都可改，改完按「③ 開始 key in 排程」會用修改後的值寫入 WEBCVIS（術前診斷／預計心導管請回「③ 入院序整合」那一步改）。改「時段」會自動帶入時間（AM 06xx / PM 18xx / 非時段 21xx，同醫師當日依序 +1 分），需要時再微調。</p>` : '';
    return editHint + blocks + skips;
  };

  // 第二主治 combobox: input + ▼ + popup. Free-text typing still allowed
  // (overlay from 主治醫師導管時段表 may pre-fill any doctor; user can override
  // to a name not in the preset list). Preset = the 5 doctors who most often
  // appear as second per the user's 2026-05-21 request.
  const SECOND_DOCTOR_OPTIONS = ['蘇奕嘉', '葉建寬', '葉立浩', '許毓軨', '洪晨惠'];
  function secondDoctorCombobox(chart, value) {
    const esc = s => String(s || '').replace(/</g, '&lt;').replace(/"/g, '&quot;');
    const optsAttr = esc(JSON.stringify(SECOND_DOCTOR_OPTIONS));
    return `<span class="fg-cell second-doc-cell" data-options='${optsAttr}'>
      <input type="text" class="plan-ov second-doc-input fg-input" autocomplete="off"
             data-chart="${esc(chart)}" data-field="second_doctor"
             value="${esc(value)}" placeholder="第二主治" style="width:88px">
      <button type="button" class="fg-chev" tabindex="-1" title="展開選單">▼</button>
      <ul class="fg-popup" hidden></ul>
    </span>`;
  }
  function wireSecondDoctorCombos() {
    const scope = out();
    if (!scope) return;
    const closeAll = () => scope.querySelectorAll('.second-doc-cell ul.fg-popup')
      .forEach(p => { p.hidden = true; p.classList.remove('open'); });
    scope.querySelectorAll('span.second-doc-cell').forEach(cell => {
      const inp = cell.querySelector('input.second-doc-input');
      const btn = cell.querySelector('button.fg-chev');
      const popup = cell.querySelector('ul.fg-popup');
      if (!inp || !btn || !popup) return;
      let options = [];
      try { options = JSON.parse(cell.getAttribute('data-options') || '[]'); }
      catch (_) { options = []; }
      const buildList = (filter) => {
        const f = (filter || '').toLowerCase();
        const items = options.filter(o => !f || o.toLowerCase().includes(f));
        popup.innerHTML = items.map(o =>
          `<li tabindex="-1" data-val="${o.replace(/"/g, '&quot;')}">${o.replace(/</g, '&lt;')}</li>`
        ).join('') || '<li class="empty">（沒有符合的選項）</li>';
      };
      const open = (filterByValue) => {
        buildList(filterByValue ? inp.value : '');
        popup.hidden = false; popup.classList.add('open');
      };
      const close = () => { popup.hidden = true; popup.classList.remove('open'); };
      btn.addEventListener('mousedown', e => {
        e.preventDefault();
        if (!popup.hidden) { close(); return; }
        closeAll();
        open(false);  // ▼ click = show ALL
        inp.focus();
      });
      inp.addEventListener('input', () => {
        if (popup.hidden) { closeAll(); open(true); }
        else buildList(inp.value);
      });
      popup.addEventListener('mousedown', e => {
        const li = e.target.closest('li[data-val]');
        if (!li) return;
        e.preventDefault();
        inp.value = li.dataset.val;
        close();
        inp.dispatchEvent(new Event('change'));
        inp.focus();
      });
    });
    // Close on outside click (scoped to this widget only).
    document.addEventListener('mousedown', e => {
      if (!e.target.closest('.second-doc-cell')) closeAll();
    });
  }

  // Auto-fill 時間(+房) when the user changes a row's 時段, mirroring the
  // backend compute_time(): AM 0600+ / PM 1800+ / 非時段 2100+, +index where
  // index = preceding rows of the SAME doctor in that date table (matches
  // _enrich's per-(cath,doctor) counter, skips excluded from the table).
  const TIME_BASE = { AM: 6 * 60, PM: 18 * 60, '非時段': 21 * 60 };
  const wirePlanAuto = () => {
    out().querySelectorAll('select.plan-ov[data-field="session"]').forEach(sel => {
      sel.addEventListener('change', () => {
        const doctor = sel.dataset.doctor || '';
        const tr = sel.closest('tr'), tbody = sel.closest('tbody');
        if (!tr || !tbody) return;
        let idx = 0;
        for (const s of tbody.querySelectorAll('select.plan-ov[data-field="session"]')) {
          if (s === sel) break;
          if ((s.dataset.doctor || '') === doctor) idx++;
        }
        const base = TIME_BASE[sel.value];
        if (base != null) {
          const m = base + idx;
          const t = String(Math.floor(m / 60)).padStart(2, '0') +
                    String(m % 60).padStart(2, '0');
          const ti = tr.querySelector('input.plan-ov[data-field="time"]');
          if (ti) ti.value = t;
        }
        if (sel.value === '非時段') {
          const ri = tr.querySelector('select.plan-ov[data-field="room"]');
          if (ri) ri.value = 'H1';
        }
      });
    });
  };

  // Collect the user's manual edits from the dry-run (預覽排程) table — the
  // 排 checkbox, 導管日期, second doctor, etc. Shared by 對照 (verify) and
  // key in so un-checking 不排 in step 1 is honoured by BOTH later steps.
  const collectPlanOverrides = () => {
    const ov = {};
    const isoToSlash = s => String(s || '').replace(/-/g, '/');
    out().querySelectorAll('.plan-ov').forEach(el => {
      const c = el.dataset.chart, f = el.dataset.field;
      if (!c || !f) return;
      if (f === 'skip_inverted') {
        // checkbox checked = include = skip:false
        (ov[c] = ov[c] || {}).skip = !el.checked;
        return;
      }
      (ov[c] = ov[c] || {})[f] = (f === 'cath_date') ? isoToSlash(el.value) : el.value;
    });
    return ov;
  };

  $('#plan5-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    if (!date) return flash($('#s5-msg'), '請填日期', 'err');
    await withBusy($('#plan5-btn'), '產出計畫中…', async () => {
      flash($('#s5-msg'), '產出計畫中…', 'ok');
      try {
        const r = await api(`/api/step5/plan?date=${date}`);
        out().innerHTML = renderPlan(r.plan, r.skipped);
        wirePlanAuto();
        wireSecondDoctorCombos();
        flash($('#s5-msg'), '✓ 計畫已產出（未寫入 WEBCVIS）', 'ok');
      } catch (err) {
        flash($('#s5-msg'), '✗ ' + err.message, 'err');
      }
    });
  });

  $('#verify5-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    if (!date) return flash($('#s5-msg'), '請填日期', 'err');
    if (!confirm('這會開啟瀏覽器登入 WEBCVIS 查一遍現有排程（只查不寫），繼續？')) return;
    await withBusy($('#verify5-btn'), '比對中…', async () => {
    flash($('#s5-msg'), '登入 WEBCVIS 查詢中…', 'ok');
    const fd = new FormData(); fd.append('date', date);
    // Pass the preview table's 不排 toggles so 對照 honours them too.
    const ovV = collectPlanOverrides();
    if (Object.keys(ovV).length) fd.append('overrides', JSON.stringify(ovV));
    try {
      const r = await api('/api/step5/verify', { method: 'POST', body: fd });
      const ok  = r.found.map(p => `<tr class="ok"><td>✓ 已在排程</td><td>${p.cath_date}</td><td>${p.doctor}</td><td>${escName(p.name)}</td><td>${p.chart}</td></tr>`).join('');
      const bad = r.missing.map(p => `<tr class="bad"><td>✗ 還沒進排程</td><td>${p.cath_date}</td><td>${p.doctor}</td><td>${escName(p.name)}</td><td>${p.chart}</td></tr>`).join('');
      const skip = r.skipped.map(p => `<tr><td>${p.unexpected_present ? '⚠ 標記不排卻在排程裡' : '— 不排（跳過）'}</td><td>—</td><td>${p.doctor}</td><td>${escName(p.name)}</td><td>${p.chart}</td></tr>`).join('');
      out().innerHTML = `<p>已在排程 ${r.totals.ok} 位 / 還沒進排程 ${r.totals.missing} 位 / 不排 ${r.totals.skip} 位</p>
        <table class="data"><thead><tr><th>狀態</th><th>導管日期</th><th>主治</th><th>姓名</th><th>病歷</th></tr></thead>
        <tbody>${bad}${ok}${skip}</tbody></table>`;
      flash($('#s5-msg'), r.totals.missing ? `比對完成：還有 ${r.totals.missing} 位沒進排程` : '✓ 比對完成：應排的都已在排程裡', r.totals.missing ? 'err' : 'ok');
    } catch (err) {
      flash($('#s5-msg'), '✗ ' + err.message, 'err');
    }
    });
  });

  $('#keyin5-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    if (!date) return flash($('#s5-msg'), '請填日期', 'err');
    if (!confirm('這會開啟瀏覽器，實際把導管排程「寫進」WEBCVIS（先建立排程，再補上術前診斷與術式）。確定繼續？')) return;
    // Collect manual edits from the dry-run table (if a plan is on screen).
    // Special handling for the 排 checkbox (data-field=skip_inverted → skip=!checked)
    // and the 導管日期 input (input[type=date] returns YYYY-MM-DD → backend wants
    // YYYY/MM/DD for cath_date).
    const ov = collectPlanOverrides();
    // Show cancel button while keyin runs. op_id is computed from date,
    // matching the backend (`step5_{date}`).
    const cancelBtn5 = $('#cancel5-btn');
    const opId5 = `step5_${date}`;
    if (cancelBtn5) {
      cancelBtn5.style.display = '';
      cancelBtn5.onclick = async () => {
        if (!confirm('已寫入 WEBCVIS 的不會撤銷，只會停止後續這批沒跑到的。確定取消？')) return;
        cancelBtn5.disabled = true;
        cancelBtn5.textContent = '取消中…';
        try {
          const fd = new FormData();
          fd.append('op_id', opId5);
          await api('/api/op/cancel', { method: 'POST', body: fd });
          flash($('#s5-msg'), '已請求取消 — 等目前這筆 ADD/UPT 跑完後停止', 'ok');
        } catch (e) {
          cancelBtn5.disabled = false;
          cancelBtn5.textContent = '✕ 取消 key in';
        }
      };
    }
    await withBusy($('#keyin5-btn'), 'Key in 中…', async () => {
    flash($('#s5-msg'), '寫入 WEBCVIS 中…（會開瀏覽器）', 'ok');
    const fd = new FormData(); fd.append('date', date); fd.append('dry_run', 'no');
    if (Object.keys(ov).length) fd.append('overrides', JSON.stringify(ov));
    try {
      const r = await api('/api/step5/keyin', { method: 'POST', body: fd });
      const rMap = { ok: '✓ 成功', skip: '— 已存在，略過', error: '✗ 失敗' };
      const rCls = x => x === 'ok' ? 'ok' : (x === 'skip' ? '' : 'bad');
      const rTxt = x => rMap[x] || x;
      const addRows = (r.add || []).map(x => `<tr class="${rCls(x.result)}"><td>${rTxt(x.result)}</td><td>${escName(x.name)}</td><td>${x.chart}</td><td>${x.reason || ''}</td></tr>`).join('');
      const uptRows = (r.upt || []).map(x => `<tr class="${rCls(x.result)}"><td>${rTxt(x.result)}</td><td>${escName(x.name)}</td><td>${x.chart}</td><td>${x.reason || ''}</td></tr>`).join('');
      const missRows = (r.missing_after || []).map(x => `<tr class="bad"><td>✗ 沒寫進去</td><td>${escName(x.name)}</td><td>${x.chart}</td><td>${x.cath_date}</td><td>${esc(x.reason || '原因不明（請看詳細執行記錄）')}</td></tr>`).join('');
      out().innerHTML = `
        <h3>第一階段 — 建立排程（成功 ${r.summary.ok} / 已存在略過 ${r.summary.skip} / 失敗 ${r.summary.error}）</h3>
        <table class="data"><thead><tr><th>狀態</th><th>姓名</th><th>病歷</th><th>說明</th></tr></thead><tbody>${addRows}</tbody></table>
        <h3>第二階段 — 補上術前診斷與預計術式（${(r.upt || []).length} 筆）</h3>
        <table class="data"><thead><tr><th>狀態</th><th>姓名</th><th>病歷</th><th>說明</th></tr></thead><tbody>${uptRows || '<tr><td colspan=4>無（沒有需要補診斷／術式的病人）</td></tr>'}</tbody></table>
        ${missRows ? `<h3>key in 後再查一次：有 ${(r.missing_after||[]).length} 位沒寫進排程</h3><table class="data"><thead><tr><th>狀態</th><th>姓名</th><th>病歷</th><th>導管日期</th><th>原因</th></tr></thead><tbody>${missRows}</tbody></table>` : '<p class="ok">key in 後再查一次：應排的病人全部都在排程裡 ✓</p>'}
        <details class="hint"><summary>詳細執行記錄（除錯用）</summary><pre class="test-output">${(r.log || []).join('\n')}</pre></details>`;
      let baseMsg;
      if (r.canceled) {
        baseMsg = `⚠ 已取消（跑完 ${(r.add || []).length} 筆 ADD / ${(r.upt || []).length} 筆 UPT 後停止）`;
      } else if (r.summary.error) {
        baseMsg = `⚠ 有 ${r.summary.error} 位寫入失敗，請看上方表格`;
      } else {
        baseMsg = '✓ 排程已全部 key 進 WEBCVIS';
      }
      flash($('#s5-msg'), baseMsg, (r.canceled || r.summary.error) ? 'err' : 'ok');
    } catch (err) {
      flash($('#s5-msg'), '✗ ' + err.message, 'err');
    } finally {
      if (cancelBtn5) {
        cancelBtn5.style.display = 'none';
        cancelBtn5.disabled = false;
        cancelBtn5.textContent = '✕ 取消 key in';
      }
    }
    });
  });
}

// ---------- Step 6: LINE push ----------
function setupStep6() {
  $('#preview6-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    if (!date) return flash($('#s6-msg'), '請填日期', 'err');
    await withBusy($('#preview6-btn'), '預覽中…', async () => {
      flash($('#s6-msg'), '預覽 LINE 中…', 'ok');
      try {
        const r = await api(`/api/step6/preview?date=${date}`);
        $('#line-preview').textContent = r.text;
        flash($('#s6-msg'), '✓ 預覽完成（尚未推播）', 'ok');
      } catch (err) {
        flash($('#s6-msg'), '✗ ' + err.message, 'err');
      }
    });
  });

  $('#push6-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    if (!date) return flash($('#s6-msg'), '請填日期', 'err');
    if (!confirm(`確定推送 ${date} 的入院名單到 LINE group？`)) return;
    const fd = new FormData();
    fd.append('date', date);
    fd.append('group_id', $('#line-group').value);
    await withBusy($('#push6-btn'), '推送中…', async () => {
      flash($('#s6-msg'), '推送 LINE 中…', 'ok');
      try {
        const r = await api('/api/step6/push', { method: 'POST', body: fd });
        $('#line-preview').textContent = r.preview;
        flash($('#s6-msg'), `✓ 已推到 ${r.sent_to}（${r.length} 字）`, 'ok');
      } catch (err) {
        flash($('#s6-msg'), '✗ ' + err.message, 'err');
      }
    });
  });
}

// ---------- Step 4 pin panels (patient + doctor) ----------
// Patient pin = "this specific patient gets global 序號 N" (overrides RR).
// Doctor pin  = "this doctor is the N-th in the round-robin draw order".
// Pins persist in localStorage keyed by date so reloading the page keeps them.
const pinStorageKey = (date) => `pin_${date}`;
function loadPins() {
  const date = $('#date-input').value.trim();
  try {
    return JSON.parse(localStorage.getItem(pinStorageKey(date)) || '{}') || {};
  } catch (_) {
    return {};
  }
}
function savePins(patch) {
  const date = $('#date-input').value.trim();
  const cur = loadPins();
  Object.assign(cur, patch);
  localStorage.setItem(pinStorageKey(date), JSON.stringify(cur));
}
function pinsForPayload() {
  // Read live values from the rendered inputs (source of truth for the click)
  const patient_pins = {};
  $$('#pin-patient-wrap input[data-chart]').forEach(i => {
    const v = parseInt((i.value || '').trim(), 10);
    if (v > 0) patient_pins[i.dataset.chart] = v;
  });
  const doctor_pins = {};
  $$('#pin-doctor-wrap input[data-doc]').forEach(i => {
    const v = parseInt((i.value || '').trim(), 10);
    if (v > 0) doctor_pins[i.dataset.doc] = v;
  });
  return { patient_pins, doctor_pins };
}

function renderPinPanels(tables) {
  const esc = s => String(s || '').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  const saved = loadPins();
  const patPin = saved.patient_pins || {};
  const docPin = saved.doctor_pins  || {};

  const flat = [];
  Object.entries(tables).forEach(([doc, pts]) => {
    pts.forEach(p => flat.push({ doctor: doc, name: p.name, chart_no: p.chart_no }));
  });
  const patBody = flat.map(p => {
    const cur = patPin[p.chart_no] || '';
    return `<tr><td>${esc(p.name)}</td><td>${esc(p.chart_no)}</td><td>${esc(p.doctor)}</td>
      <td><input data-chart="${esc(p.chart_no)}" type="number" min="1" value="${esc(cur)}" placeholder="—" class="pin-input"></td></tr>`;
  }).join('');
  const patHtml = `<details class="pin-panel" ${Object.keys(patPin).length ? 'open' : ''}>
    <summary><strong>📌 病人入院序 pin</strong>（指定特定病人為第 N 位；空白 = 走抽籤）</summary>
    <table class="data"><thead><tr><th>姓名</th><th>病歷號</th><th>主治</th><th>第幾位</th></tr></thead>
    <tbody>${patBody}</tbody></table></details>`;

  const docBody = Object.entries(tables).map(([doc, pts]) => {
    const cur = docPin[doc] || '';
    return `<tr><td>${esc(doc)}</td><td>${pts.length}</td>
      <td><input data-doc="${esc(doc)}" type="number" min="1" value="${esc(cur)}" placeholder="—" class="pin-input"></td></tr>`;
  }).join('');
  const docHtml = `<details class="pin-panel" ${Object.keys(docPin).length ? 'open' : ''}>
    <summary><strong>📌 醫師抽籤順位 pin</strong>（指定某醫師排第 N 順位；空白 = 抽籤表權重決定）</summary>
    <table class="data"><thead><tr><th>主治醫師</th><th>病人數</th><th>第幾順位</th></tr></thead>
    <tbody>${docBody}</tbody></table></details>`;

  let host = $('#pin-wrap');
  if (!host) {
    host = document.createElement('div');
    host.id = 'pin-wrap';
    $('#subtables-wrap').insertAdjacentElement('beforebegin', host);
  }
  host.innerHTML =
    `<div id="pin-patient-wrap">${patHtml}</div>` +
    `<div id="pin-doctor-wrap">${docHtml}</div>`;

  // Auto-save into localStorage on every input change so page reloads keep state
  $$('#pin-wrap input.pin-input').forEach(inp => {
    inp.addEventListener('input', () => {
      const { patient_pins, doctor_pins } = pinsForPayload();
      savePins({ patient_pins, doctor_pins });
    });
  });
}

let _fgOptions = null;

async function ensureFgOptions() {
  if (_fgOptions) return _fgOptions;
  try {
    const r = await api('/api/options/fg');
    _fgOptions = { f: r.f || [], g: r.g || [] };
  } catch (_) {
    _fgOptions = { f: [], g: [] };
  }
  return _fgOptions;
}

function fgInput(col, value, row, options, listId) {
  const esc = s => String(s || '').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  // Custom combobox: input + ▼ that opens a real <ul> popup (not native
  // datalist). Always works regardless of browser. Still typeable for free
  // text. options stored on data-options for the popup builder.
  const optsAttr = esc(JSON.stringify(options || []));
  return `<span class="fg-cell" data-options='${optsAttr}'>
    <input class="fg-input" type="text" autocomplete="off"
           data-row="${row}" data-col="${col}" value="${esc(value)}"
           placeholder="點 ▼ 或自填">
    <button type="button" class="fg-chev" tabindex="-1" title="展開選單">▼</button>
    <ul class="fg-popup" hidden></ul>
  </span>`;
}

// 註記 (sub-table col H = 8): free-text, NO dropdown. A bare input.fg-input
// so the existing wireFgInputsIn save-on-blur path picks it up and writes
// via /api/step4/cell; the chevron/popup loop only touches span.fg-cell so
// this stays a plain text box. Use for 「不排導管」 etc.
function noteInput(value, row) {
  const esc = s => String(s || '').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  if (!row) return `<span class="hint">（無 row，不可填註記）</span>`;
  return `<input class="fg-input note-input" type="text" autocomplete="off"
           data-row="${row}" data-col="8" value="${esc(value)}"
           placeholder="註記，如 不排導管 / 待會診…">`;
}

// 備註(住服) (sub-table col I = 9): same free-text affordance as 註記.
// Mirrors to N-V Q via propagate_field_edit in /api/step4/cell.
function houseInput(value, row) {
  const esc = s => String(s || '').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  if (!row) return `<span class="hint">（無 row，不可填備註(住服)）</span>`;
  return `<input class="fg-input house-input" type="text" autocomplete="off"
           data-row="${row}" data-col="9" value="${esc(value)}"
           placeholder="備註(住服)，如 V (住服已申請)…">`;
}

function fgDatalist(id, options) {
  // Legacy datalist kept for backward compat (no longer used by fgInput);
  // returns empty string so existing call sites are no-ops.
  return '';
}

async function renderSubtables(tables) {
  const opts = await ensureFgOptions();
  const esc = s => String(s || '').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  // Parse "<age> y/o <gender>\n..." prefix from c_text (col C). EMR writeback
  // puts this prefix on every patient with non-empty divUserSpec.
  const parseDemog = (cText) => {
    const m = String(cText || '').match(/^(\d+)\s+y\/o\s+([男女])\s*\n/);
    return m ? { age: m[1], gender: m[2] } : { age: '', gender: '' };
  };
  // Datalists are shared across all rows; render once at the top
  const datalists = fgDatalist('fg-f-list', opts.f) + fgDatalist('fg-g-list', opts.g);
  const html = Object.entries(tables).map(([doc, pts]) => {
    const body = pts.map(p => {
      const d = parseDemog(p.emr);
      return `
      <tr>
        <td>${esc(p.name)}</td><td>${esc(p.chart_no)}</td>
        <td>${esc(d.gender)}</td><td>${esc(d.age)}</td>
        <td class="editable editable-pin" data-row="${p.row}" data-col="5" contenteditable="true" title="填數字 = 同醫師內排序（1/2/3）">${esc(p.manual)}</td>
        <td>${fgInput(6, p.diagnosis, p.row, opts.f, 'fg-f-list')}</td>
        <td>${fgInput(7, p.cathlab,   p.row, opts.g, 'fg-g-list')}</td>
        <td>${noteInput(p.note, p.row)}</td>
        <td>${houseInput(p.house, p.row)}</td>
      </tr>`;
    }).join('');
    return `<div class="doctor-block"><h3>${doc}（${pts.length}人）</h3>
      <table class="data"><thead><tr><th>姓名</th><th>病歷號</th><th>性別</th><th>年齡</th><th>同醫師內排序(E)</th><th>術前診斷(F)</th><th>預計心導管(G)</th><th>註記</th><th>備註(住服)</th></tr></thead>
      <tbody>${body}</tbody></table></div>`;
  }).join('');
  $('#subtables-wrap').innerHTML = datalists + html || '<p class="hint">沒找到子表格</p>';
  renderPinPanels(tables);
  wireEditableCells();
  wireFgInputs();
}

function wireFgInputsIn(scopeSel, msgSel, onSavedExtra) {
  const date = $('#date-input').value.trim();
  const scope = $(scopeSel);
  if (!scope) return;
  scope.querySelectorAll('input.fg-input').forEach(inp => {
    inp.dataset.original = inp.value;
    const save = async () => {
      const val = inp.value.trim();
      if (val === inp.dataset.original) return;
      if (!inp.dataset.row || inp.dataset.row === 'undefined') {
        // No row known (e.g. patient not in any sub-table) — refuse to save
        flash($(msgSel), '✗ 找不到子表格 row，無法寫回', 'err');
        return;
      }
      inp.classList.add('saving');
      try {
        const fd = new FormData();
        fd.append('date', date);
        fd.append('row', inp.dataset.row);
        fd.append('col', inp.dataset.col);
        fd.append('value', val);
        await api('/api/step4/cell', { method: 'POST', body: fd });
        inp.dataset.original = val;
        inp.classList.remove('saving');
        inp.classList.add('saved');
        setTimeout(() => inp.classList.remove('saved'), 1200);
        flash($(msgSel),
          `✓ 已存 ${String.fromCharCode(64 + parseInt(inp.dataset.col))}${inp.dataset.row} = ${val || '(空)'}`, 'ok');
        if (typeof onSavedExtra === 'function') onSavedExtra(inp);
      } catch (err) {
        inp.classList.remove('saving');
        inp.classList.add('error');
        flash($(msgSel), '✗ ' + err.message, 'err');
      }
    };
    inp.addEventListener('change', save);
    inp.addEventListener('blur', save);
  });
  // Wire ▼ chevron — opens a custom popup <ul> with all options.
  // Click an option = sets the input value + commits via the same save path.
  // Click outside = closes. Typing in the input still works (combobox UX).
  const closeAll = () => scope.querySelectorAll('ul.fg-popup').forEach(p => {
    p.hidden = true; p.classList.remove('open');
  });
  scope.querySelectorAll('span.fg-cell').forEach(cell => {
    const inp   = cell.querySelector('input.fg-input');
    const btn   = cell.querySelector('button.fg-chev');
    const popup = cell.querySelector('ul.fg-popup');
    // Defensive: if the rendered cell is from a stale (cached) template
    // that pre-dates the chevron + popup, bail out instead of crashing
    // addEventListener on null.
    if (!inp || !btn || !popup) return;
    let options = [];
    try { options = JSON.parse(cell.getAttribute('data-options') || '[]'); }
    catch (_) { options = []; }
    const buildList = (filter) => {
      const f = (filter || '').toLowerCase();
      const items = options.filter(o => !f || o.toLowerCase().includes(f));
      popup.innerHTML = items.map(o =>
        `<li tabindex="-1" data-val="${o.replace(/"/g,'&quot;')}">${o.replace(/</g,'&lt;')}</li>`
      ).join('') || '<li class="empty">（沒有符合的選項）</li>';
    };
    // Chevron click → ALWAYS show full list (no filter), regardless of current value.
    // Typing in input → filter narrows the list (combobox UX).
    const open = (filterByValue) => {
      buildList(filterByValue ? inp.value : '');
      popup.hidden = false; popup.classList.add('open');
    };
    const close = () => { popup.hidden = true; popup.classList.remove('open'); };
    btn.addEventListener('mousedown', (e) => {
      e.preventDefault();
      // toggle
      if (!popup.hidden) { close(); return; }
      closeAll();  // close any other open popup
      open(false);  // false = ignore current value, show ALL options
      inp.focus();
    });
    inp.addEventListener('focus', () => { /* don't auto-open on focus */ });
    inp.addEventListener('input', () => {
      // Typing in the input auto-opens the popup with a value-filtered list,
      // so users get suggestions without having to click ▼ first. (Same UX
      // as a native <datalist> combobox.)
      if (popup.hidden) {
        closeAll();
        open(true);  // true = filter by current input value
      } else {
        buildList(inp.value);
      }
    });
    popup.addEventListener('mousedown', (e) => {
      const li = e.target.closest('li[data-val]');
      if (!li) return;
      e.preventDefault();
      inp.value = li.dataset.val;
      close();
      // Trigger save (change handler bound above already fires on blur/change;
      // dispatch change so it also fires on click-set without losing focus).
      inp.dispatchEvent(new Event('change'));
      inp.focus();
    });
  });
  // Close popups on click outside the scope
  document.addEventListener('mousedown', (e) => {
    if (!e.target.closest('.fg-cell')) closeAll();
  }, { once: false });
}

function wireFgInputs() {
  // Step 4 sub-table view — saves go to /api/step4/cell.
  // Bidirectional sync: when user saves F/G here, push the value into the
  // matching Step 3 EMR card input (by row+col) so both views stay coherent.
  wireFgInputsIn('#subtables-wrap', '#s4-msg', (savedInp) => {
    const row = savedInp.dataset.row;
    const col = savedInp.dataset.col;
    const val = savedInp.value;
    document.querySelectorAll(
      `#emr-results input.fg-input[data-row="${row}"][data-col="${col}"]`
    ).forEach(target => {
      target.value = val;
      target.dataset.original = val;  // suppress duplicate save round-trip
    });
  });
}

function wireEditableCells() {
  const date = $('#date-input').value.trim();
  $$('#subtables-wrap td.editable').forEach(td => {
    td.dataset.original = td.textContent;
    td.addEventListener('blur', async () => {
      const val = td.textContent.trim();
      if (val === td.dataset.original) return;
      td.classList.add('saving');
      try {
        const fd = new FormData();
        fd.append('date', date);
        fd.append('row', td.dataset.row);
        fd.append('col', td.dataset.col);
        fd.append('value', val);
        await api('/api/step4/cell', { method: 'POST', body: fd });
        td.dataset.original = val;
        td.classList.remove('saving');
        td.classList.add('saved');
        setTimeout(() => td.classList.remove('saved'), 1200);
        flash($('#s4-msg'), `✓ 已存 ${String.fromCharCode(64 + parseInt(td.dataset.col))}${td.dataset.row}`, 'ok');
      } catch (err) {
        td.classList.remove('saving');
        td.classList.add('error');
        flash($('#s4-msg'), '✗ ' + err.message, 'err');
      }
    });
  });
}
