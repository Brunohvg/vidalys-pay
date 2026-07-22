/* Vidalys Pay — Web Push controller */
(function () {
    'use strict';
    var button;
    var subscription;
    var config;

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
        if (Notification.permission === 'denied') { setState('denied'); return; }
        var permission = await Notification.requestPermission();
        if (permission !== 'granted') { setState(permission === 'denied' ? 'denied' : 'disabled'); return; }
        setState('loading');
        var registration = await navigator.serviceWorker.ready;
        subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: applicationServerKey(config.data.public_key),
        });
        await api('POST', subscription.toJSON());
        setState('enabled');
        showToast('Notificações ativadas neste aparelho.', 'success');
    }

    async function disable() {
        setState('loading');
        var json = subscription.toJSON();
        await api('DELETE', {endpoint: json.endpoint});
        await subscription.unsubscribe();
        subscription = null;
        setState('disabled');
        if ('clearAppBadge' in navigator) navigator.clearAppBadge().catch(function () {});
        showToast('Notificações desativadas.', 'success');
    }

    async function init() {
        button = document.getElementById('push-notification-button');
        if (!button) return;
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
            if (Notification.permission === 'denied') setState('denied');
            else setState(subscription ? 'enabled' : 'disabled');
        } catch (error) {
            setState('unavailable', error.message);
        }
        button.addEventListener('click', async function () {
            try { if (subscription) await disable(); else await enable(); }
            catch (error) { setState('disabled'); showToast(error.message, 'error'); }
        });
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
