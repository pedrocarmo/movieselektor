(function () {
  var MIN_MS = 3000;
  var drawInterval = null;
  var drawStart    = null;

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
    stopDrawAnimation();
    var pickArea = document.getElementById('pick-area');
    if (pickArea) pickArea.innerHTML = machineCardHTML();
    drawInterval = setInterval(function () {
      var el = document.getElementById('machine-rank');
      if (el) el.textContent = Math.floor(Math.random() * 1000) + 1;
    }, 60);
  }

  function stopDrawAnimation() {
    if (drawInterval) { clearInterval(drawInterval); drawInterval = null; }
  }

  // Record draw start + kick off animation for draw/skip requests.
  document.body.addEventListener('htmx:beforeRequest', function (e) {
    var path = e.detail.requestConfig && e.detail.requestConfig.path;
    if (path === '/draw' || path === '/skip') {
      drawStart = Date.now();
      startDrawAnimation();
    }
    // Signal button: show loading text while the request is in flight.
    if (e.target && e.target.id === 'signal-share-btn') {
      e.target.textContent = '⏳ Sending…';
    }
  });

  // When the response arrives, hold the swap until MIN_MS has elapsed.
  document.body.addEventListener('htmx:beforeSwap', function (e) {
    var path = e.detail.requestConfig && e.detail.requestConfig.path;
    if ((path !== '/draw' && path !== '/skip') || drawStart === null) return;

    var remaining = MIN_MS - (Date.now() - drawStart);
    drawStart = null;

    if (remaining <= 0) {
      stopDrawAnimation();
      return; // response already took long enough — swap immediately
    }

    // Cancel HTMX's automatic swap and reschedule it ourselves.
    // e.detail.swapSpec is absent in HTMX 2.0.4, so supply it explicitly.
    e.detail.shouldSwap = false;
    var target   = e.detail.target;
    var content  = e.detail.serverResponse;

    setTimeout(function () {
      stopDrawAnimation();
      htmx.swap(target, content, { swapStyle: 'outerHTML' });
    }, remaining);
  });
})();
