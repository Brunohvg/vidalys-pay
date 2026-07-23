/* Vidalys Pay — Seller App Runtime v4 */
(function () {
    'use strict';

    var splash = document.getElementById('appSplash');
    var splashStartedAt = performance.now();
    var firstOpen = false;
    try {
        firstOpen = !sessionStorage.getItem('vidalys-app-ready-v5');
        if (firstOpen) sessionStorage.setItem('vidalys-app-ready-v5', '1');
    } catch (_) {}

    function revealApp() {
        document.body.classList.add('app-ready');
        if (splash) {
            splash.classList.add('app-splash--hide');
            window.setTimeout(function () { splash.remove(); }, 220);
        }
    }

    if (splash && firstOpen) {
        splash.classList.add('app-splash--visible');
        window.addEventListener('load', function () {
            var elapsed = performance.now() - splashStartedAt;
            window.setTimeout(revealApp, Math.max(0, 900 - elapsed));
        }, { once: true });
        window.setTimeout(revealApp, 1800);
    } else {
        if (splash) splash.remove();
        requestAnimationFrame(function () { document.body.classList.add('app-ready'); });
    }

    window.showToast = function (message, type, duration) {
        var toast = document.getElementById('toast');
        if (!toast) return;
        toast.className = 'toast';
        if (type) toast.classList.add('toast--' + type);
        toast.textContent = message;
        toast.classList.add('show');
        clearTimeout(window.__vidalysToastTimer);
        window.__vidalysToastTimer = setTimeout(function () { toast.classList.remove('show'); }, duration || 2400);
    };

    window.updateOnlineStatus = function () {
        var online = navigator.onLine;
        var banner = document.getElementById('offlineBanner');
        var status = document.getElementById('connectionStatus');
        document.body.classList.toggle('offline', !online);
        if (banner) banner.hidden = online;
        if (status) status.textContent = online ? 'Online' : 'Offline';
    };

    window.getCsrfToken = function () {
        var input = document.querySelector('[name=csrfmiddlewaretoken]');
        if (input) return input.value;
        var cookie = document.cookie.split(';').find(function (c) { return c.trim().startsWith('csrftoken='); });
        return cookie ? cookie.split('=')[1] : '';
    };

    window.formatCurrency = function (cents) {
        return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(cents / 100);
    };

    function addPressFeedback() {
        document.addEventListener('pointerdown', function (event) {
            var target = event.target.closest('button, .btn-primary, .btn-secondary, .btn-whatsapp, .link-card__action, .nav a');
            if (target && !target.disabled) target.classList.add('is-pressed');
        }, { passive: true });
        ['pointerup', 'pointercancel'].forEach(function (name) {
            document.addEventListener(name, function () {
                document.querySelectorAll('.is-pressed').forEach(function (el) { el.classList.remove('is-pressed'); });
            }, { passive: true });
        });
    }

    if ('serviceWorker' in navigator) {
        window.addEventListener('load', function () {
            navigator.serviceWorker.register('/sw.js', { scope: '/app/' }).catch(function () {});
        }, { once: true });
    }
    window.addEventListener('online', window.updateOnlineStatus);
    window.addEventListener('offline', window.updateOnlineStatus);
    document.addEventListener('DOMContentLoaded', function () {
        window.updateOnlineStatus();
        addPressFeedback();
    });
})();
