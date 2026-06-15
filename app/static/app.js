(function () {
  var drawInterval = null;

  function machineCardHTML() {
    return '<div class="machine-card" id="machine-card">'
      + '<div class="machine-dots"></div>'
      + '<div class="machine-screen">'
      + '<p class="machine-label" id="machine-label">Drawing…</p>'
      + '<p class="machine-rank">#<span id="machine-rank">—</span></p>'
      + '<p class="machine-hint" id="machine-hint"></p>'
      + '</div>'
      + '<div class="machine-dots"></div>'
      + '</div>';
  }

  function startDrawAnimation() {
    var rankEl = document.getElementById('machine-rank');
    if (!rankEl) return;
    stopDrawAnimation();
    drawInterval = setInterval(function () {
      rankEl.textContent = Math.floor(Math.random() * 1000) + 1;
    }, 60);
  }

  function stopDrawAnimation() {
    if (drawInterval) { clearInterval(drawInterval); drawInterval = null; }
  }

  document.body.addEventListener('htmx:beforeRequest', function (e) {
    var path = e.detail.requestConfig && e.detail.requestConfig.path;

    if (path === '/draw' || path === '/skip') {
      // Replace whatever is in pick-area with the machine card so the
      // animation runs regardless of which state we're coming from.
      var pickArea = document.getElementById('pick-area');
      if (pickArea) pickArea.innerHTML = machineCardHTML();
      startDrawAnimation();
    }

    // Signal button: show loading text while the request is in flight.
    if (e.target && e.target.id === 'signal-share-btn') {
      e.target.textContent = '⏳ Sending…';
    }
  });

  document.body.addEventListener('htmx:afterSwap', stopDrawAnimation);
})();
