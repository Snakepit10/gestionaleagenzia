/**
 * Conteggio Contanti — somma delle 3 casse (Cassaforte, Cassa banco, Monete)
 * + calcolatrice (click e tastierino, stile Windows). Nessun salvataggio.
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
    var st = { display: '0', acc: null, op: null, waiting: false };

    function show() {
        var d = document.getElementById('calc_display');
        if (d) d.value = st.display;
    }
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
    function inputDigit(d) {
        if (st.waiting) { st.display = (d === '.' ? '0.' : d); st.waiting = false; }
        else if (d === '.') { if (st.display.indexOf('.') < 0) st.display += '.'; }
        else { st.display = (st.display === '0') ? d : st.display + d; }
        show();
    }
    function chooseOp(op) {
        var v = parseFloat(st.display);
        if (st.op !== null && !st.waiting) {
            var r = clean(compute(st.acc, v, st.op));
            st.acc = r; st.display = String(r);
        } else {
            st.acc = v;
        }
        st.op = op; st.waiting = true; show();
    }
    function equals() {
        if (st.op === null) return;
        var v = parseFloat(st.display);
        var r = clean(compute(st.acc, v, st.op));
        st.display = String(r); st.acc = r; st.op = null; st.waiting = true; show();
    }
    function clearAll() { st = { display: '0', acc: null, op: null, waiting: false }; show(); }
    function clearEntry() { st.display = '0'; show(); }
    function backspace() {
        if (st.waiting) return;
        st.display = st.display.length > 1 ? st.display.slice(0, -1) : '0';
        if (st.display === '-' || st.display === '') st.display = '0';
        show();
    }
    function negate() {
        if (st.display !== '0') {
            st.display = st.display.charAt(0) === '-' ? st.display.slice(1) : '-' + st.display;
            show();
        }
    }

    function onKey(e) {
        // Non catturare la tastiera mentre si digita in un campo (casse, form, ecc.)
        var ae = document.activeElement;
        if (ae && /^(INPUT|TEXTAREA|SELECT)$/.test(ae.tagName) && ae.id !== 'calc_display') return;
        var k = e.key;
        if (k >= '0' && k <= '9') { inputDigit(k); e.preventDefault(); }
        else if (k === '.' || k === ',') { inputDigit('.'); e.preventDefault(); }
        else if (k === '+' || k === '-' || k === '*' || k === '/') { chooseOp(k); e.preventDefault(); }
        else if (k === 'Enter' || k === '=') { equals(); e.preventDefault(); }
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
            if (b.dataset.val !== undefined) inputDigit(b.dataset.val);
            else if (b.dataset.op !== undefined) chooseOp(b.dataset.op);
            else switch (b.dataset.act) {
                case 'clear': clearAll(); break;
                case 'ce': clearEntry(); break;
                case 'back': backspace(); break;
                case 'equals': equals(); break;
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
