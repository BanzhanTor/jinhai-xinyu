/* ==========================================================
   金海心语 · 前端逻辑
   全部数据走 Python 后端：/api/chat /api/score /api/report ...
   ========================================================== */
(function () {
  'use strict';

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  /* -------------------------------------------------- 基础 */
  let toastTimer = null;
  function toast(msg, ms) {
    const t = $('#toast');
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('show'), ms || 2200);
  }

  const modal = $('#modal');
  function openModal(html) {
    $('#modalContent').innerHTML = html;
    modal.hidden = false;
    document.body.style.overflow = 'hidden';
  }
  function closeModal() {
    modal.hidden = true;
    document.body.style.overflow = '';
  }
  $('#modalX').addEventListener('click', closeModal);
  modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !modal.hidden) closeModal(); });

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[c]);
  }

  /* -------------------------------------------------- 会话 ID */
  function makeSessionId() {
    const p = () => Math.random().toString(36).slice(2, 8);
    return 's_' + Date.now().toString(36) + '_' + p();
  }
  let SESSION = '';
  try { SESSION = localStorage.getItem('jhxy_session') || ''; } catch (e) { }
  if (!SESSION) {
    SESSION = makeSessionId();
    try { localStorage.setItem('jhxy_session', SESSION); } catch (e) { }
  }

  /* -------------------------------------------------- 接口封装 */
  async function api(path, opts) {
    opts = opts || {};
    const url = '/api' + path;
    const init = { method: opts.method || 'GET', headers: {} };
    if (opts.body !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(opts.body);
    }
    let resp;
    try {
      resp = await fetch(url, init);
    } catch (e) {
      throw new Error('连不上后端服务，请确认 python app.py 还在运行');
    }
    let data = null;
    try { data = await resp.json(); } catch (e) { }
    if (!resp.ok) {
      throw new Error((data && data.error) || ('请求失败：HTTP ' + resp.status));
    }
    return data || {};
  }

  /* -------------------------------------------------- 状态灯 */
  let RUNTIME = { has_api_key: false, api_ready: false, model: '', base_url: '', provider: '' };

  function setStatus(state, text) {
    const el = $('#apiStatus');
    el.dataset.state = state;
    $('#apiStatusText').textContent = text;
  }

  async function loadConfig() {
    setStatus('loading', '检测中…');
    try {
      const d = await api('/config');
      RUNTIME = d.config || {};
      applyStatus();
      return RUNTIME;
    } catch (e) {
      showConnFail(e.message);
      return null;
    }
  }

  function applyStatus() {
    const banner = $('#offlineBanner');
    $('#connBanner').hidden = true;
    if (RUNTIME.api_ready) {
      setStatus('api', '大模型已接入');
      banner.hidden = true;
    } else {
      setStatus('offline', '离线模式');
      banner.hidden = false;
    }
  }

  /* -------------------------------------------------- 连不上后端 */
  function isFileProtocol() {
    return location.protocol === 'file:';
  }

  function showConnFail(detail) {
    const banner = $('#connBanner');
    const isFile = isFileProtocol();
    banner.hidden = false;

    if (isFile) {
      $('#connTitle').textContent = '页面是双击打开的，所以连不上后端';
      $('#connText').innerHTML =
        '你是直接用浏览器打开了 html 文件（<code>file://</code> 协议），' +
        '浏览器出于安全限制，不允许这种方式访问本地接口。<br>' +
        '请在项目文件夹里打开命令行，运行 <code>python app.py --open</code>，' +
        '它会自动打开 <b>http://127.0.0.1:8000</b> —— 必须用那个地址访问才连得通。';
      $('#connRetry').hidden = true;
      setStatus('error', '需要启动服务');
    } else {
      $('#connTitle').textContent = '连不上后端服务';
      $('#connText').innerHTML =
        `当前页面地址是 <code>${esc(location.origin)}</code>，但接口没有响应。` +
        '请确认启动服务的那命令行窗口还开着（窗口一关，服务就停了），' +
        '然后点「重新连接」。' +
        (detail ? `<br><span style="opacity:.75">系统提示：${esc(detail)}</span>` : '');
      $('#connRetry').hidden = false;
      setStatus('error', '后端未连接');
    }
  }

  function showConnHelp() {
    const isFile = isFileProtocol();
    const rows = [
      ['当前页面地址', location.href.length > 60 ? location.href.slice(0, 60) + '…' : location.href],
      ['协议', location.protocol],
      ['期望的后端', 'http://127.0.0.1:8000'],
      ['后端状态', isFile ? '未检测（file:// 无法访问接口）' : '无响应'],
    ];
    openModal(`
      <span class="cat-tag">连接诊断</span>
      <h3 style="margin-bottom:16px">为什么连不上</h3>
      <div class="set-sec">
        ${rows.map(([k, v]) => `<div class="set-row" style="margin-bottom:10px">
          <label style="font-size:12px;color:var(--muted);font-weight:600">${esc(k)}</label>
          <div style="font-family:Consolas,monospace;font-size:12.5px;color:var(--ink);word-break:break-all">${esc(v)}</div>
        </div>`).join('')}
      </div>

      <div class="set-sec">
        <h4>按顺序检查</h4>
        <div style="font-size:13px;line-height:2;color:var(--body)">
          <div>① 有没有开命令行窗口跑 <code style="background:var(--grey);padding:1px 6px;border-radius:4px">python app.py</code>？</div>
          <div>② 那个窗口还开着没有？（按 Ctrl+C 或关窗口 = 服务停止）</div>
          <div>③ 浏览器地址栏是不是 <b>http://127.0.0.1:8000</b>？</div>
          <div>④ 如果提示端口被占用，看命令行里它自动换到了哪个端口</div>
        </div>
      </div>

      <div class="set-sec">
        <h4>正确启动方式</h4>
        <code class="set-code">cd /d "D:\\大创\\金海\\金海心语-完整版"
python app.py --open</code>
        <div class="hint" style="font-size:11.5px;color:var(--muted);margin-top:8px;line-height:1.7">
          在文件资源管理器里打开这个文件夹，地址栏输入 <b>cmd</b> 回车，就能直接进入该目录。
        </div>
      </div>

      <div class="set-actions">
        <button class="btn btn-primary btn-sm" id="connModalRetry">重新连接</button>
      </div>
    `);
    $('#connModalRetry').addEventListener('click', () => location.reload());
  }

  $('#connRetry').addEventListener('click', () => location.reload());
  $('#connHelp').addEventListener('click', showConnHelp);

  $('#apiStatus').addEventListener('click', () => openSettings());
  document.addEventListener('click', e => {
    if (e.target.id === 'openSettings2') openSettings();
  });

  /* -------------------------------------------------- 设置面板 */
  const PRESETS = {
    deepseek: { base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
    openai: { base_url: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
    qwen: { base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
    kimi: { base_url: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' },
    zhipu: { base_url: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4-flash' },
    ollama: { base_url: 'http://127.0.0.1:11434/v1', model: 'qwen2.5:7b' },
    custom: { base_url: '', model: '' }
  };

  function openSettings() {
    const c = RUNTIME || {};
    const prov = c.provider || 'deepseek';
    const opts = Object.keys(PRESETS).map(k =>
      `<option value="${k}"${k === prov ? ' selected' : ''}>${
        { deepseek: 'DeepSeek（推荐）', openai: 'OpenAI', qwen: '通义千问', kimi: 'Kimi',
          zhipu: '智谱 GLM', ollama: '本地 Ollama', custom: '自定义' }[k]}</option>`
    ).join('');

    openModal(`
      <span class="cat-tag">接口设置</span>
      <h3 style="margin-bottom:8px">接入你自己的大模型</h3>
      <p style="font-size:12.5px;color:var(--muted);line-height:1.75;margin-bottom:22px">
        填好下面三项就能用真实大模型作答。没配也能用，系统会自动走内置规则引擎。
        <br>配置会写进项目根目录的 <b>config.json</b>，不会上传到任何地方。
      </p>

      <div class="set-sec">
        <div class="set-row">
          <label>服务商</label>
          <select class="set-input" id="setProvider">${opts}</select>
          <span class="hint">选好会自动带出接口地址和模型名，也可以手动改。</span>
        </div>
        <div class="set-row">
          <label>API 地址（base_url）</label>
          <input class="set-input" id="setBaseUrl" value="${esc(c.base_url || '')}"
                 placeholder="https://api.deepseek.com/v1">
        </div>
        <div class="set-row">
          <label>模型名（model）</label>
          <input class="set-input" id="setModel" value="${esc(c.model || '')}"
                 placeholder="deepseek-chat">
        </div>
        <div class="set-row">
          <label>API Key</label>
          <input class="set-input" id="setKey" type="password" autocomplete="off"
                 value="" placeholder="${c.has_api_key ? '已保存 ' + esc(c.key_tail || '') + '，留空则不修改' : 'sk-...'}">
          <span class="hint">去服务商控制台复制。填完点「测试连接」，通过了再保存。</span>
        </div>
      </div>

      <div class="set-actions">
        <button class="btn btn-primary btn-sm" id="btnTest">测试连接</button>
        <button class="btn-line btn-sm" id="btnSave">保存配置</button>
        <button class="btn-line btn-sm" id="btnClear">清空 Key</button>
      </div>

      <div id="setResult" hidden></div>

      <div style="margin-top:22px;padding-top:18px;border-top:1px solid var(--line)">
        <div class="hint" style="font-size:11.5px;color:var(--muted);line-height:1.8">
          也可以不用界面，直接改 <b>config.json</b>：
        </div>
        <code class="set-code">{
  "provider": "deepseek",
  "base_url": "https://api.deepseek.com/v1",
  "model": "deepseek-chat",
  "api_key": "sk-你自己的一把key"
}</code>
        <div class="hint" style="font-size:11.5px;color:var(--muted);line-height:1.8;margin-top:10px">
          改完重启服务，或在命令行运行 <b>python test_api.py</b> 验证。
        </div>
      </div>
    `);

    $('#setProvider').addEventListener('change', e => {
      const p = PRESETS[e.target.value];
      if (p && p.base_url) {
        $('#setBaseUrl').value = p.base_url;
        $('#setModel').value = p.model;
      }
    });

    $('#btnTest').addEventListener('click', () => runTest(true));
    $('#btnSave').addEventListener('click', saveSettings);
    $('#btnClear').addEventListener('click', () => {
      $('#setKey').value = '';
      $('#setKey').disabled = true;
      $('#btnClear').dataset.cleared = '1';
      toast('已清空输入框，点「保存配置」生效');
    });
  }

  function settingsPayload() {
    const p = {
      provider: $('#setProvider').value,
      base_url: $('#setBaseUrl').value.trim(),
      model: $('#setModel').value.trim()
    };
    const keyEl = $('#setKey');
    if (!keyEl.disabled) {
      const k = keyEl.value.trim();
      if (k) p.api_key = k;
    } else {
      p.api_key = '';
    }
    return p;
  }

  function showSetResult(ok, text) {
    const el = $('#setResult');
    el.hidden = false;
    el.className = 'set-result' + (ok ? '' : ' err');
    el.textContent = text;
  }

  async function runTest(showInPanel) {
    const body = settingsPayload();
    const btn = $('#btnTest');
    if (btn) { btn.disabled = true; btn.textContent = '测试中…'; }
    try {
      const d = await api('/test', { method: 'POST', body });
      const r = d.result || {};
      if (r.ok) {
        const msg = `连接成功（${r.ms} ms）\n模型：${r.model}\n回声：${r.reply}`;
        if (showInPanel) showSetResult(true, msg); else toast('连接成功');
      } else {
        const msg = `连接失败：${r.error || '未知错误'}\n请检查 key、接口地址和模型名。`;
        if (showInPanel) showSetResult(false, msg); else toast('连接失败');
      }
      return r.ok;
    } catch (e) {
      if (showInPanel) showSetResult(false, e.message); else toast(e.message, 3500);
      return false;
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '测试连接'; }
    }
  }

  async function saveSettings() {
    const body = settingsPayload();
    try {
      const d = await api('/config', { method: 'POST', body });
      RUNTIME = Object.assign({}, RUNTIME, d.config || {});
      applyStatus();
      showSetResult(true, '已保存：' + (RUNTIME.model || '') + '\n' + (RUNTIME.base_url || ''));
      toast('配置已生效');
      setTimeout(closeModal, 900);
    } catch (e) {
      showSetResult(false, e.message);
    }
  }

  /* ==================================================
     一、智能对话
     ================================================== */
  let chatInited = false;

  function addMsg(who, text, meta) {
    const log = $('#chatLog');
    const wrap = document.createElement('div');
    wrap.className = 'msg msg-' + who;

    const av = document.createElement('div');
    av.className = 'avatar';
    av.textContent = who === 'ai' ? '心' : '我';

    const bub = document.createElement('div');
    bub.className = 'bubble';

    if (meta && meta.emotion) {
      const tag = document.createElement('span');
      tag.className = 'emotion-tag';
      tag.textContent = meta.emotion + ' · ' + Math.round((meta.score || 0.7) * 100) + '%';
      bub.appendChild(tag);
      if (meta.source) {
        const s = document.createElement('span');
        s.className = 'src-tag';
        s.dataset.src = meta.source;
        s.textContent = meta.source === 'llm' ? '模型判断' : '规则判断';
        bub.appendChild(s);
      }
      bub.appendChild(document.createElement('br'));
    }

    String(text).split('\n').forEach((line, i) => {
      if (i) bub.appendChild(document.createElement('br'));
      bub.appendChild(document.createTextNode(line));
    });

    if (meta && meta.crisis) {
      const c = document.createElement('div');
      c.className = 'crisis-card';
      c.innerHTML = '<b>' + esc(meta.crisis.title) + '</b><br>' + esc(meta.crisis.text);
      bub.appendChild(c);
    }

    wrap.appendChild(av);
    wrap.appendChild(bub);
    log.appendChild(wrap);
    log.scrollTop = log.scrollHeight;
    return wrap;
  }

  function showTyping() {
    const log = $('#chatLog');
    const wrap = document.createElement('div');
    wrap.className = 'msg msg-ai';
    wrap.id = 'typingMsg';
    wrap.innerHTML = '<div class="avatar">心</div><div class="bubble">' +
      '<div class="typing"><i></i><i></i><i></i></div></div>';
    log.appendChild(wrap);
    log.scrollTop = log.scrollHeight;
  }
  function hideTyping() {
    const t = $('#typingMsg');
    if (t) t.remove();
  }

  function updateEmotion(emo, strategy) {
    const badge = $('#emotionBadge');
    const map = { '消极': 'neg', '中性': 'mid', '积极': 'pos', '高风险': 'risk' };
    const state = map[emo.label] || 'mid';
    badge.dataset.state = state;
    badge.textContent = emo.label;
    const fill = $('#emotionFill');
    fill.style.width = Math.round((emo.score || 0.6) * 100) + '%';
    const colors = { neg: 'var(--coral)', risk: 'var(--deep)', pos: 'var(--sage)', mid: 'var(--sage)' };
    fill.style.background = colors[state] || 'var(--sage)';
    $('#emotionHint').textContent =
      (strategy ? strategy.name + '：' + strategy.desc : '') +
      (RUNTIME.api_ready ? '' : '（离线规则引擎）');
  }

  async function sendChat(text) {
    text = (text || '').trim();
    if (!text) return;
    addMsg('user', text);
    showTyping();

    try {
      const d = await api('/chat', { method: 'POST', body: { session_id: SESSION, message: text } });
      hideTyping();
      addMsg('ai', d.reply, {
        emotion: d.emotion.label,
        score: d.emotion.score,
        source: d.emotion.source,
        crisis: d.crisis_card
      });
      updateEmotion(d.emotion, d.strategy);
      if (d.warning) toast(d.warning, 4200);
      refreshSessionStat();
    } catch (e) {
      hideTyping();
      addMsg('ai', '抱歉，服务出了点问题：' + e.message);
    }
  }

  async function initChat() {
    chatInited = true;
    addMsg('ai', '你好，我是心语。\n这里不用报名，也不用说得多好听——想到什么说什么就行。\n今天过得怎么样？');
    try {
      const d = await api('/chat/history?session_id=' + encodeURIComponent(SESSION));
      if (d.messages && d.messages.length) {
        $('#chatLog').innerHTML = '';
        d.messages.forEach(m => {
          if (m.role === 'user') addMsg('user', m.content);
          else addMsg('ai', m.content, { emotion: m.emotion, score: 0.8 });
        });
      }
      updateSessionStat(d.stats);
    } catch (e) { /* 首次访问没有历史，忽略 */ }
  }

  function updateSessionStat(stats) {
    const el = $('#sessionStat');
    if (!stats) { el.textContent = '还没有记录'; return; }
    el.innerHTML = `已倾诉 <b>${stats.user_turns}</b> 次`
      + (stats.risk_turns ? `，其中 <b>${stats.risk_turns}</b> 次触发风险预警` : '');
  }

  async function refreshSessionStat() {
    try {
      const d = await api('/chat/history?session_id=' + encodeURIComponent(SESSION) + '&limit=1');
      updateSessionStat(d.stats);
    } catch (e) { }
  }

  $('#chatForm').addEventListener('submit', e => {
    e.preventDefault();
    const el = $('#chatText');
    const v = el.value;
    el.value = '';
    el.style.height = 'auto';
    sendChat(v);
  });

  const chatText = $('#chatText');
  chatText.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = Math.min(120, this.scrollHeight) + 'px';
  });
  chatText.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      $('#chatForm').dispatchEvent(new Event('submit', { cancelable: true }));
    }
  });
  $('#chatQuick').addEventListener('click', e => {
    const b = e.target.closest('.chip');
    if (b) sendChat(b.dataset.say);
  });

  /* -------------------------------------------------- 心理小结 */
  $('#genReport').addEventListener('click', async () => {
    try {
      const d = await api('/report?session_id=' + encodeURIComponent(SESSION));
      openModal(`
        <span class="cat-tag">心理状态小结</span>
        <h3 style="margin-bottom:6px">本次会话 · 自动生成</h3>
        <p style="font-size:12px;color:var(--faint);margin-bottom:20px">${esc(d.generated_at)}</p>
        <div class="report-box">${esc(d.text)}</div>
        <p style="font-size:11.5px;color:var(--faint);margin-top:16px;line-height:1.7">${esc(d.disclaimer)}</p>
        <div class="report-actions">
          <button class="btn btn-primary btn-sm" id="copyReport">复制文本</button>
        </div>
      `);
      $('#copyReport').addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(d.text);
          toast('已复制');
        } catch (e) { toast('复制失败，请手动选择文本'); }
      });
    } catch (e) { toast(e.message, 3500); }
  });

  /* ==================================================
     二、情绪测评
     ================================================== */
  let SCALES = {};
  let currentScale = 'GAD7';
  let answers = [];

  function renderQuiz(key) {
    const s = SCALES[key];
    if (!s) return;
    currentScale = key;
    answers = new Array(s.items.length).fill(-1);

    let html = `<div class="quiz-intro"><h3>${esc(s.name)}</h3>
      <p>请回想最近两周的实际情况。没有对错，按真实感受作答。</p>
      <div class="scale-legend">${s.options.map((o, i) => `<span>${i} = ${esc(o)}</span>`).join('')}</div>
    </div>`;

    s.items.forEach((q, i) => {
      html += `<div class="q-item" data-i="${i}">
        <div class="q-text"><b>${i + 1}</b>${esc(q)}</div>
        <div class="q-opts">${s.options.map((o, v) =>
          `<button class="opt" data-v="${v}">${esc(o)}</button>`).join('')}</div>
      </div>`;
    });

    html += `<div class="quiz-foot">
      <button class="btn btn-primary" id="submitQuiz" disabled>生成报告</button>
      <span class="quiz-progress" id="quizProg">已完成 <b>0</b> / ${s.items.length}</span>
    </div>`;

    $('#quizArea').innerHTML = html;
    $('#quizArea').dataset.ready = key;
    $('#resultArea').innerHTML = '';
    $('#historyArea').hidden = true;
  }

  $('#page-assess').addEventListener('click', e => {
    const opt = e.target.closest('.opt');
    if (opt) {
      const item = opt.closest('.q-item');
      const i = +item.dataset.i;
      answers[i] = +opt.dataset.v;
      $$('.opt', item).forEach(b => b.classList.remove('sel'));
      opt.classList.add('sel');
      item.classList.add('answered');
      const done = answers.filter(a => a >= 0).length;
      $('#quizProg').innerHTML = `已完成 <b>${done}</b> / ${answers.length}`;
      $('#submitQuiz').disabled = done < answers.length;
      return;
    }
    if (e.target.id === 'submitQuiz') submitQuiz();
  });

  async function submitQuiz() {
    const btn = $('#submitQuiz');
    btn.disabled = true;
    btn.textContent = '生成中…';
    try {
      const d = await api('/score', {
        method: 'POST',
        body: { session_id: SESSION, scale: currentScale, answers }
      });
      renderResult(d.result);
    } catch (e) {
      toast(e.message, 3500);
      btn.disabled = false;
      btn.textContent = '生成报告';
    }
  }

  function renderResult(r) {
    const colorMap = { none: 'var(--sage)', mild: 'var(--sage)', moderate: '#C9A227', severe: 'var(--coral)', crisis: 'var(--deep)' };
    const pillLv = r.crisis ? 'crisis' : r.level_key;

    let html = `<div class="result-card">
      <div class="result-head">
        <div>
          <div class="result-score">${r.total}<small>/ ${r.max}</small></div>
          <div style="margin-top:10px"><span class="level-pill" data-lv="${pillLv}">${esc(r.level_label)}</span></div>
        </div>
        <div style="text-align:right;font-size:12px;color:var(--faint);line-height:1.8">
          ${esc(r.scale_name)}<br>${new Date().toLocaleDateString('zh-CN')}
        </div>
      </div>
      <p style="font-size:14px;line-height:1.8;margin-top:14px">${esc(r.description)}</p>
      <div class="result-bar"><i style="width:${r.percent}%;background:${colorMap[r.level_key] || 'var(--sage)'}"></i></div>
      <div class="result-legend"><span>0</span><span>轻度</span><span>中度</span><span>${r.max}</span></div>`;

    if (r.crisis) {
      html += `<div class="result-crisis">
        <h4>请现在就做一件事</h4>
        <p>联系学校心理中心预约一次面谈，或拨打 <b>12356</b> 心理援助热线（全国 24 小时）。<br>
        如果此刻你觉得不安全，请立刻告诉身边的室友、家人，或拨打 <b>120</b>。<br>
        你不需要一个人扛，这不是软弱，是正确地使用了身边的资源。</p></div>`;
    }

    html += `<div class="result-section"><h4>给你的建议</h4><ul>
      ${r.advice.map(a => `<li>${esc(a)}</li>`).join('')}
    </ul></div>
    <div class="result-actions">
      <button class="btn-line" id="againQuiz">重新测一次</button>
      <a class="btn-line" href="#chat" data-page="chat">去和心语聊聊</a>
      <button class="btn-line" id="seeTrend">看看我的趋势</button>
    </div></div>`;

    $('#quizArea').innerHTML = '';
    $('#resultArea').innerHTML = html;
    $('#resultArea').scrollIntoView({ behavior: 'smooth', block: 'start' });

    $('#againQuiz').addEventListener('click', () => renderQuiz(currentScale));
    $('#seeTrend').addEventListener('click', () => {
      $$('.assess-tabs .tab').forEach(t => t.classList.toggle('active', t.dataset.scale === 'history'));
      renderHistory();
    });
  }

  /* -------------------------------------------------- 记录与趋势 */
  async function renderHistory() {
    $('#quizArea').innerHTML = '<div class="hist-empty"><span class="loading-line"></span>正在读取记录…</div>';
    $('#resultArea').innerHTML = '';
    $('#historyArea').hidden = true;

    try {
      const d = await api('/assessments?session_id=' + encodeURIComponent(SESSION));
      $('#quizArea').innerHTML = '';
      $('#historyArea').hidden = false;

      if (!d.items || !d.items.length) {
        $('#historyArea').innerHTML = '<div class="hist-empty">还没有测评记录。<br>做一次并提交，这里就会出现你的变化趋势。</div>';
        return;
      }

      let html = '';
      ['GAD7', 'PHQ9'].forEach(k => {
        const trend = d.trend[k] || [];
        if (trend.length < 1) return;
        const max = SCALES[k] ? SCALES[k].max : (k === 'GAD7' ? 21 : 27);
        const bars = trend.map(t => {
          const h = Math.max(4, Math.round(t.total / max * 130));
          const lvl = t.total >= max * 0.65 ? 'severe' : (t.total >= max * 0.45 ? 'moderate' : 'none');
          return `<div class="trend-col">
            <span class="trend-val">${t.total}</span>
            <div class="trend-bar" data-lv="${lvl}" style="height:${h}px"></div>
            <span class="trend-lbl">${esc((t.created_at || '').slice(5, 10))}</span>
          </div>`;
        }).join('');

        let delta = '';
        if (trend.length >= 2) {
          const diff = trend[trend.length - 1].total - trend[0].total;
          const pct = trend[0].total ? Math.round(Math.abs(diff) / trend[0].total * 100) : 0;
          if (diff < 0) delta = `<span class="trend-delta">↓ 较首次下降 ${Math.abs(diff)} 分（${pct}%）</span>`;
          else if (diff > 0) delta = `<span class="trend-delta up">↑ 较首次上升 ${diff} 分</span>`;
          else delta = `<span class="trend-delta">与首次持平</span>`;
        }

        html += `<div class="trend-box">
          <h4>${k === 'GAD7' ? '焦虑（GAD-7）' : '抑郁（PHQ-9）'}变化 ${delta}</h4>
          <div class="sub">每次提交后都会记录，前测—后测的对比就在这里</div>
          <div class="trend-chart">${bars}</div>
        </div>`;
      });

      html += '<div style="margin-top:6px">';
      d.items.forEach(h => {
        html += `<div class="hist-item">
          <span class="hist-type">${esc(h.scale)}</span>
          <span class="hist-score">${h.total}<small style="font-size:12px;color:var(--faint)"> / ${
            h.scale === 'GAD7' ? 21 : 27}</small></span>
          <span class="hist-meta">${esc(h.level_label)}</span>
          <span class="hist-date">${esc(h.created_at)}</span>
        </div>`;
      });
      html += '</div>';

      $('#historyArea').innerHTML = html;
    } catch (e) {
      $('#quizArea').innerHTML = '<div class="hist-empty">读取记录失败：' + esc(e.message) + '</div>';
    }
  }

  $$('.assess-tabs .tab').forEach(tab => {
    tab.addEventListener('click', () => {
      $$('.assess-tabs .tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const k = tab.dataset.scale;
      if (k === 'history') renderHistory();
      else renderQuiz(k);
    });
  });

  /* ==================================================
     三、心理科普
     ================================================== */
  let activeCat = '全部';
  let keyword = '';

  async function loadKnowledge() {
    try {
      const qs = `?cat=${encodeURIComponent(activeCat)}&q=${encodeURIComponent(keyword)}`;
      const d = await api('/knowledge' + qs);
      if (d.categories && !$('#knowCats').dataset.built) {
        $('#knowCats').dataset.built = '1';
        $('#knowCats').innerHTML = d.categories.map(c =>
          `<button class="cat${c === activeCat ? ' active' : ''}" data-cat="${esc(c)}">${esc(c)}</button>`
        ).join('');
      }
      const items = d.items || [];
      $('#knowEmpty').hidden = items.length > 0;
      $('#knowGrid').innerHTML = items.map(a => `
        <article class="know-card" data-id="${a.id}">
          <span class="cat-tag">${esc(a.cat)}</span>
          <h3>${esc(a.title)}</h3>
          <p>${esc(a.summary)}</p>
          <div class="meta">约 ${a.minutes} 分钟读完</div>
        </article>`).join('');
    } catch (e) {
      toast('科普内容加载失败：' + e.message, 3500);
    }
  }

  $('#knowCats').addEventListener('click', e => {
    const b = e.target.closest('.cat');
    if (!b) return;
    activeCat = b.dataset.cat;
    $$('#knowCats .cat').forEach(x => x.classList.toggle('active', x.dataset.cat === activeCat));
    loadKnowledge();
  });

  let searchTimer = null;
  $('#knowSearch').addEventListener('input', e => {
    keyword = e.target.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadKnowledge, 320);
  });

  $('#knowGrid').addEventListener('click', async e => {
    const card = e.target.closest('.know-card');
    if (!card) return;
    try {
      const d = await api('/knowledge/' + card.dataset.id);
      const a = d.article;
      openModal(`<span class="cat-tag">${esc(a.cat)}</span>
        <h3>${esc(a.title)}</h3>
        <div class="body">${a.body.map(p => `<p>${esc(p)}</p>`).join('')}</div>`);
    } catch (err) { toast(err.message, 3000); }
  });

  /* ==================================================
     四、心灵树洞
     ================================================== */
  function renderPosts(items) {
    if (!items || !items.length) {
      $('#treeList').innerHTML = '<div class="hist-empty">还没有人说话。你可以是第一个。</div>';
      return;
    }
    $('#treeList').innerHTML = items.map(p => {
      const body = p.hidden
        ? `<div class="post-hidden">这条内容包含高风险表述，已转入人工通道，暂不公开展示。
           发布者如需要帮助，请拨打 12356。</div>`
        : `<div class="post-body">${esc(p.text)}</div>
           <div class="post-ai"><b>心语</b><span>${esc(p.ai_reply).replace(/\n/g, '<br>')}</span></div>`;
      return `<article class="post" data-id="${p.id}">
        <div class="post-head">
          <div class="post-anon">匿</div>
          <span class="post-name">匿名同学</span>
          <span class="post-emo" data-e="${esc(p.emotion || '')}">${esc(p.emotion || '')}</span>
          <span class="post-time">${esc((p.created_at || '').slice(5, 16))}</span>
        </div>
        ${body}
        <div class="post-foot">
          <button class="post-act" data-act="like">♥ <span>${p.likes}</span></button>
          <span class="post-act">💬 回应 ${p.hidden ? 0 : 1}</span>
        </div>
      </article>`;
    }).join('');
  }

  async function loadTree() {
    try {
      const d = await api('/tree');
      renderPosts(d.items);
    } catch (e) {
      $('#treeList').innerHTML = '<div class="hist-empty">树洞加载失败：' + esc(e.message) + '</div>';
    }
  }

  $('#treeText').addEventListener('input', e => {
    $('#treeCount').textContent = e.target.value.length + ' / 500';
  });

  $('#treePost').addEventListener('click', async () => {
    const ta = $('#treeText');
    const text = ta.value.trim();
    if (!text) { toast('先写点什么吧'); return; }
    if (text.length < 4) { toast('再多写几个字吧'); return; }

    const btn = $('#treePost');
    btn.disabled = true;
    btn.textContent = '发布中…';
    try {
      const d = await api('/tree', { method: 'POST', body: { text } });
      renderPosts(d.items);
      ta.value = '';
      $('#treeCount').textContent = '0 / 500';
      toast(d.hidden ? '内容已进入人工通道，不会公开显示' : '已匿名发布');
    } catch (e) {
      toast(e.message, 3500);
    } finally {
      btn.disabled = false;
      btn.textContent = '匿名发布';
    }
  });

  $('#treeList').addEventListener('click', async e => {
    const btn = e.target.closest('[data-act="like"]');
    if (!btn) return;
    const id = btn.closest('.post').dataset.id;
    try {
      const d = await api('/tree/' + id + '/like', { method: 'POST' });
      btn.querySelector('span').textContent = d.likes;
    } catch (err) { toast(err.message, 3000); }
  });

  /* ==================================================
     路由 + 启动
     ================================================== */
  const PAGES = ['home', 'chat', 'assess', 'know', 'tree'];
  const LOADED = {};

  async function go(page) {
    if (PAGES.indexOf(page) < 0) page = 'home';
    $$('.page').forEach(p => p.classList.remove('active'));
    const el = $('#page-' + page);
    if (el) el.classList.add('active');
    $$('.nav-link').forEach(a => a.classList.toggle('active', a.dataset.page === page));
    $('.nav-links').classList.remove('open');
    window.scrollTo(0, 0);

    if (page === 'chat' && !chatInited) await initChat();
    if (page === 'know' && !LOADED.know) { LOADED.know = 1; await loadKnowledge(); }
    if (page === 'tree' && !LOADED.tree) { LOADED.tree = 1; await loadTree(); }
    if (page === 'assess' && !LOADED.assess) {
      LOADED.assess = 1;
      renderQuiz('GAD7');
    }
  }

  document.addEventListener('click', e => {
    const a = e.target.closest('[data-page]');
    if (!a) return;
    e.preventDefault();
    const p = a.dataset.page;
    if (location.hash !== '#' + p) location.hash = p;
    else go(p);
  });
  window.addEventListener('hashchange', () => go(location.hash.replace('#', '')));
  $('#burger').addEventListener('click', () => $('.nav-links').classList.toggle('open'));

  (async function boot() {
    const cfg = await loadConfig();
    if (cfg && cfg.scales) {
      SCALES = cfg.scales;
      LOADED.assess = 0;
    } else {
      // 后端没起来也要让页面可用（用内置最小副本）
      SCALES = {
        GAD7: {
          name: '广泛性焦虑量表 GAD-7', max: 21, options: ['完全不会', '好几天', '一半以上天数', '几乎每天'],
          items: ['感到紧张、焦虑或急切', '无法停止或控制担忧', '对各种各样的事情担忧过多',
            '很难放松下来', '由于不安而无法静坐', '变得容易烦恼或急躁',
            '感到似乎将有可怕的事情发生而害怕']
        },
        PHQ9: {
          name: '患者健康问卷 PHQ-9', max: 27, options: ['完全不会', '好几天', '一半以上天数', '几乎每天'],
          items: ['做事时提不起劲或没有兴趣', '感到心情低落、沮丧或绝望', '入睡困难、睡不安稳或睡得过多',
            '感觉疲倦或没有活力', '食欲不振或吃得太多', '觉得自己很糟，或很失败，或让自己/家人失望',
            '对事物专注有困难', '动作或说话慢到别人都察觉，或相反：烦躁、坐立不安',
            '有不如死掉、或用某种方式伤害自己的念头']
        }
      };
    }
    await go(location.hash.replace('#', '') || 'home');
  })();

})();
