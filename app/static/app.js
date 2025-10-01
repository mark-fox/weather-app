// Minimal, unobtrusive JS: attach behavior if the elements exist.
(function () {
  function initUseMyLocation(buttonId, messageId) {
    const btn = document.getElementById(buttonId);
    const msg = document.getElementById(messageId);
    if (!btn || !msg) return;

    if (!('geolocation' in navigator)) {
      btn.disabled = true;
      msg.textContent = ' Geolocation not supported by this browser.';
      return;
    }

    btn.addEventListener('click', function () {
      msg.textContent = ' Getting your location…';
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          const lat = pos.coords.latitude.toFixed(6);
          const lon = pos.coords.longitude.toFixed(6);
          const params = new URLSearchParams({
            q: '',
            name: 'Your location',
            lat: String(lat),
            lon: String(lon)
          });
          window.location.href = '/result?' + params.toString();
        },
        function (err) {
          if (err.code === 1) {
            msg.textContent = ' Permission denied. Please allow location access or type a city.';
          } else {
            msg.textContent = ' Could not get location. Try again or type a city.';
          }
        },
        { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 }
      );
    });
  }

  // Initialize on both pages if present
  document.addEventListener('DOMContentLoaded', function () {
    initUseMyLocation('use-loc-btn', 'use-loc-msg');       // index.html
    initUseMyLocation('use-loc-btn-result', 'use-loc-msg-result'); // result.html (optional)
  });
}());
