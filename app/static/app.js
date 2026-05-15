// ========================================================================
// Small vanilla JS app. No framework — keeps the local bundle zero-deps.
// ========================================================================

// ---------- Help modal (runs on every page) ----------
(function () {
  const link = document.getElementById('help-link');
  const modal = document.getElementById('help-modal');
  const close = document.getElementById('help-close');
  if (!link || !modal) return;
  link.addEventListener('click', (e) => { e.preventDefault(); modal.hidden = false; });
  if (close) close.addEventListener('click', () => { modal.hidden = true; });
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.hidden = true; });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.hidden) modal.hidden = true;
  });
})();


// ---------- Sheet viewer modal (runs on every page) ----------
(function () {
  const link    = document.getElementById('viewer-link');
  const modal   = document.getElementById('viewer-modal');
  const close   = document.getElementById('viewer-close');
  const select  = document.getElementById('viewer-date-select');
  const refresh = document.getElementById('viewer-refresh');
  const msg     = document.getElementById('viewer-msg');
  const body    = document.getElementById('viewer-body');
  if (!link || !modal) return;

  const MAIN_HEADER  = ['實際住院日','開刀日','科別','主治醫師','主診斷(ICD)','姓名','性別','年齡','病歷號碼','病床號','入院提示','住急'];
  const ORDER_HEADER = ['序號','主治醫師','病人姓名','備註(住服)','備註','病歷號','術前診斷','預計心導管','每日續等清單','改期'];
  const SUB_HEADER   = ['姓名','病歷號','EMR','summary','入院序','術前診斷','預計心導管','註記'];

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
    // Sub-table patient rows live at title_row + 2 (skip title + sub-header).
    // Cols A..H = 1..8 in the sheet.
    const startRow = (sub.title_row || 1) + 2;
    return `<div class="viewer-sub">${title}${renderTable(SUB_HEADER, sub.rows || [], startRow, 1)}</div>`;
  }

  function render(data) {
    const mainRows  = (data.main  || []).slice(1);   // strip header row
    const orderRows = (data.ordering || []).slice(1);
    const main  = `<div class="viewer-section"><h3>主資料 A-L（${mainRows.length} 列）</h3>${renderTable(MAIN_HEADER, mainRows, 2, 1)}</div>`;
    // Ordering block lives at columns N..W = 14..23. Pass colOffset=14.
    const order = `<div class="viewer-section"><h3>入院序 N-W（${orderRows.length} 列）</h3>${renderTable(ORDER_HEADER, orderRows, 2, 14)}</div>`;
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
      const fd = new FormData();
      fd.append('sheet', currentSheet);
      fd.append('row', row);
      fd.append('col', col);
      fd.append('value', next);
      const r = await fetch('/api/sheet/write_cell', { method: 'POST', body: fd });
      if (!r.ok) throw new Error(await r.text());
      td.setAttribute('data-orig', next);
      td.classList.remove('viewer-cell-saving');
      td.classList.add('viewer-cell-saved');
      setTimeout(() => td.classList.remove('viewer-cell-saved'), 1200);
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

  async function loadSheets() {
    setMsg('讀取分頁清單…', 'ok');
    try {
      const r = await api('/api/sheet/list');
      const all = r.sheets || [];
      const dates = all.filter(isYmd).sort((a, b) => b.localeCompare(a));
      const others = all.filter(s => !isYmd(s));
      const today = todayYmd();
      const opts = ['<option value="">— 選擇分頁 —</option>'];
      if (dates.length) {
        opts.push('<optgroup label="日期分頁 (YYYYMMDD)">');
        opts.push(...dates.map(d => `<option value="${d}"${d === today ? ' selected' : ''}>${d}</option>`));
        opts.push('</optgroup>');
      }
      if (others.length) {
        opts.push('<optgroup label="其他工作表">');
        opts.push(...others.map(s => `<option value="${s}">${s}</option>`));
        opts.push('</optgroup>');
      }
      select.innerHTML = opts.join('');
      setMsg(`日期分頁 ${dates.length}、其他工作表 ${others.length}`, 'ok');
      if (dates.includes(today)) loadSheet(today);
    } catch (err) {
      setMsg('✗ ' + err.message, 'err');
    }
  }

  async function loadSheet(name) {
    if (!name) { body.innerHTML = '<p class="hint">選一個分頁開始查閱。</p>'; return; }
    setMsg('讀取 ' + name + ' …', 'ok');
    body.innerHTML = '<p class="hint">載入中…</p>';
    currentSheet = name;
    try {
      if (isYmd(name)) {
        const r = await api(`/api/sheet/read?date=${encodeURIComponent(name)}`);
        if (r.error) { setMsg('✗ ' + r.error, 'err'); body.innerHTML = `<p class="viewer-empty">${esc(r.error)}</p>`; return; }
        render(r);
      } else {
        const r = await api(`/api/sheet/raw?name=${encodeURIComponent(name)}`);
        if (r.error) { setMsg('✗ ' + r.error, 'err'); body.innerHTML = `<p class="viewer-empty">${esc(r.error)}</p>`; return; }
        renderRaw(r);
      }
      setMsg('✓ ' + name + '（可直接編輯儲存格）', 'ok');
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
      alert(`${friendly} 同步失敗：${e}`);
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
      $('#test-output').textContent = '測試中…';
      try {
        const r = await api('/api/settings/test');
        $('#test-output').textContent = JSON.stringify(r, null, 2);
      } catch (err) {
        $('#test-output').textContent = err.message;
      }
    });
  });
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
  subtable_count_mismatch: '子表格人數標題與實際不符',
  gap_too_small:           '子表格間空白行不足（< 2）',
  subtable_missing_title:  '子表格缺少標題（姓名列前沒有 X（N人））',
  chart_text_format:       '病歷號欄位格式',
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
    await withBusy($('#write1-btn'), '寫入中…', async () => {
      await step1Write(date, rows, /* allowOverwrite */ false);
    });
  });
}

async function step1Write(date, rows, allowOverwrite) {
  const fd = new FormData();
  fd.append('date', date);
  fd.append('rows', JSON.stringify(rows));
  fd.append('allow_overwrite', allowOverwrite ? 'yes' : 'no');
  try {
    const r = await api('/api/step1/write', { method: 'POST', body: fd });
    if (r.needs_confirm) {
      // Existing sheet — show diff preview and ask for confirmation
      const confirmed = await showStep1DiffAndConfirm(r);
      if (confirmed) {
        await step1Write(date, rows, true);
      } else {
        flash($('#ocr-msg'), '取消寫入（已保留舊資料）', 'ok');
      }
    } else {
      flash($('#ocr-msg'), `✓ 已寫入 ${r.range}`, 'ok');
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
      <p class="hint">確認後：A-L 主資料覆蓋為新清單；**子表格自動跟著動**（取消的列刪除、新增的病人掛到對應主治、換醫師的列搬到新醫師），新列 F/G 留白待 Step 3 EMR 填。<strong>N-V 入院序仍不會自動更新</strong> — 動到病人數量請手動重跑 Step 2 + Step 4。</p>
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

// ---------- Step 3: EMR ----------
function setupStep3() {
  $('#run3-btn').addEventListener('click', async () => {
    const url = $('#session-url').value.trim();
    let patients;
    const raw = $('#emr-patients').value.trim();
    if (raw) {
      try { patients = JSON.parse(raw); }
      catch { return flash($('#s3-msg'), '病人 JSON 格式錯誤', 'err'); }
    } else {
      patients = step2Ordered;
    }
    if (!url || !patients || !patients.length)
      return flash($('#s3-msg'), '請填 session URL 並確定有病人清單', 'err');

    const date = $('#date-input').value.trim();
    await withBusy($('#run3-btn'), `EMR 擷取中… (${patients.length} 位)`, async () => {
      flash($('#s3-msg'), `擷取中… (${patients.length} 位)`, 'ok');
      const fd = new FormData();
      fd.append('session_url', url);
      fd.append('patients_json', JSON.stringify(patients));
      fd.append('date', date);
      fd.append('admission_date', date);
      try {
        const r = await api('/api/step3/run', { method: 'POST', body: fd });
        renderEmrResults(r.results);
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
          skippedNote = `；寫回子表格 ${wb.written} 位${autoBuilt}` +
            (missing ? `，${missing} 位查無子表格` : '');
        }
        flash($('#s3-msg'),
          `✓ 完成 ${r.results.length} 位${skippedNote}`, level);
      } catch (err) {
        flash($('#s3-msg'), '✗ ' + err.message, 'err');
      }
    });
  });
}

function renderEmrResults(results) {
  const escape = s => (s || '').replace(/</g, '&lt;');
  const html = results.map(r => {
    const demog = (r.age != null && r.gender) ? `${r.age} y/o ${r.gender}` : '';
    const fg = `<span class="emr-fg">F=${escape(r.f) || '—'} / G=${escape(r.g) || '—'}</span>`;
    const emrName = r.emr_name && r.emr_name !== r.name
      ? `<span class="emr-name-fix">(EMR：${escape(r.emr_name)})</span>` : '';
    const visit = r.visit_label ? `<span class="hint">[訪視: ${escape(r.visit_label)}]</span>` : '';
    // Empty SOAP / boilerplate-only response → render the warning card not a <pre>
    // so the user immediately sees "no clinic record" rather than scanning text.
    const noRecord = r.has_record === false;
    const body = noRecord
      ? `<p class="msg err" style="margin:6px 0">⚠ ${escape(r.c_text) || '查無 EMR'}</p>`
      : `<pre>${escape(r.c_text)}</pre>`;
    return `
    <div class="emr-card${noRecord ? ' emr-no-record' : ''}">
      <h3>${escape(r.doctor)} / ${escape(r.name)} ${emrName} (${escape(r.chart_no)}) ${r.error ? '⚠' : ''}</h3>
      ${r.error ? `<p class="msg err">${escape(r.error)}</p>` : ''}
      <p class="hint">${escape(demog)} &nbsp; ${fg} &nbsp; ${visit}</p>
      ${body}
    </div>`;
  }).join('');
  $('#emr-results').innerHTML = html;
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
        flash($('#s4-msg'),
          `✓ ${r.range}（病人 pin ${r.pinned_patients} / 醫師 pin ${r.pinned_doctors}；抽籤表 ${weekday}：${tix}）`, 'ok');
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
        flash($('#s4-msg'), `✓ 已整合 ${r.rows} 筆到 ${r.range}`, 'ok');
      } catch (err) {
        flash($('#s4-msg'), '✗ ' + err.message, 'err');
      }
    });
  });
}

// ---------- Step 5: Cathlab ----------
function setupStep5() {
  const out = () => $('#s5-output');

  const renderPlan = (plan, skipped) => {
    const blocks = Object.entries(plan).map(([d, pts]) => {
      const body = pts.map(p => {
        const diagCell = p.diag_id ? `${p.diag_label} <span class="hint">[${p.diag_id}]</span>` : `<span class="err">${p.diag || '—'}（無對應 ID）</span>`;
        const procCell = p.proc_id ? `${p.proc_label} <span class="hint">[${p.proc_id}]</span>` : (p.cath ? `<span class="err">${p.cath}（無對應 ID → 進備註）</span>` : '—');
        const sessionTag = p.in_schedule === false || p.session === 'OFF' ? '<span class="err">非時段</span>' : p.session;
        const doctorCell = p.second_doctor ? `${p.doctor}<br><span class="hint">+${p.second_doctor}</span>` : p.doctor;
        return `<tr><td>${p.seq}</td><td>${doctorCell}</td><td>${p.name}</td><td>${p.chart}</td><td>${sessionTag}</td><td>${p.room}</td><td>${p.time}</td><td>${diagCell}</td><td>${procCell}</td><td>${p.note_out || ''}</td></tr>`;
      }).join('');
      return `<h3>${d} — ${pts.length} 位</h3><table class="data"><thead><tr><th>#</th><th>主治</th><th>姓名</th><th>病歷</th><th>時段</th><th>房</th><th>時間</th><th>術前診斷</th><th>預計心導管</th><th>註記</th></tr></thead><tbody>${body}</tbody></table>`;
    }).join('');
    const skips = skipped.length ? `<h3>跳過 ${skipped.length} 位</h3><ul>${skipped.map(p => `<li>${p.doctor} ${p.name} (${p.chart}) — ${p.note}</li>`).join('')}</ul>` : '';
    return blocks + skips;
  };

  $('#plan5-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    if (!date) return flash($('#s5-msg'), '請填日期', 'err');
    await withBusy($('#plan5-btn'), '產出計畫中…', async () => {
      flash($('#s5-msg'), '產出計畫中…', 'ok');
      try {
        const r = await api(`/api/step5/plan?date=${date}`);
        out().innerHTML = renderPlan(r.plan, r.skipped);
        flash($('#s5-msg'), '✓ 計畫已產出（未寫入 WEBCVIS）', 'ok');
      } catch (err) {
        flash($('#s5-msg'), '✗ ' + err.message, 'err');
      }
    });
  });

  $('#verify5-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    if (!date) return flash($('#s5-msg'), '請填日期', 'err');
    if (!confirm('這會開啟 Playwright 登入 WEBCVIS 查詢排程，繼續？')) return;
    await withBusy($('#verify5-btn'), '驗證中…', async () => {
    flash($('#s5-msg'), '登入 WEBCVIS 查詢中…', 'ok');
    const fd = new FormData(); fd.append('date', date);
    try {
      const r = await api('/api/step5/verify', { method: 'POST', body: fd });
      const ok  = r.found.map(p => `<tr class="ok"><td>OK</td><td>${p.cath_date}</td><td>${p.doctor}</td><td>${p.name}</td><td>${p.chart}</td></tr>`).join('');
      const bad = r.missing.map(p => `<tr class="bad"><td>NG</td><td>${p.cath_date}</td><td>${p.doctor}</td><td>${p.name}</td><td>${p.chart}</td></tr>`).join('');
      const skip = r.skipped.map(p => `<tr><td>${p.unexpected_present ? '⚠ SKIP 卻在排程' : 'SKIP'}</td><td>—</td><td>${p.doctor}</td><td>${p.name}</td><td>${p.chart}</td></tr>`).join('');
      out().innerHTML = `<p>OK ${r.totals.ok} / MISSING ${r.totals.missing} / SKIP ${r.totals.skip}</p>
        <table class="data"><thead><tr><th>狀態</th><th>cath_date</th><th>主治</th><th>姓名</th><th>病歷</th></tr></thead>
        <tbody>${bad}${ok}${skip}</tbody></table>`;
      flash($('#s5-msg'), `✓ 驗證完成（${r.totals.missing} 筆遺漏）`, r.totals.missing ? 'err' : 'ok');
    } catch (err) {
      flash($('#s5-msg'), '✗ ' + err.message, 'err');
    }
    });
  });

  $('#keyin5-btn').addEventListener('click', async () => {
    const date = $('#date-input').value.trim();
    if (!date) return flash($('#s5-msg'), '請填日期', 'err');
    if (!confirm('這會開啟 Playwright 實際新增導管排程到 WEBCVIS（ADD + UPT）。確定繼續？')) return;
    await withBusy($('#keyin5-btn'), 'Key in 中…', async () => {
    flash($('#s5-msg'), '寫入 WEBCVIS 中…（會開瀏覽器）', 'ok');
    const fd = new FormData(); fd.append('date', date); fd.append('dry_run', 'no');
    try {
      const r = await api('/api/step5/keyin', { method: 'POST', body: fd });
      const addRows = (r.add || []).map(x => `<tr class="${x.result === 'ok' ? 'ok' : (x.result === 'skip' ? '' : 'bad')}"><td>${x.result}</td><td>${x.name}</td><td>${x.chart}</td><td>${x.reason || ''}</td></tr>`).join('');
      const uptRows = (r.upt || []).map(x => `<tr><td>${x.result}</td><td>${x.name}</td><td>${x.chart}</td><td>${x.reason || ''}</td></tr>`).join('');
      const missRows = (r.missing_after || []).map(x => `<tr class="bad"><td>MISSING</td><td>${x.name}</td><td>${x.chart}</td><td>${x.cath_date}</td></tr>`).join('');
      out().innerHTML = `
        <h3>ADD（${r.summary.ok} 成功 / ${r.summary.skip} 略過 / ${r.summary.error} 錯）</h3>
        <table class="data"><thead><tr><th>狀態</th><th>姓名</th><th>病歷</th><th>備註</th></tr></thead><tbody>${addRows}</tbody></table>
        <h3>UPT（補 pdijson/phcjson）</h3>
        <table class="data"><thead><tr><th>狀態</th><th>姓名</th><th>病歷</th><th>備註</th></tr></thead><tbody>${uptRows || '<tr><td colspan=4>無</td></tr>'}</tbody></table>
        ${missRows ? `<h3>事後驗證 MISSING</h3><table class="data"><tbody>${missRows}</tbody></table>` : '<p class="ok">事後驗證全數存在</p>'}
        <pre class="test-output">${(r.log || []).join('\n')}</pre>`;
      flash($('#s5-msg'), r.summary.error ? `⚠ 有 ${r.summary.error} 筆錯誤` : '✓ keyin 完成', r.summary.error ? 'err' : 'ok');
    } catch (err) {
      flash($('#s5-msg'), '✗ ' + err.message, 'err');
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
  return `<input class="fg-input" type="text" list="${listId}"
            data-row="${row}" data-col="${col}" value="${esc(value)}"
            placeholder="可選清單或自填">`;
}

function fgDatalist(id, options) {
  const esc = s => String(s || '').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  return `<datalist id="${id}">` +
    options.map(o => `<option value="${esc(o)}">`).join('') + '</datalist>';
}

async function renderSubtables(tables) {
  const opts = await ensureFgOptions();
  const esc = s => String(s || '').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  // Datalists are shared across all rows; render once at the top
  const datalists = fgDatalist('fg-f-list', opts.f) + fgDatalist('fg-g-list', opts.g);
  const html = Object.entries(tables).map(([doc, pts]) => {
    const body = pts.map(p => `
      <tr>
        <td>${esc(p.name)}</td><td>${esc(p.chart_no)}</td>
        <td class="editable editable-pin" data-row="${p.row}" data-col="5" contenteditable="true" title="填數字 = 同醫師內排序（1/2/3）">${esc(p.manual)}</td>
        <td>${fgInput(6, p.diagnosis, p.row, opts.f, 'fg-f-list')}</td>
        <td>${fgInput(7, p.cathlab,   p.row, opts.g, 'fg-g-list')}</td>
        <td>${esc(p.note)}</td>
      </tr>`).join('');
    return `<div class="doctor-block"><h3>${doc}（${pts.length}人）</h3>
      <table class="data"><thead><tr><th>姓名</th><th>病歷號</th><th>同醫師內排序(E)</th><th>術前診斷(F)</th><th>預計心導管(G)</th><th>註記</th></tr></thead>
      <tbody>${body}</tbody></table></div>`;
  }).join('');
  $('#subtables-wrap').innerHTML = datalists + html || '<p class="hint">沒找到子表格</p>';
  renderPinPanels(tables);
  wireEditableCells();
  wireFgInputs();
}

function wireFgInputs() {
  const date = $('#date-input').value.trim();
  $$('#subtables-wrap input.fg-input').forEach(inp => {
    inp.dataset.original = inp.value;
    const save = async () => {
      const val = inp.value.trim();
      if (val === inp.dataset.original) return;
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
        flash($('#s4-msg'),
          `✓ 已存 ${String.fromCharCode(64 + parseInt(inp.dataset.col))}${inp.dataset.row} = ${val || '(空)'}`, 'ok');
      } catch (err) {
        inp.classList.remove('saving');
        inp.classList.add('error');
        flash($('#s4-msg'), '✗ ' + err.message, 'err');
      }
    };
    inp.addEventListener('change', save);
    inp.addEventListener('blur', save);
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
