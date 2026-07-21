/* Vidalys Pay — App JavaScript v2 */

// Toast notification with type support
function showToast(message, type = 'default', duration = 3000) {
    const toast = document.getElementById('toast');
    if (!toast) return;

    // Remove previous classes
    toast.className = 'toast';

    // Add type class
    if (type === 'success') toast.classList.add('toast--success');
    else if (type === 'error') toast.classList.add('toast--error');
    else if (type === 'warning') toast.classList.add('toast--warning');

    toast.textContent = message;
    toast.classList.add('show');

    setTimeout(() => toast.classList.remove('show'), duration);
}

// Offline detection
function updateOnlineStatus() {
    const banner = document.getElementById('offlineBanner');
    const status = document.getElementById('connectionStatus');
    if (navigator.onLine) {
        document.body.classList.remove('offline');
        if (banner) banner.style.display = 'none';
        if (status) {
            status.textContent = 'online';
            status.style.color = '';
        }
    } else {
        document.body.classList.add('offline');
        if (banner) banner.style.display = 'block';
        if (status) {
            status.textContent = 'offline';
            status.style.color = 'var(--color-warning)';
        }
    }
}

window.addEventListener('online', updateOnlineStatus);
window.addEventListener('offline', updateOnlineStatus);
document.addEventListener('DOMContentLoaded', updateOnlineStatus);

// CSRF token helper
function getCsrfToken() {
    const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
    return cookie ? cookie.split('=')[1] : '';
}

// Format currency
function formatCurrency(cents) {
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL',
    }).format(cents / 100);
}
