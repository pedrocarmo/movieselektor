(function () {
  var drawInterval = null;

  function startDrawAnimation() {
    var rankEl = document.getElementById('machine-rank');
    var label  = document.getElementById('machine-label');
    var hint   = document.getElementById('machine-hint');
    if (!rankEl) return;
    if (label) label.textContent = 'Drawing…';
    if (hint)  hint.textContent  = '';
    drawInterval = setInterval(function () {
      rankEl.textContent = Math.floor(Math.random() * 1000) + 1;
    }, 60);
  }

  function stopDrawAnimation() {
    if (drawInterval) { clearInterval(drawInterval); drawInterval = null; }
  }

  document.body.addEventListener('htmx:beforeRequest', function (e) {
    var path = e.detail.requestConfig && e.detail.requestConfig.path;
    if (path === '/draw' || path === '/skip') startDrawAnimation();

    // Signal button: show loading text (button is disabled by hx-disabled-elt)
    if (e.target && e.target.id === 'signal-share-btn') {
      e.target.dataset.originalText = e.target.textContent;
      e.target.textContent = '⏳ Sending…';
    }
  });

  document.body.addEventListener('htmx:afterSwap', stopDrawAnimation);
})();
