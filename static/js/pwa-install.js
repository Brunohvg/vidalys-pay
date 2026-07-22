/* Vidalys Pay — PWA Install Controller v1 */

(function () {
  var deferredInstallPrompt = null;
  var installButton = null;
  var iosModal = null;

  function isRunningStandalone() {
    return window.matchMedia('(display-mode: standalone)').matches
        || window.navigator.standalone === true;
  }

  function isIOSDevice() {
    var ua = navigator.userAgent || '';
    return /iPhone|iPad|iPod/i.test(ua);
  }

  function updateInstallUI(state) {
    if (!installButton) return;

    switch (state) {
      case 'loading':
        installButton.style.display = 'none';
        break;

      case 'installable':
        installButton.style.display = 'flex';
        installButton.querySelector('.profile-action__text').textContent = 'Instalar aplicativo';
        installButton.disabled = false;
        break;

      case 'already_installed':
        installButton.style.display = 'flex';
        installButton.querySelector('.profile-action__text').textContent = 'Aplicativo instalado';
        installButton.disabled = true;
        installButton.style.opacity = '0.5';
        break;

      case 'unsupported':
        installButton.style.display = 'flex';
        installButton.querySelector('.profile-action__text').textContent = 'Instalar aplicativo';
        installButton.disabled = false;
        break;

      default:
        break;
    }
  }

  function openIOSInstructions() {
    showIOSModal();
  }

  function showIOSModal() {
    if (iosModal) {
      iosModal.style.display = 'flex';
      return;
    }

    iosModal = document.createElement('div');
    iosModal.className = 'pwa-modal-overlay';
    iosModal.setAttribute('role', 'dialog');
    iosModal.setAttribute('aria-modal', 'true');
    iosModal.setAttribute('aria-labelledby', 'pwa-modal-title');
    iosModal.innerHTML =
      '<div class="pwa-modal">' +
      '  <h2 id="pwa-modal-title" class="pwa-modal__title">Instalar no iPhone</h2>' +
      '  <ol class="pwa-modal__steps">' +
      '    <li>Abra esta página no <strong>Safari</strong>.</li>' +
      '    <li>Toque em <strong>Compartilhar</strong> <span style="font-size:18px">&#x1F4E4;</span> na barra inferior.</li>' +
      '    <li>Escolha <strong>&#x201C;Adicionar &#x00E0; Tela de In&#x00ED;cio&#x201D;</strong>.</li>' +
      '    <li>Toque em <strong>&#x201C;Adicionar&#x201D;</strong>.</li>' +
      '  </ol>' +
      '  <button type="button" class="btn-secondary pwa-modal__close" aria-label="Fechar">Fechar</button>' +
      '</div>';

    iosModal.addEventListener('click', function (e) {
      if (e.target === iosModal) hideIOSModal();
    });

    iosModal.querySelector('.pwa-modal__close').addEventListener('click', hideIOSModal);

    document.addEventListener('keydown', function onEsc(e) {
      if (e.key === 'Escape') {
        hideIOSModal();
        document.removeEventListener('keydown', onEsc);
      }
    });

    document.body.appendChild(iosModal);

    requestAnimationFrame(function () {
      iosModal.style.display = 'flex';
    });
  }

  function hideIOSModal() {
    if (iosModal) {
      iosModal.style.display = 'none';
      if (installButton) installButton.focus();
    }
  }

  function requestInstall() {
    if (isRunningStandalone()) {
      updateInstallUI('already_installed');
      return;
    }

    if (isIOSDevice()) {
      openIOSInstructions();
      return;
    }

    if (!deferredInstallPrompt) {
      openIOSInstructions();
      return;
    }

    deferredInstallPrompt.prompt();

    deferredInstallPrompt.userChoice.then(function (result) {
      if (result.outcome === 'accepted') {
        updateInstallUI('already_installed');
      }
      deferredInstallPrompt = null;
    });
  }

  function init() {
    if (isRunningStandalone()) {
      return;
    }

    installButton = document.getElementById('pwa-install-button');
    if (!installButton) return;

    updateInstallUI('loading');

    installButton.addEventListener('click', function (e) {
      e.preventDefault();
      requestInstall();
    });
  }

  window.addEventListener('beforeinstallprompt', function (event) {
    event.preventDefault();
    deferredInstallPrompt = event;
    updateInstallUI('installable');
  });

  window.addEventListener('appinstalled', function () {
    deferredInstallPrompt = null;
    updateInstallUI('already_installed');
  });

  window.matchMedia('(display-mode: standalone)').addEventListener('change', function (e) {
    if (e.matches) {
      updateInstallUI('already_installed');
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
