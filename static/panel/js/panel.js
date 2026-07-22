/* Vidalys Pay — Painel JS */
(function(){
    var body=document.body;
    var sidebar=document.getElementById('sidebar');
    var overlay=document.getElementById('overlay');
    var menuBtn=document.getElementById('menuBtn');

    function open(){sidebar.classList.add('open');overlay.classList.add('open');menuBtn.setAttribute('aria-expanded','true')}
    function close(){sidebar.classList.remove('open');overlay.classList.remove('open');menuBtn.setAttribute('aria-expanded','false')}

    if(menuBtn)menuBtn.addEventListener('click',function(){sidebar.classList.contains('open')?close():open()});
    if(overlay)overlay.addEventListener('click',close);
    document.addEventListener('keydown',function(e){if(e.key==='Escape'&&sidebar.classList.contains('open'))close()});
    if(sidebar)sidebar.addEventListener('click',function(e){if(e.target.closest('a')&&window.innerWidth<1024)setTimeout(close,100)});

    /* Confirmation modal */
    window.confirmAction=function(title,text,actionUrl,confirmLabel){
        var m=document.getElementById('confirmModal');
        if(!m)return;
        document.getElementById('modalTitle').textContent=title;
        document.getElementById('modalText').textContent=text;
        document.getElementById('modalForm').action=actionUrl;
        document.getElementById('modalConfirmBtn').textContent=confirmLabel||'Confirmar';
        m.classList.add('open');m.setAttribute('aria-hidden','false');
        document.getElementById('modalCancel').focus();
        function closeM(){m.classList.remove('open');m.setAttribute('aria-hidden','true')}
        document.getElementById('modalCancel').onclick=closeM;
        document.getElementById('modalBackdrop').onclick=closeM;
        document.addEventListener('keydown',function h(e){if(e.key==='Escape'&&m.classList.contains('open')){closeM();document.removeEventListener('keydown',h)}});
    };
})();
