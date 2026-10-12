/* Presentation only: retain the ticket and chart nodes, including pending edits. */
(() => {
  'use strict';
  const button = document.getElementById('toggle-trading-panel');
  const panel = document.getElementById('trade');
  if (!button || !panel) return;
  const key = 'wheel.tradingPanelCollapsed';
  let collapsed = false;
  try { collapsed = localStorage.getItem(key) === 'true'; } catch (_) {}
  function render() {
    panel.hidden = collapsed;
    document.body.classList.toggle('trading-panel-collapsed', collapsed);
    button.setAttribute('aria-expanded', String(!collapsed));
    const zh = document.documentElement.lang.startsWith('zh');
    const label = zh ? (collapsed ? '展开交易面板' : '收起交易面板')
      : (collapsed ? 'Show trading panel' : 'Hide trading panel');
    button.setAttribute('aria-label', label);
    button.title = label;
  }
  button.addEventListener('click', () => {
    collapsed = !collapsed;
    render();
    try { localStorage.setItem(key, String(collapsed)); } catch (_) {}
  });
  new MutationObserver(render).observe(document.documentElement, {
    attributes: true, attributeFilter: ['lang']
  });
  render();
})();
