const $ = id => document.getElementById(id);
const state = {
  mode: 'dip', data: null, dipData: null, drgData: null, diagnoses: [], operations: [],
  suggestions: { dx: [], op: [] }, switching: false,
};
const norm = value => String(value ?? '').trim().toUpperCase().replace(/\s+/g, '');

function node(tag, className = '', content = '') {
  const result = document.createElement(tag);
  if (className) result.className = className;
  if (content) result.textContent = content;
  return result;
}

function clear(element) { element.replaceChildren(); }

function exactName(code, kind) {
  return state.suggestions[kind].find(item => item.code === code)?.name ?? '';
}

async function searchDrg(kind, query) {
  const url = `./api/search?mode=drg&kind=${kind}&q=${encodeURIComponent(query)}`;
  const response = await fetch(url);
  if (!response.ok) throw new Error('编码字典查询失败');
  return (await response.json()).suggestions;
}

function renderSelected(kind) {
  const list = kind === 'dx' ? state.diagnoses : state.operations;
  const container = $(kind === 'dx' ? 'diagnosis-list' : 'operation-list');
  $(kind === 'dx' ? 'dx-count' : 'op-count').textContent = `${list.length} 项`;
  clear(container);
  list.forEach((item, index) => {
    const row = node('div', `selected-item ${index === 0 ? 'main' : ''}`);
    row.append(node('span', 'item-order', String(index + 1)));
    const body = node('div', 'item-body');
    const top = node('div', 'item-top');
    top.append(node('span', 'item-code', item.code));
    if (index === 0) top.append(node('span', 'item-tag', kind === 'dx' ? '主诊断' : '主操作'));
    if (index > 0 && item.ccType && state.mode === 'drg') {
      top.append(node('span', 'item-tag severity', item.ccType));
    }
    body.append(top);
    const name = item.name || exactName(item.code, kind);
    if (name) body.append(node('div', 'item-name', name));
    row.append(body);
    const remove = node('button', 'remove-item', '×');
    remove.type = 'button';
    remove.setAttribute('aria-label', `移除 ${item.code}`);
    remove.onclick = () => { list.splice(index, 1); renderSelected(kind); };
    row.append(remove);
    container.append(row);
  });
}

async function addCode(kind, rawCode, suppliedName = '', ccType = '') {
  const input = $(kind === 'dx' ? 'diagnosis-input' : 'operation-input');
  const code = norm(rawCode || input.value);
  const list = kind === 'dx' ? state.diagnoses : state.operations;
  if (!code) return;
  if (!/^[A-Z][A-Z0-9.]*$/i.test(code) && !/^[0-9][A-Z0-9.]*$/i.test(code)) {
    showError('请输入编码；如需按名称查找，请从下拉建议中选取。');
    return;
  }
  if (list.some(item => item.code === code)) {
    showError(`${code} 已添加，请勿重复输入。`);
    return;
  }
  const item = { code, name: suppliedName || (state.mode === 'dip' ? exactName(code, kind) : ''), ccType };
  list.push(item);
  input.value = '';
  $(kind === 'dx' ? 'diagnosis-suggestions' : 'operation-suggestions').hidden = true;
  $('form-error').hidden = true;
  renderSelected(kind);
  input.focus();
  if (state.mode === 'drg' && !suppliedName) {
    try {
      const found = (await searchDrg(kind, code)).find(result => result.code === code);
      if (found && list.includes(item)) {
        item.name = found.name;
        item.ccType = found.ccType || '';
        renderSelected(kind);
      }
    } catch (_) { /* The code remains usable even if its display name is unavailable. */ }
  }
}

function showError(message) {
  $('form-error').textContent = message;
  $('form-error').hidden = false;
}

function setupSearch(kind) {
  const input = $(kind === 'dx' ? 'diagnosis-input' : 'operation-input');
  const popup = $(kind === 'dx' ? 'diagnosis-suggestions' : 'operation-suggestions');
  let requestNumber = 0;
  input.addEventListener('input', async () => {
    const currentRequest = ++requestNumber;
    const requestMode = state.mode;
    const query = input.value.trim().toUpperCase();
    clear(popup);
    if (query.length < 2) { popup.hidden = true; return; }
    let found = [];
    if (state.mode === 'drg') {
      try { found = await searchDrg(kind, input.value.trim()); }
      catch (_) { popup.hidden = true; return; }
    } else {
      const starts = [], contains = [];
      for (const item of state.suggestions[kind]) {
        if (item.code.startsWith(query)) starts.push(item);
        else if (item.code.includes(query) || item.name.includes(input.value.trim())) contains.push(item);
        if (starts.length >= 8 && contains.length >= 4) break;
      }
      found = [...starts.slice(0, 8), ...contains.slice(0, 4)].slice(0, 10);
    }
    if (currentRequest !== requestNumber || state.mode !== requestMode ||
        input.value.trim().toUpperCase() !== query) return;
    if (!found.length) { popup.hidden = true; return; }
    for (const item of found) {
      const option = node('button', 'suggestion');
      option.type = 'button';
      option.append(node('b', '', item.code), node('small', '', item.name));
      option.addEventListener('mousedown', event => {
        event.preventDefault();
        addCode(kind, item.code, item.name, item.ccType || '');
      });
      popup.append(option);
    }
    popup.hidden = false;
  });
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter') { event.preventDefault(); addCode(kind); }
    if (event.key === 'Escape') popup.hidden = true;
  });
  input.addEventListener('blur', () => setTimeout(() => { popup.hidden = true; }, 120));
}

function detail(container, label, value, extra = '') {
  const box = node('div', `result-detail ${extra}`);
  box.append(node('div', 'detail-label', label), node('div', 'detail-value', value || '—'));
  container.append(box);
}

function ruleLine(box, label, value) {
  const line = node('div', 'rule-line');
  line.append(node('em', '', label), node('code', '', value || '无'));
  box.append(line);
}

function renderDrgResult(result) {
  const root = $('result-content');
  clear(root);
  $('trace-card').hidden = false;
  renderTrace(result.trace);
  const hero = node('div', 'result-hero');
  hero.append(node('div', `result-status ${result.hit ? '' : 'warn'}`,
    result.hit ? '分组成功 · CHS-DRG 3.0' : '未能完成 DRG 分组'));
  if (!result.hit) {
    hero.append(node('h3', '', '未入组'), node('p', '', result.message));
    root.append(hero);
    return;
  }
  const hit = result.hit;
  hero.append(node('h3', '', hit.code), node('p', '', hit.name));
  const chips = node('div', 'result-chips');
  chips.append(node('span', 'result-chip', hit.weight ? `参考权重 ${hit.weight}` : '参考权重：暂无参考数据'));
  chips.append(node('span', 'result-chip fee-chip',
    hit.fee ? `参考费用 ${Number(hit.fee).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} 元` : '参考费用：暂无参考数据'));
  if (hit.label) chips.append(node('span', 'result-chip neutral', hit.label));
  hero.append(chips);
  root.append(hero);
  const grid = node('div', 'result-grid path-grid');
  for (const [key, label] of [['mdc', 'MDC 大类'], ['adrg', 'ADRG 核心病组'], ['drg', '最终 DRG']]) {
    const row = result.path[key];
    detail(grid, label, row ? `${row.code} · ${row.name}` : '未命中');
  }
  root.append(grid);
  const rules = node('div', 'rule-box');
  rules.append(node('strong', '', '最终病组的判断条件'));
  ruleLine(rules, 'ADRG', result.path.adrg?.rule || '先期分组');
  ruleLine(rules, 'DRG', result.path.drg?.rule || '本 ADRG 的默认末档');
  root.append(rules);
  const note = node('p', 'reference-note',
    '金额来自 CHS-DRG 3.0 参考表，是参考费用，不代表实际医保结算款。');
  root.append(note);
}

function renderResult(result) {
  if (result.scheme === 'drg') { renderDrgResult(result); return; }
  const root = $('result-content');
  clear(root);
  $('trace-card').hidden = false;
  renderTrace(result.trace);

  const hero = node('div', 'result-hero');
  const status = node('div', `result-status ${result.status === 'matched' ? '' : 'warn'}`, result.status === 'matched' ? '匹配完成 · 核心病种' : '规则检查结果');
  hero.append(status);
  if (result.hit) {
    hero.append(node('h3', '', result.hit.key), node('p', '', result.hit.name));
    const chips = node('div', 'result-chips');
    chips.append(node('span', 'result-chip', result.hit.sectionLabel), node('span', 'result-chip neutral', `表内序号 ${result.hit.number}`));
    if (result.grassroots?.length) chips.append(node('span', 'result-chip', `基层病种 · 第 ${result.grassroots[0].number} 项`));
    hero.append(chips);
    root.append(hero);
    const grid = node('div', 'result-grid');
    detail(grid, '规则分类', `${result.hit.category} · ${result.hit.sectionLabel}`);
    detail(grid, '规则来源', `${result.sourceSheetName} · 第 ${result.hit.row} 行`);
    detail(grid, '输入主诊断', result.processed.principalDx);
    detail(grid, '输入主操作', result.processed.mainOperation || '未填写');
    root.append(grid);
    const rules = node('div', 'rule-box');
    rules.append(node('strong', '', '命中条件'));
    ruleLine(rules, '主诊断', result.hit.diagnosisRule);
    ruleLine(rules, '操作', result.hit.operationRule);
    if (result.hit.auxiliaryRule) ruleLine(rules, '附加条件', result.hit.auxiliaryRule);
    root.append(rules);
    if (result.alternatives.length) {
      const more = node('details', 'alternatives');
      more.append(node('summary', '', `另有 ${result.alternatives.length} 条候选规则，点击查看`));
      const list = node('ul');
      result.alternatives.forEach(item => list.append(node('li', '', `${item.key} · ${item.name}`)));
      more.append(list);
      root.append(more);
    }
  } else {
    hero.append(node('h3', '', result.status === 'excluded' ? '不纳入分组' : result.status === 'unmatched' ? '未命中核心规则' : '需要核对输入'));
    hero.append(node('p', '', result.message));
    const chips = node('div', 'result-chips');
    chips.append(node('span', 'result-chip neutral', result.status === 'unmatched' ? '不自动判定为综合病种' : '已停止后续规则匹配'));
    hero.append(chips);
    root.append(hero);
    if (result.status === 'unmatched') {
      const box = node('div', 'rule-box');
      box.append(node('strong', '', '下一步建议'), node('div', 'detail-value', '请核对主诊断、主操作及其他诊断、操作是否录入完整。'));
      root.append(box);
    }
  }
}

function renderTrace(trace) {
  const list = $('trace-list');
  clear(list);
  trace.forEach(item => {
    const row = node('div', `trace-item ${item.state}`);
    row.append(node('span', 'trace-indicator', item.state === 'passed' ? '✓' : item.state === 'blocked' ? '!' : item.state === 'info' ? 'i' : '–'));
    const body = node('div');
    body.append(node('strong', '', item.title), node('p', '', item.detail));
    row.append(body);
    list.append(row);
  });
}

function currentCase() {
  return {
    mode: state.mode,
    diagnoses: state.diagnoses.map(item => item.code),
    operations: state.operations.map(item => item.code),
    sex: $('sex').value,
    age: $('age').value,
    ageDays: $('age').value === '0' ? $('age-days').value : null,
    birthWeight: $('weight').value,
    admissionWeight: $('weight').value,
    lengthOfStay: $('days').value,
  };
}

async function runGrouping() {
  $('form-error').hidden = true;
  if (!state.data) { showError('规则数据尚未加载完成。'); return; }
  if (!state.diagnoses.length) { showError('请先添加主要诊断。'); $('diagnosis-input').focus(); return; }
  if ($('weight').value.trim() && !/^\d+$/.test($('weight').value.trim())) {
    showError('入院体重只能填写数字，不要附加 g 等单位。'); $('weight').focus(); return;
  }
  if (Number($('age').value) < 0 || Number($('days').value) < 0) {
    showError('年龄和住院天数不能为负数。'); return;
  }
  const button = $('run-button');
  button.disabled = true;
  try {
    const response = await fetch('./api/group', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentCase()),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    renderResult(result);
  } catch (error) {
    showError(error.message);
  } finally {
    button.disabled = false;
  }
}

function renderEmpty() {
  const root = $('result-content');
  clear(root);
  const empty = node('div', 'empty-state');
  empty.append(node('div', 'empty-icon', '◎'));
  empty.append(node('h3', '', '等待录入病例'));
  empty.append(node('p', '', state.mode === 'drg'
    ? '填写主要诊断后点击“执行 DRG 分组”，这里会显示 MDC → ADRG → DRG 的结果、参考权重和费用。'
    : '填写主要诊断后点击“执行 DIP 分组”，这里会显示命中的核心病种和依据。'));
  root.append(empty);
  $('trace-card').hidden = true;
}

function applyMode(mode) {
  state.mode = mode;
  state.data = mode === 'dip' ? state.dipData : state.drgData;
  for (const value of ['dip', 'drg']) {
    const button = $(`mode-${value}`);
    button.classList.toggle('active', value === mode);
    button.setAttribute('aria-pressed', String(value === mode));
  }
  const drg = mode === 'drg';
  $('brand-rule').textContent = `当前规则：全国版 ${drg ? 'CHS-DRG' : 'CHS-DIP'} 3.0`;
  $('topbar-mode').textContent = drg ? 'CHS-DRG 3.0' : 'CHS-DIP 3.0';
  $('intro-eyebrow').textContent = drg ? 'CHS-DRG · 3.0' : 'CHS-DIP · 3.0';
  $('intro-copy').textContent = drg
    ? '按 MDC、ADRG、DRG 逐级匹配，查看病组、参考权重与费用。'
    : '录入主要诊断及诊疗信息，查看命中的核心病种规则与逐步判断依据。';
  $('input-mode-chip').textContent = drg ? '全国版 CHS-DRG 3.0' : '全国版 CHS-DIP 3.0';
  $('result-mode-chip').textContent = $('input-mode-chip').textContent;
  $('run-label').textContent = drg ? '执行 DRG 分组' : '执行 DIP 分组';
  $('diagnosis-input').placeholder = drg
    ? '输入 ICD 医保编码或诊断名称，如 J18.000'
    : '输入 ICD-10 编码或诊断名称，如 J18.900';
  $('operation-input').placeholder = drg
    ? '输入手术操作编码或名称，如 96.7201'
    : '输入操作编码或名称，如 33.2402';
  $('basic-hint').textContent = drg
    ? '年龄、性别、天龄和入院体重可能参与 DRG 规则判断'
    : '用于呈现完整病例；特殊规则会读取天龄与入院体重';
  $('dip-explorer').hidden = drg;
  $('drg-explorer').hidden = !drg;
  $('rule-stats').textContent = drg
    ? `${state.drgData?.mdcCount || 0} 条 MDC 规则 · ${state.drgData?.adrgCount || 0} 条 ADRG 规则 · ${state.drgData?.drgCount || 0} 条 DRG 规则`
    : `${state.dipData?.coreCount.toLocaleString('zh-CN') || 0} 条核心规则 · ${state.dipData?.grassrootsCount || 0} 条基层病种`;
  $('form-error').hidden = true;
  for (const id of ['diagnosis-suggestions', 'operation-suggestions']) $(id).hidden = true;
  renderSelected('dx'); renderSelected('op'); renderEmpty();
}

async function switchMode(mode) {
  if (mode === state.mode || state.switching) return;
  if (!(mode === 'drg' ? state.drgData : state.dipData)) {
    showError('该分组方案的规则数据尚未加载完成。'); return;
  }
  const page = $('page-book');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  state.switching = true;
  if (!reduced) {
    page.classList.add('mode-fade-out');
    await new Promise(resolve => setTimeout(resolve, 120));
  }
  applyMode(mode);
  if (!reduced) {
    page.classList.remove('mode-fade-out');
    page.classList.add('mode-fade-in');
    await new Promise(resolve => setTimeout(resolve, 180));
    page.classList.remove('mode-fade-in');
  }
  state.switching = false;
}

async function fillExample(kind) {
  state.diagnoses = [];
  state.operations = [];
  $('sex').value = '女';
  $('age').value = '30';
  $('weight').value = '';
  $('days').value = '12';
  $('age-days-wrap').hidden = true;
  if (kind === 'conservative') state.diagnoses.push({ code: 'J18.900', name: '肺炎' });
  if (kind === 'procedure') {
    state.diagnoses.push({ code: 'J18.900', name: '肺炎' });
    state.operations.push({ code: '33.2402', name: '超声内镜下支气管穿刺活组织检查术' });
  }
  if (kind === 'tumor') {
    state.diagnoses.push({ code: 'Z51.101', name: '肿瘤化学治疗' }, { code: 'C34.901', name: '支气管恶性肿瘤' });
    state.operations.push({ code: '99.2503', name: '静脉注射化疗药物' }, { code: '99.2800X005', name: '静脉注射抗肿瘤免疫制剂治疗' });
  }
  if (kind.startsWith('drg-')) {
    $('sex').value = '男';
    $('days').value = '15';
    state.diagnoses.push({ code: 'J18.000', name: '支气管肺炎' });
    if (kind === 'drg-mcc') {
      state.diagnoses.push({ code: 'N39.000', name: '泌尿道感染', ccType: 'CC' },
        { code: 'N17.900', name: '急性肾衰竭', ccType: 'MCC' });
    }
    if (kind === 'drg-operation') {
      state.operations.push({ code: '96.7201', name: '呼吸机治疗[大于等于96小时]' },
        { code: '33.2400X001', name: '支气管镜下支气管活检' });
    }
  }
  renderSelected('dx'); renderSelected('op');
  await runGrouping();
  $('result-title').scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
}

function initActions() {
  setupSearch('dx'); setupSearch('op');
  $('add-diagnosis').onclick = () => addCode('dx');
  $('add-operation').onclick = () => addCode('op');
  $('run-button').onclick = runGrouping;
  $('mode-dip').onclick = () => switchMode('dip');
  $('mode-drg').onclick = () => switchMode('drg');
  $('clear-button').onclick = () => {
    state.diagnoses = []; state.operations = [];
    renderSelected('dx'); renderSelected('op');
    $('form-error').hidden = true;
    $('age').value = '30'; $('age-days').value = ''; $('age-days-wrap').hidden = true;
    $('weight').value = ''; $('days').value = '12';
    $('diagnosis-input').value = ''; $('operation-input').value = '';
    renderEmpty();
  };
  $('age').addEventListener('input', () => { $('age-days-wrap').hidden = $('age').value !== '0'; });
  document.querySelectorAll('[data-example]').forEach(button => button.addEventListener('click', () => fillExample(button.dataset.example)));
}

async function init() {
  initActions();
  try {
    const response = await fetch('./api/catalog');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.dipData = await response.json();
    state.data = state.dipData;
    state.suggestions = state.dipData.suggestions;
    applyMode('dip');
  } catch (error) {
    $('rule-stats').textContent = '规则加载失败';
    showError(`无法连接 Python 分组服务：${error.message}。请在项目目录的终端运行 python server.py。`);
  }
  try {
    const response = await fetch('./api/catalog?mode=drg');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.drgData = await response.json();
  } catch (error) {
    showError(`DRG 规则加载失败：${error.message}`);
  }
}

init();
