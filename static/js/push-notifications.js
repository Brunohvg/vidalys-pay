/* Vidalys Pay — Web Push controller */
(function () {
    'use strict';
    var button;
    var subscription;
    var config;
    var onboarding;
    var onboardingTrigger;
    var ONBOARDING_KEY = 'vidalys.pushOnboarding';
    var SNOOZE_DAYS = 7;

    function isStandalone() {
        return window.matchMedia('(display-mode: standalone)').matches
            || window.navigator.standalone === true;
    }

    function setState(state, detail) {
        if (!button) return;
        var title = button.querySelector('.profile-action__text');
        var hint = button.querySelector('small');
        button.dataset.state = state;
        button.disabled = state === 'loading' || state === 'unavailable';
        if (state === 'loading') { title.textContent = 'Verificando notificações…'; hint.textContent = 'Aguarde um instante'; }
        if (state === 'enabled') { title.textContent = 'Notificações ativadas'; hint.textContent = detail || 'Toque para desativar neste aparelho'; }
        if (state === 'disabled') { title.textContent = 'Ativar notificações'; hint.textContent = detail || 'Receba atualizações de pagamentos'; }
        if (state === 'denied') { title.textContent = 'Notificações bloqueadas'; hint.textContent = 'Libere nas configurações do aparelho'; }
        if (state === 'unavailable') { title.textContent = 'Notificações indisponíveis'; hint.textContent = detail || 'Este navegador não oferece suporte'; }
    }

    function saveOnboarding(state, until) {
        try { localStorage.setItem(ONBOARDING_KEY, JSON.stringify({state: state, until: until || 0})); }
        catch (_) {}
    }

    function shouldShowOnboarding() {
        if (!isStandalone() || Notification.permission !== 'default' || subscription) return false;
        try {
            var saved = JSON.parse(localStorage.getItem(ONBOARDING_KEY) || '{}');
            if (saved.state === 'enabled' || saved.state === 'denied') return false;
            if (saved.state === 'snoozed' && Number(saved.until) > Date.now()) return false;
        } catch (_) {}
        return true;
    }

    function hideOnboarding() {
        if (!onboarding) return;
        onboarding.classList.remove('is-visible');
        document.body.classList.remove('push-onboarding-open');
        window.setTimeout(function () {
            if (onboarding) onboarding.hidden = true;
        }, 220);
        if (onboardingTrigger && typeof onboardingTrigger.focus === 'function') onboardingTrigger.focus();
    }

    function snoozeOnboarding() {
        saveOnboarding('snoozed', Date.now() + SNOOZE_DAYS * 24 * 60 * 60 * 1000);
        hideOnboarding();
    }

    function showOnboarding() {
        if (onboarding || !shouldShowOnboarding()) return;
        onboardingTrigger = document.activeElement;
        onboarding = document.createElement('div');
        onboarding.className = 'push-onboarding';
        onboarding.hidden = true;
        onboarding.setAttribute('role', 'dialog');
        onboarding.setAttribute('aria-modal', 'true');
        onboarding.setAttribute('aria-labelledby', 'push-onboarding-title');
        onboarding.innerHTML =
            '<div class="push-onboarding__backdrop"></div>' +
            '<section class="push-onboarding__sheet">' +
            '  <div class="push-onboarding__handle" aria-hidden="true"></div>' +
            '  <div class="push-onboarding__icon" aria-hidden="true"><span></span></div>' +
            '  <p class="push-onboarding__eyebrow">Acompanhe em tempo real</p>' +
            '  <h2 id="push-onboarding-title">Receba avisos dos seus pagamentos</h2>' +
            '  <p class="push-onboarding__description">Você será avisado sobre pagamentos aprovados ou recusados, cancelamentos, expirações, reembolsos e chargebacks.</p>' +
            '  <div class="push-onboarding__actions">' +
            '    <button type="button" class="push-onboarding__enable">Ativar notificações</button>' +
            '    <button type="button" class="push-onboarding__later">Agora não</button>' +
            '  </div>' +
            '</section>';
        document.body.appendChild(onboarding);
        onboarding.querySelector('.push-onboarding__backdrop').addEventListener('click', snoozeOnboarding);
        onboarding.querySelector('.push-onboarding__later').addEventListener('click', snoozeOnboarding);
        onboarding.querySelector('.push-onboarding__enable').addEventListener('click', async function () {
            var enableButton = onboarding.querySelector('.push-onboarding__enable');
            enableButton.disabled = true;
            enableButton.textContent = 'Ativando…';
            try {
                var enabled = await enable();
                if (enabled) {
                    saveOnboarding('enabled');
                    hideOnboarding();
                } else {
                    saveOnboarding(Notification.permission === 'denied' ? 'denied' : 'snoozed', Date.now() + SNOOZE_DAYS * 24 * 60 * 60 * 1000);
                    hideOnboarding();
                }
            } catch (error) {
                enableButton.disabled = false;
                enableButton.textContent = 'Tentar novamente';
                showToast(error.message, 'error');
            }
        });
        onboarding.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') snoozeOnboarding();
        });
        onboarding.hidden = false;
        document.body.classList.add('push-onboarding-open');
        requestAnimationFrame(function () {
            onboarding.classList.add('is-visible');
            onboarding.querySelector('.push-onboarding__enable').focus();
        });
    }

    async function api(method, payload) {
        var response = await fetch('/api/v1/me/push-subscriptions/', {
            method: method,
            credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken()},
            body: payload ? JSON.stringify(payload) : undefined,
        });
        var data = response.status === 204 ? {} : await response.json();
        if (!response.ok) throw new Error(data.error || 'Não foi possível configurar notificações.');
        return data;
    }

    function applicationServerKey(value) {
        var padding = '='.repeat((4 - value.length % 4) % 4);
        var base64 = (value + padding).replace(/-/g, '+').replace(/_/g, '/');
        var raw = atob(base64);
        return Uint8Array.from(Array.prototype.map.call(raw, function (char) { return char.charCodeAt(0); }));
    }

    async function enable() {
        if (Notification.permission === 'denied') { setState('denied'); return false; }
        var permission = await Notification.requestPermission();
        if (permission !== 'granted') { setState(permission === 'denied' ? 'denied' : 'disabled'); return false; }
        setState('loading');
        var registration = await navigator.serviceWorker.ready;
        subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: applicationServerKey(config.data.public_key),
        });
        await api('POST', subscription.toJSON());
        setState('enabled');
        showToast('Notificações ativadas neste aparelho.', 'success');
        return true;
    }

    async function disable() {
        setState('loading');
        var currentSubscription = subscription;
        var endpoint = currentSubscription && currentSubscription.endpoint;
        if (!endpoint) {
            var registration = await navigator.serviceWorker.ready;
            currentSubscription = await registration.pushManager.getSubscription();
            endpoint = currentSubscription && currentSubscription.endpoint;
        }
        if (endpoint) await api('DELETE', {endpoint: endpoint});
        if (currentSubscription) {
            try { await currentSubscription.unsubscribe(); }
            catch (_) { /* The server is already disabled; stale browser state is harmless. */ }
        }
        subscription = null;
        saveOnboarding('snoozed', Date.now() + SNOOZE_DAYS * 24 * 60 * 60 * 1000);
        setState('disabled');
        if ('clearAppBadge' in navigator) navigator.clearAppBadge().catch(function () {});
        showToast('Notificações desativadas.', 'success');
    }

    async function init() {
        button = document.getElementById('push-notification-button');
        if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
            setState('unavailable', 'Instale o app ou use um navegador compatível'); return;
        }
        setState('loading');
        try {
            config = await api('GET');
            if (!config.data.available || !config.data.public_key) {
                setState('unavailable', 'Configuração pendente no servidor'); return;
            }
            var registration = await navigator.serviceWorker.ready;
            subscription = await registration.pushManager.getSubscription();
            if (Notification.permission === 'denied') {
                saveOnboarding('denied');
                setState('denied');
            } else if (subscription) {
                saveOnboarding('enabled');
                await api('POST', subscription.toJSON());
                setState('enabled');
            } else {
                setState('disabled');
                window.setTimeout(showOnboarding, 700);
            }
        } catch (error) {
            setState('unavailable', error.message);
        }
        if (button) button.addEventListener('click', async function () {
            try { if (subscription) await disable(); else await enable(); }
            catch (error) { setState(subscription ? 'enabled' : 'disabled'); showToast(error.message, 'error'); }
        });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
