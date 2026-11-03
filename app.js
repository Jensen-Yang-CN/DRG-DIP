const $ = id => document.getElementById(id);
const state = { data: null, diagnoses: [], operations: [], suggestions: { dx: [], op: [] } };
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

function addCode(kind, rawCode, suppliedName = '') {
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
  list.push({ code, name: suppliedName || exactName(code, kind) });
  input.value = '';
  $(kind === 'dx' ? 'diagnosis-suggestions' : 'operation-suggestions').hidden = true;
  $('form-error').hidden = true;
  renderSelected(kind);
  input.focus();
}

function showError(message) {
  $('form-error').textContent = message;
  $('form-error').hidden = false;
}

function setupSearch(kind) {
  const input = $(kind === 'dx' ? 'diagnosis-input' : 'operation-input');
  const popup = $(kind === 'dx' ? 'diagnosis-suggestions' : 'operation-suggestions');
  input.addEventListener('input', () => {
    const query = input.value.trim().toUpperCase();
    clear(popup);
    if (query.length < 2) { popup.hidden = true; return; }
    const starts = [], contains = [];
    for (const item of state.suggestions[kind]) {
      if (item.code.startsWith(query)) starts.push(item);
      else if (item.code.includes(query) || item.name.includes(input.value.trim())) contains.push(item);
      if (starts.length >= 8 && contains.length >= 4) break;
    }
    const found = [...starts.slice(0, 8), ...contains.slice(0, 4)].slice(0, 10);
    if (!found.length) { popup.hidden = true; return; }
    for (const item of found) {
      const option = node('button', 'suggestion');
      option.type = 'button';
      option.append(node('b', '', item.code), node('small', '', item.name));
      option.addEventListener('mousedown', event => {
        event.preventDefault();
        addCode(kind, item.code, item.name);
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

function renderResult(result) {
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
    diagnoses: state.diagnoses.map(item => item.code),
    operations: state.operations.map(item => item.code),
    sex: $('sex').value,
    age: $('age').value,
    ageDays: $('age').value === '0' ? $('age-days').value : null,
    birthWeight: $('weight').value,
    lengthOfStay: $('days').value,
  };
}

async function runGrouping() {
  $('form-error').hidden = true;
  if (!state.data) { showError('规则数据尚未加载完成。'); return; }
  if (!state.diagnoses.length) { showError('请先添加主要诊断。'); $('diagnosis-input').focus(); return; }
  if (Number($('age').value) < 0 || Number($('days').value) < 0 || Number($('weight').value) < 0) { showError('年龄、体重和住院天数不能为负数。'); return; }
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
    showError(`分组服务请求失败：${error.message}`);
  } finally {
    button.disabled = false;
  }
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
  renderSelected('dx'); renderSelected('op');
  await runGrouping();
  $('result-title').scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
}

function initActions() {
  setupSearch('dx'); setupSearch('op');
  $('add-diagnosis').onclick = () => addCode('dx');
  $('add-operation').onclick = () => addCode('op');
  $('run-button').onclick = runGrouping;
  $('clear-button').onclick = () => {
    state.diagnoses = []; state.operations = [];
    renderSelected('dx'); renderSelected('op');
    $('form-error').hidden = true;
    $('trace-card').hidden = true;
    window.location.reload();
  };
  $('age').addEventListener('input', () => { $('age-days-wrap').hidden = $('age').value !== '0'; });
  document.querySelectorAll('[data-example]').forEach(button => button.addEventListener('click', () => fillExample(button.dataset.example)));
}

async function init() {
  initActions();
  try {
    const response = await fetch('./api/catalog');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    state.suggestions = state.data.suggestions;
    $('rule-stats').textContent = `${state.data.coreCount.toLocaleString('zh-CN')} 条核心规则 · ${state.data.grassrootsCount} 条基层病种`;
  } catch (error) {
    $('rule-stats').textContent = '规则加载失败';
    showError(`无法连接 Python 分组服务：${error.message}。请运行 start-demo.cmd 启动。`);
  }
}

init();
