/**
 * Conteggio Contanti — somma delle casse (Cassaforte, Cassa banco)
 * + calcolatrice (click e tastierino) con riga espressione: mostra le operazioni
 * (es. "30 + 20 + 50") e aggiorna il totale finché non si preme Invio/=.
 * Nessun salvataggio.
 */
(function () {
    'use strict';

    function fmt(v) { return v.toFixed(2).replace('.', ',') + ' €'; }

    // ---------- Somma casse ----------
    function ricalcola() {
        var tot = 0;
        document.querySelectorAll('.cassa-input').forEach(function (inp) {
            var v = parseFloat((inp.value || '').replace(',', '.'));
            if (!isNaN(v)) tot += v;
        });
        tot = Math.round(tot * 100) / 100;
        var g = document.getElementById('cc_totale_generale');
        if (g) g.textContent = fmt(tot);
        return tot;
    }

    // ---------- Calcolatrice ----------
    var parts = [];       // token: numeri (stringa) e operatori (+ - * /)
    var justEq = false;   // true subito dopo "="

    function clean(r) { return isFinite(r) ? Math.round(r * 1e10) / 1e10 : 0; }
    function compute(a, b, op) {
        switch (op) {
            case '+': return a + b;
            case '-': return a - b;
            case '*': return a * b;
            case '/': return b === 0 ? NaN : a / b;
        }
        return b;
    }
    function lastIsOp() {
        return parts.length > 0 && '+-*/'.indexOf(parts[parts.length - 1]) >= 0;
    }
    function evalParts() {
        if (parts.length === 0) return 0;
        var acc = parseFloat(parts[0]); if (isNaN(acc)) acc = 0;
        for (var i = 1; i + 1 < parts.length; i += 2) {
            var n = parseFloat(parts[i + 1]); if (isNaN(n)) break;
            acc = compute(acc, n, parts[i]);
        }
        return clean(acc);
    }
    function opSimbolo(op) { return op === '*' ? '×' : op === '/' ? '÷' : op === '-' ? '−' : op; }
    function show() {
        var disp = document.getElementById('calc_display');
        var expr = document.getElementById('calc_expr');
        if (expr) {
            expr.textContent = parts.map(function (t) {
                return '+-*/'.indexOf(t) >= 0 ? opSimbolo(t) : t.replace('.', ',');
            }).join(' ');
        }
        if (disp) { disp.value = String(evalParts()).replace('.', ','); }
    }

    function digit(d) {
        if (justEq) { parts = []; justEq = false; }
        if (parts.length === 0 || lastIsOp()) {
            parts.push(d === '.' ? '0.' : d);
        } else {
            var cur = parts[parts.length - 1];
            if (d === '.') { if (cur.indexOf('.') < 0) parts[parts.length - 1] = cur + '.'; }
            else parts[parts.length - 1] = (cur === '0' ? d : cur + d);
        }
        show();
    }
    function operatore(op) {
        justEq = false;
        if (parts.length === 0) parts.push('0');
        if (lastIsOp()) parts[parts.length - 1] = op;
        else parts.push(op);
        show();
    }
    function uguale() {
        if (parts.length < 3 || lastIsOp()) return;
        var r = evalParts();
        parts = [String(r)];
        justEq = true;
        show();
    }
    function clearAll() { parts = []; justEq = false; show(); }
    function clearEntry() {
        if (parts.length && !lastIsOp()) parts[parts.length - 1] = '0';
        show();
    }
    function backspace() {
        if (parts.length === 0 || lastIsOp()) return;
        var cur = parts[parts.length - 1];
        parts[parts.length - 1] = cur.length > 1 ? cur.slice(0, -1) : '0';
        if (parts[parts.length - 1] === '-') parts[parts.length - 1] = '0';
        show();
    }
    function negate() {
        if (parts.length && !lastIsOp()) {
            var cur = parts[parts.length - 1];
            parts[parts.length - 1] = cur.charAt(0) === '-' ? cur.slice(1) : '-' + cur;
            show();
        }
    }

    function onKey(e) {
        var ae = document.activeElement;
        if (ae && /^(INPUT|TEXTAREA|SELECT)$/.test(ae.tagName) && ae.id !== 'calc_display') return;
        var k = e.key;
        if (k >= '0' && k <= '9') { digit(k); e.preventDefault(); }
        else if (k === '.' || k === ',') { digit('.'); e.preventDefault(); }
        else if (k === '+' || k === '-' || k === '*' || k === '/') { operatore(k); e.preventDefault(); }
        else if (k === 'Enter' || k === '=') { uguale(); e.preventDefault(); }
        else if (k === 'Backspace') { backspace(); e.preventDefault(); }
        else if (k === 'Escape') { clearAll(); e.preventDefault(); }
        else if (k === 'Delete') { clearEntry(); e.preventDefault(); }
    }

    function initCalc() {
        var grid = document.getElementById('calc_grid');
        if (!grid) return;
        grid.addEventListener('click', function (e) {
            var b = e.target.closest('button');
            if (!b) return;
            if (b.dataset.val !== undefined) digit(b.dataset.val);
            else if (b.dataset.op !== undefined) operatore(b.dataset.op);
            else switch (b.dataset.act) {
                case 'clear': clearAll(); break;
                case 'ce': clearEntry(); break;
                case 'back': backspace(); break;
                case 'equals': uguale(); break;
                case 'neg': negate(); break;
            }
        });
        document.addEventListener('keydown', onKey);
        show();
    }

    function init() {
        var container = document.getElementById('conteggio-contanti');
        if (!container) return;

        container.addEventListener('input', ricalcola);
        container.addEventListener('change', ricalcola);

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

        initCalc();
        ricalcola();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
