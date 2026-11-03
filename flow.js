const flowBook = document.getElementById('flow-book');
let activeFlow = 'dip';
let turning = false;

function showFlow(mode) {
  activeFlow = mode;
  document.getElementById('dip-flow').hidden = mode !== 'dip';
  document.getElementById('drg-flow').hidden = mode !== 'drg';
  document.getElementById('flow-brand-rule').textContent =
    `当前流程：${mode === 'drg' ? 'CHS-DRG' : 'CHS-DIP'} 3.0`;
  for (const value of ['dip', 'drg']) {
    const button = document.getElementById(`flow-mode-${value}`);
    button.classList.toggle('active', value === mode);
    button.setAttribute('aria-pressed', String(value === mode));
  }
}

async function turnFlow(mode) {
  if (turning || mode === activeFlow) return;
  turning = true;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!reduced) {
    flowBook.classList.add('page-turn-out');
    await new Promise(resolve => setTimeout(resolve, 220));
  }
  showFlow(mode);
  if (!reduced) {
    flowBook.classList.remove('page-turn-out');
    flowBook.classList.add('page-turn-in');
    await new Promise(resolve => setTimeout(resolve, 380));
    flowBook.classList.remove('page-turn-in');
  }
  turning = false;
  window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' });
}

document.getElementById('flow-mode-dip').addEventListener('click', () => turnFlow('dip'));
document.getElementById('flow-mode-drg').addEventListener('click', () => turnFlow('drg'));
