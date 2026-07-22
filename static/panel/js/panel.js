/* Vidalys Pay — Painel JavaScript */

(function() {
    'use strict';

    var body = document.body;
    var sidebar = document.getElementById('panelSidebar');
    var overlay = document.getElementById('sidebarOverlay');
    var menuToggle = document.getElementById('menuToggle');

    function openSidebar() {
        body.classList.add('sidebar-open');
        menuToggle.setAttribute('aria-expanded', 'true');
        overlay.setAttribute('aria-hidden', 'false');
        sidebar.focus();
    }

    function closeSidebar() {
        body.classList.remove('sidebar-open');
        menuToggle.setAttribute('aria-expanded', 'false');
        overlay.setAttribute('aria-hidden', 'true');
        if (menuToggle) menuToggle.focus();
    }

    if (menuToggle) {
        menuToggle.addEventListener('click', function() {
            if (body.classList.contains('sidebar-open')) {
                closeSidebar();
            } else {
                openSidebar();
            }
        });
    }

    if (overlay) {
        overlay.addEventListener('click', closeSidebar);
    }

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && body.classList.contains('sidebar-open')) {
            closeSidebar();
        }
    });

    // Close sidebar when a link is clicked (mobile)
    if (sidebar) {
        sidebar.addEventListener('click', function(e) {
            var link = e.target.closest('a');
            if (link && window.innerWidth < 1024) {
                setTimeout(closeSidebar, 100);
            }
        });
    }

    // ── Confirmation Modal ──────────────────────────────────────────────────
    window.confirmAction = function(title, text, actionUrl, confirmLabel) {
        var modal = document.getElementById('confirmModal');
        var modalTitle = document.getElementById('modalTitle');
        var modalText = document.getElementById('modalText');
        var modalForm = document.getElementById('modalForm');
        var modalConfirm = document.getElementById('modalConfirm');
        var modalCancel = document.getElementById('modalCancel');
        var backdrop = document.getElementById('modalBackdrop');

        if (!modal) return;

        modalTitle.textContent = title;
        modalText.textContent = text;
        modalForm.action = actionUrl;
        modalConfirm.textContent = confirmLabel || 'Confirmar';
        modal.classList.add('open');
        modal.setAttribute('aria-hidden', 'false');
        modalCancel.focus();

        function closeModal() {
            modal.classList.remove('open');
            modal.setAttribute('aria-hidden', 'true');
            if (document.activeElement && document.activeElement.closest('#confirmModal')) {
                var trigger = document.querySelector('[onclick*="confirmAction"]:focus');
                if (trigger) trigger.focus();
            }
        }

        modalCancel.onclick = closeModal;
        backdrop.onclick = closeModal;

        document.addEventListener('keydown', function handler(e) {
            if (e.key === 'Escape' && modal.classList.contains('open')) {
                closeModal();
                document.removeEventListener('keydown', handler);
            }
        });
    };
})();
