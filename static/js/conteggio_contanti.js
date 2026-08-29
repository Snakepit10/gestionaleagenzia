/**
 * Conteggio Contanti — calcolatore lato client (nessun salvataggio).
 * Tre casse fisse (Cassaforte, Cassa banco, Monete); per ogni cassa l'operatore
 * inserisce il totale diretto oppure il dettaglio dei pezzi per taglio.
 * Il totale generale può essere usato come cassa finale (carry-over via sessionStorage).
 */
(function () {
    'use strict';

    var BANCONOTE = [500, 200, 100, 50, 20, 10, 5];
    var MONETE = [2, 1, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01];

    function fmt(v) {
        return v.toFixed(2).replace('.', ',') + ' €';
    }
    function fmtTaglio(v) {
        // 500 -> "500 €", 0.5 -> "0,50 €"
        return (v >= 1 ? v.toString() : v.toFixed(2)).replace('.', ',') + ' €';
    }

    // Costruisce la griglia dei tagli per una cassa
    function grigliaPezzi(cassaId, tagli) {
        var html = '<div class="row g-1">';
        tagli.forEach(function (t) {
            var key = ('' + t).replace('.', '_');
            html +=
                '<div class="col-6 col-md-4 col-lg-3">' +
                '  <div class="input-group input-group-sm mb-1">' +
                '    <span class="input-group-text taglio-label" style="min-width:64px;justify-content:flex-end;">' + fmtTaglio(t) + '</span>' +
                '    <input type="number" min="0" step="1" inputmode="numeric" class="form-control pezzi-input" ' +
                '           data-cassa="' + cassaId + '" data-taglio="' + t + '" placeholder="0">' +
                '    <span class="input-group-text subtot" data-cassa="' + cassaId + '" data-taglio="' + t + '" style="min-width:78px;">0,00 €</span>' +
                '  </div>' +
                '</div>';
        });
        html += '</div>';
        return html;
    }

    function totaleCassa(cassaId) {
        var root = document.getElementById(cassaId);
        if (!root) return 0;
        var modo = root.querySelector('.modo-cassa:checked');
        modo = modo ? modo.value : 'totale';
        if (modo === 'totale') {
            var inp = root.querySelector('.totale-diretto');
            var v = parseFloat((inp && inp.value || '').replace(',', '.'));
            return isNaN(v) ? 0 : v;
        }
        // modalità pezzi
        var tot = 0;
        root.querySelectorAll('.pezzi-input').forEach(function (inp) {
            var qty = parseInt(inp.value, 10) || 0;
            var taglio = parseFloat(inp.getAttribute('data-taglio')) || 0;
            var sub = Math.round(qty * taglio * 100) / 100;
            var badge = root.querySelector('.subtot[data-taglio="' + inp.getAttribute('data-taglio') + '"]');
            if (badge) badge.textContent = fmt(sub);
            tot += sub;
        });
        return Math.round(tot * 100) / 100;
    }

    function ricalcola() {
        var totale = 0;
        ['cassaforte', 'cassa_banco', 'monete'].forEach(function (cid) {
            var t = totaleCassa(cid);
            var out = document.querySelector('.totale-cassa[data-cassa="' + cid + '"]');
            if (out) out.textContent = fmt(t);
            totale += t;
        });
        totale = Math.round(totale * 100) / 100;
        var g = document.getElementById('cc_totale_generale');
        if (g) g.textContent = fmt(totale);
        return totale;
    }

    function aggiornaVisibilita(cid) {
        var root = document.getElementById(cid);
        if (!root) return;
        var modo = root.querySelector('.modo-cassa:checked');
        modo = modo ? modo.value : 'totale';
        var boxTot = root.querySelector('.box-totale');
        var boxPezzi = root.querySelector('.box-pezzi');
        if (boxTot) boxTot.classList.toggle('d-none', modo !== 'totale');
        if (boxPezzi) boxPezzi.classList.toggle('d-none', modo !== 'pezzi');
    }

    function init() {
        var container = document.getElementById('conteggio-contanti');
        if (!container) return;

        // Inietta le griglie pezzi (banconote + monete) in ogni cassa
        ['cassaforte', 'cassa_banco', 'monete'].forEach(function (cid) {
            var host = document.querySelector('#' + cid + ' .box-pezzi');
            if (host) {
                host.innerHTML =
                    '<div class="small text-muted mt-1 mb-1">Banconote</div>' +
                    grigliaPezzi(cid, BANCONOTE) +
                    '<div class="small text-muted mt-2 mb-1">Monete</div>' +
                    grigliaPezzi(cid, MONETE);
            }
            aggiornaVisibilita(cid);
        });

        // Eventi: input pezzi/totale e cambio modalità
        container.addEventListener('input', ricalcola);
        container.addEventListener('change', function (e) {
            if (e.target && e.target.classList.contains('modo-cassa')) {
                aggiornaVisibilita(e.target.getAttribute('data-cassa'));
            }
            ricalcola();
        });

        // "Usa come cassa finale": carry-over verso la pagina di chiusura
        var btn = document.getElementById('cc_usa_cassa_finale');
        if (btn) {
            btn.addEventListener('click', function () {
                var totale = ricalcola();
                try { sessionStorage.setItem('valoreCassaCalcolato', totale.toFixed(2)); } catch (e) {}
                var ok = document.getElementById('cc_copia_successo');
                if (ok) ok.classList.remove('d-none');
                var url = btn.getAttribute('data-chiudi-url');
                if (url) { setTimeout(function () { window.location.href = url; }, 1000); }
            });
        }

        ricalcola();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
