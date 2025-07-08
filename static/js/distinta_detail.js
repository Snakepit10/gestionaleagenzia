/**
 * distinta_detail.js - Gestisce tutte le funzionalità della pagina dettaglio distinta
 * Versione: 1.0
 * 
 * Questo script gestisce:
 * 1. Pulsanti importo rapido
 * 2. Stili dei badge per i tipi di movimento
 * 3. Caricamento movimenti cliente
 * 4. Funzionalità saldo movimenti
 */

(function(window, document, $) {
    'use strict';
    
    // Configurazione colori
    const COLORS = {
        schedina: { bg: '#7b0828', text: 'white' },
        ricarica: { bg: '#ffc107', text: 'black' },
        prelievo: { bg: '#6f42c1', text: 'white' },
        incasso_credito: { bg: '#198754', text: 'white' },
        pagamento_debito: { bg: '#fd7e14', text: 'white' },
        success: '#198754',
        danger: '#dc3545'
    };
    
    // =========================================================
    // SEZIONE 1: FUNZIONI HELPER E UTILITY
    // =========================================================
    
    /**
     * Imposta il valore del campo importo
     * @param {number} value - Valore da impostare
     */
    function setImportoValue(value) {
        // Cerca il campo importo con diverse strategie
        const input = document.getElementById('id_importo') || 
                      document.querySelector('input[name="importo"]') ||
                      document.querySelector('form input[type="number"]');
        
        if (input) {
            input.value = value;
            $(input).trigger('change');
            return true;
        }
        
        return false;
    }
    
    /**
     * Formatta un numero con segno e 2 decimali
     * @param {number} value - Valore da formattare 
     * @param {boolean} showPositiveSign - Se mostrare il segno + per valori positivi
     * @returns {string} - Valore formattato
     */
    function formatCurrency(value, showPositiveSign = false) {
        const absValue = Math.abs(parseFloat(value)).toFixed(2);
        if (value < 0) {
            return '-' + absValue + ' €';
        } else {
            return (showPositiveSign ? '+' : '') + absValue + ' €';
        }
    }
    
    // =========================================================
    // SEZIONE 2: GESTIONE STILI
    // =========================================================

    /**
     * Assicura che tutti i badge abbiano la classe corretta basata sul tipo
     */
    function fixBadgeClasses() {
        // Assicura che tutti i badge abbiano la classe corretta basata sul tipo
        $('span.badge').each(function() {
            const $badge = $(this);
            const testo = $badge.text().trim().toLowerCase();

            // Solo se il badge non ha già una classe tipo-specifica
            if (!$badge.hasClass('badge-schedina') &&
                !$badge.hasClass('badge-ricarica') &&
                !$badge.hasClass('badge-prelievo') &&
                !$badge.hasClass('badge-incasso-credito') &&
                !$badge.hasClass('badge-pagamento-debito') &&
                !$badge.hasClass('bg-schedina') &&
                !$badge.hasClass('bg-ricarica') &&
                !$badge.hasClass('bg-prelievo') &&
                !$badge.hasClass('bg-incasso_credito') &&
                !$badge.hasClass('bg-pagamento_debito')) {

                // Aggiungi le classi corrette in base al testo contenuto
                if (testo.includes('schedina')) {
                    $badge.addClass('badge-schedina');
                } else if (testo.includes('ricarica')) {
                    $badge.addClass('badge-ricarica');
                } else if (testo.includes('prelievo')) {
                    $badge.addClass('badge-prelievo');
                } else if (testo.includes('incasso credito')) {
                    $badge.addClass('badge-incasso-credito');
                } else if (testo.includes('pagamento debito')) {
                    $badge.addClass('badge-pagamento-debito');
                }
            }
        });
    }

    /**
     * Aggiunge attributi data-tipo ai badge
     */
    function addBadgeDataAttributes() {
        $('.badge-schedina').attr('data-tipo', 'schedina');
        $('.badge-ricarica').attr('data-tipo', 'ricarica');
        $('.badge-prelievo').attr('data-tipo', 'prelievo');
        $('.badge-incasso-credito').attr('data-tipo', 'incasso_credito');
        $('.badge-pagamento-debito').attr('data-tipo', 'pagamento_debito');
    }

    /**
     * Verifica e ripristina gli stili se necessario
     */
    function checkStyles() {
        fixBadgeClasses();
        addBadgeDataAttributes();
    }
    
    // =========================================================
    // SEZIONE 3: GESTIONE MOVIMENTI CLIENTE
    // =========================================================
    
    /**
     * Carica i movimenti non saldati di un cliente
     * @param {number} clienteId - ID del cliente
     */
    function loadClienteMovimenti(clienteId) {
        if (!clienteId) return;
        
        const container = $('.card-body-movimenti-da-saldare');
        
        // Mostra indicatore di caricamento
        container.html(`
            <div class="text-center py-5">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Caricamento...</span>
                </div>
                <p class="mt-2">Caricamento movimenti in corso...</p>
            </div>
        `);
        
        // Carica i dati tramite AJAX
        $.ajax({
            url: "/api/movimenti-cliente/",
            data: { 'cliente_id': clienteId },
            dataType: 'json',
            success: function(data) {
                renderClienteMovimenti(data);
                checkStyles();
            },
            error: function() {
                container.html(`
                    <div class="text-center py-4">
                        <i class="fas fa-exclamation-circle text-danger fa-3x mb-3"></i>
                        <p class="mb-0">Errore nel caricamento dei dati del cliente</p>
                    </div>
                `);
            }
        });
    }
    
    /**
     * Renderizza i dati del cliente e i suoi movimenti non saldati
     * @param {Object} data - Dati cliente e movimenti
     */
    function renderClienteMovimenti(data) {
        const container = $('.card-body-movimenti-da-saldare');
        
        // Se non ci sono dati o cliente
        if (!data || !data.cliente) {
            container.html(`
                <div class="text-center py-4">
                    <i class="fas fa-user-circle text-muted fa-3x mb-3"></i>
                    <p class="mb-0">Seleziona un cliente per vedere i movimenti da saldare</p>
                </div>
            `);
            return;
        }
        
        // Intestazione con dati cliente
        const headerHtml = `
            <div class="p-3 bg-light border-bottom">
                <div class="row align-items-center">
                    <div class="col">
                        <h5 class="mb-1">${data.cliente.nome_completo}</h5>
                        <div class="d-flex">
                            <span class="me-3">Saldo: <strong class="${parseFloat(data.cliente.saldo) < 0 ? 'text-danger' : 'text-success'}">${data.cliente.saldo} €</strong></span>
                            <span>Fido: <strong>${data.cliente.fido_massimo} €</strong></span>
                        </div>
                    </div>
                    ${data.movimenti && data.movimenti.length > 0 ? `
                        <div class="col-auto">
                            <button type="button" class="btn btn-success btn-sm btn-salda-tutti" id="salda-tutti-movimenti" data-cliente="${data.cliente.id}">
                                <i class="fas fa-check-double me-1"></i> Salda Tutti
                            </button>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
        
        // Se ci sono movimenti da mostrare
        if (data.movimenti && data.movimenti.length > 0) {
            let tableHtml = `
                <div style="max-height: 300px; overflow-y: auto;">
                    <table class="table table-sm table-hover mb-0">
                        <thead>
                            <tr>
                                <th>Tipo</th>
                                <th>Importo</th>
                                <th>Data</th>
                                <th>Azioni</th>
                            </tr>
                        </thead>
                        <tbody>
            `;
            
            // Aggiungi riga per ogni movimento
            data.movimenti.forEach(function(movimento) {
                const importoClass = parseFloat(movimento.importo) < 0 ? 'text-danger' : 'text-success';
                
                // Determina tipo e stile badge
                const tipo = movimento.tipo || '';
                const tipoDisplay = movimento.tipo_display || tipo.charAt(0).toUpperCase() + tipo.slice(1).replace(/_/g, ' ');
                
                // Determina classe badge
                let badgeClass = 'badge-secondary';
                if (COLORS[tipo]) {
                    badgeClass = `badge-${tipo}`;
                }
                
                // Formatta importo 
                const importoValore = formatCurrency(movimento.importo, true);
                
                tableHtml += `
                    <tr class="movimento-row" data-id="${movimento.id}">
                        <td><span class="badge ${badgeClass}" data-tipo="${tipo}">${tipoDisplay}</span></td>
                        <td class="${importoClass} fw-bold">${importoValore}</td>
                        <td>${movimento.data}</td>
                        <td>
                            <a href="javascript:void(0)" class="btn btn-sm btn-success btn-salda-movimento me-1" data-id="${movimento.id}">
                                <i class="fas fa-check"></i> Salda
                            </a>
                            <a href="/movimenti/${movimento.id}/modifica/" class="btn btn-sm btn-info" title="Dettagli">
                                <i class="fas fa-info-circle"></i>
                            </a>
                        </td>
                    </tr>
                `;
            });
            
            tableHtml += '</tbody></table></div>';
            container.html(headerHtml + tableHtml);
            
            // Attiva i listener
            activateSaldaListeners();
        } else {
            container.html(headerHtml + `
                <div class="card-body text-center py-4">
                    <i class="fas fa-check-circle text-success fa-3x mb-3"></i>
                    <p class="mb-0">Nessun movimento da saldare per questo cliente</p>
                </div>
            `);
        }
    }
    
    // =========================================================
    // SEZIONE 4: GESTIONE SALDO MOVIMENTI
    // =========================================================
    
    /**
     * Attiva i listener per i pulsanti salda
     */
    function activateSaldaListeners() {
        // Rimuovi prima eventuali listener precedenti
        $(document).off('click', '.btn-salda-movimento');
        $(document).off('click', '.btn-salda-tutti');
        
        // Bottoni "Salda movimento" - usa delegate per funzionare anche con elementi dinamici
        $(document).on('click', '.btn-salda-movimento', function(e) {
            e.preventDefault();
            const movimentoId = $(this).data('id');
            saldaMovimento(movimentoId);
        });
        
        // Bottone "Salda tutti"
        $(document).on('click', '.btn-salda-tutti', function(e) {
            e.preventDefault();
            const clienteId = $(this).data('cliente');
            saldaTuttiMovimenti(clienteId);
        });
    }
    
    /**
     * Salda un singolo movimento
     * @param {number} movimentoId - ID del movimento da saldare
     */
    function saldaMovimento(movimentoId) {
        $.ajax({
            url: '/movimenti/' + movimentoId + '/salda/',
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            success: function(data) {
                // Mostra messaggio di successo
                showAlert('success', data.message || 'Movimento saldato con successo');
                
                // Rimuovi il movimento dalla sezione "Movimenti da saldare"
                $('.card-body-movimenti-da-saldare .btn-salda-movimento[data-id="' + movimentoId + '"]')
                    .closest('tr')
                    .fadeOut(400, function() {
                        $(this).remove();
                    });
                
                // Aggiorna il saldo del cliente se presente nei dati
                if (data.cliente && data.cliente.saldo !== undefined) {
                    updateClienteSaldo(data.cliente);
                }
                
                // Aggiorna lo stato del movimento nella tabella principale e nei tab
                // senza nascondere la riga
                updateMovimentoStatoInTables(movimentoId);
                
                // Ricarica i dati del cliente
                const clienteId = $('#id_cliente').val();
                if (clienteId) {
                    setTimeout(function() {
                        loadClienteMovimenti(clienteId);
                    }, 500);
                }
            },
            error: function() {
                showAlert('danger', 'Errore durante il saldo del movimento');
            }
        });
    }
    
    /**
     * Salda tutti i movimenti di un cliente
     * @param {number} clienteId - ID del cliente
     */
    function saldaTuttiMovimenti(clienteId) {
        // Ottieni gli ID di tutti i movimenti da saldare
        const movimentiIds = [];
        
        // Seleziona solo i movimenti nella sezione "Movimenti da saldare"
        $('.card-body-movimenti-da-saldare .btn-salda-movimento').each(function() {
            movimentiIds.push($(this).data('id'));
        });
        
        if (movimentiIds.length === 0) {
            showAlert('warning', 'Non ci sono movimenti da saldare per questo cliente');
            return;
        }
        
        // Disabilita il pulsante per evitare doppi click
        $('.btn-salda-tutti')
            .prop('disabled', true)
            .html('<i class="fas fa-spinner fa-spin"></i> Saldamento in corso...');
        
        // Avvia il processo di saldo sequenziale
        saldaMovimentiInSequenza(movimentiIds, 0);
    }
    
    /**
     * Salda i movimenti in sequenza uno dopo l'altro
     * @param {Array} movimentiIds - Array di ID movimenti
     * @param {number} index - Indice corrente
     */
    function saldaMovimentiInSequenza(movimentiIds, index) {
        // Se abbiamo finito, riabilita il pulsante
        if (index >= movimentiIds.length) {
            $('.btn-salda-tutti')
                .prop('disabled', false)
                .html('<i class="fas fa-check-double me-1"></i> Salda Tutti');
            
            // Ricarica i dati del cliente
            const clienteId = $('#id_cliente').val();
            if (clienteId) {
                setTimeout(function() {
                    loadClienteMovimenti(clienteId);
                }, 500);
            }
            
            return;
        }
        
        // Ottieni l'ID del movimento corrente
        const movimentoId = movimentiIds[index];
        
        // Salda il movimento
        $.ajax({
            url: '/movimenti/' + movimentoId + '/salda/',
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            success: function(data) {
                // Aggiorna il saldo mostrato nell'intestazione se disponibile
                if (data && data.cliente && data.cliente.saldo !== undefined) {
                    updateClienteSaldo(data.cliente);
                }
                
                // Aggiorna lo stato del movimento nelle tabelle
                updateMovimentoStatoInTables(movimentoId);
                
                // Procedi con il prossimo movimento
                setTimeout(function() {
                    saldaMovimentiInSequenza(movimentiIds, index + 1);
                }, 300);
            },
            error: function() {
                console.error('Errore nel saldare il movimento ' + movimentoId);
                
                // Continua con il prossimo movimento anche in caso di errore
                setTimeout(function() {
                    saldaMovimentiInSequenza(movimentiIds, index + 1);
                }, 300);
            }
        });
    }
    
    /**
     * Aggiorna lo stato del movimento nelle tabelle principali
     * @param {number} movimentoId - ID del movimento
     */
    function updateMovimentoStatoInTables(movimentoId) {
        // Aggiorna nella tabella principale dei movimenti
        $(`#lista-movimenti table tr, .tab-content table tr`).each(function() {
            // Prova prima a cercare nella prima colonna (tabella principale)
            if ($(this).find('td:first').text().trim() === movimentoId.toString()) {
                updateRowToSaldato($(this));
            }
            // Poi cerca tramite il pulsante salda (tabs Entrate/Uscite)
            else if ($(this).find(`.btn-salda-movimento[data-id="${movimentoId}"]`).length > 0) {
                updateRowToSaldato($(this));
            }
        });
    }
    
    /**
     * Aggiorna una riga della tabella allo stato "Saldato"
     * @param {jQuery} $row - Riga della tabella da aggiornare
     */
    function updateRowToSaldato($row) {
        // Aggiorna la colonna stato a "Saldato"
        $row.find('td:nth-child(6)').html('<span class="badge bg-success">Saldato</span>');
        // Nascondi solo il pulsante "Salda"
        $row.find('.btn-salda-movimento').hide();
    }
    
    /**
     * Aggiorna il saldo del cliente visualizzato nell'intestazione
     * @param {Object} cliente - Dati del cliente
     */
    function updateClienteSaldo(cliente) {
        const saldoClass = parseFloat(cliente.saldo) < 0 ? 'text-danger' : 'text-success';
        $('.p-3.bg-light.border-bottom .me-3 strong')
            .attr('class', saldoClass)
            .text(cliente.saldo + ' €');
    }
    
    /**
     * Mostra un messaggio di alert con auto-chiusura
     * @param {string} type - Tipo di alert (success, danger, warning)
     * @param {string} message - Messaggio da mostrare
     */
    function showAlert(type, message) {
        const alertHtml = `
            <div class="alert alert-${type} alert-dismissible fade show" role="alert">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        `;
        
        $('.container > .row:first').after(alertHtml);
        
        // Auto-chiudi l'alert dopo 5 secondi
        setTimeout(function() {
            $('.alert').alert('close');
        }, 5000);
    }
    
    // =========================================================
    // SEZIONE 5: INIZIALIZZAZIONE E CONFIGURAZIONE EVENTI
    // =========================================================
    
    /**
     * Inizializza tutti gli event handler per i pulsanti importo
     */
    function initImportoButtons() {
        $('.importo-btn').each(function() {
            const $btn = $(this);
            
            // Rimuovi handler esistenti e aggiungi il nuovo
            $btn.off('click').on('click', function() {
                const valore = parseInt($(this).data('value'), 10);
                
                // Rimuovi classe active da tutti i bottoni
                $('.importo-btn').removeClass('active');
                
                // Aggiungi classe active a questo bottone
                $(this).addClass('active');
                
                // Aggiorna stili
                applyImportoButtonStyles();
                
                // Aggiungi animazione pulsato
                $(this).addClass('pulsato');
                setTimeout(() => $(this).removeClass('pulsato'), 300);
                
                // Imposta il valore
                setImportoValue(valore);
            });
        });
    }
    
    /**
     * Inizializza il gestore per il cambio cliente
     */
    function initClienteSelect() {
        $('#id_cliente').on('change', function() {
            const clienteId = $(this).val();
            if (clienteId) {
                // Aggiorna URL senza ricaricare
                const newUrl = window.location.pathname + "?cliente=" + clienteId;
                history.pushState({}, '', newUrl);
                
                // Carica i movimenti del cliente
                loadClienteMovimenti(clienteId);
            }
        });
    }
    
    /**
     * Inizializza tutte le funzionalità
     */
    function initialize() {
        // Attiva i listener per i pulsanti salda
        activateSaldaListeners();

        // Inizializza i pulsanti importo rapido
        initImportoButtons();

        // Inizializza il select cliente
        initClienteSelect();

        // Verifica e correggi classi e attributi dei badge
        checkStyles();

        // Esponi funzione setImportoValue per compatibilità
        window.setImportoValue = setImportoValue;

        // Disabilita il comportamento AJAX sul form di nuovo movimento
        // per fare un reload completo della pagina dopo l'aggiunta
        $('form[action*="nuovo_movimento"]').off('submit');

        // Carica cliente da URL se presente
        const urlParams = new URLSearchParams(window.location.search);
        const clienteParam = urlParams.get('cliente');
        if (clienteParam) {
            $('#id_cliente').val(clienteParam);
            loadClienteMovimenti(clienteParam);
        }

        // Applica immediatamente gli stili corretti alla sezione "Movimenti da Saldare"
        $('.card-body-movimenti-da-saldare').css({
            'padding': '0',
            'z-index': '10',
            'position': 'relative'
        });

        // Assicurati che il contenitore dei movimenti da saldare abbia il corretto overflow
        $('.card-body-movimenti-da-saldare div[style*="max-height"]').css({
            'max-height': '300px',
            'overflow-y': 'auto'
        });

        // Aggiungi handler per DOM modificato con debounce per evitare troppe chiamate
        let debounceTimer;
        $(document).on('DOMSubtreeModified', function() {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(checkStyles, 100);
        });
    }

    // Esegui l'inizializzazione quando il documento è pronto
    $(document).ready(function() {
        // Importante: Assicura che i CSS siano completamente caricati
        if (document.readyState === 'complete') {
            initializeAndFixStyles();
        } else {
            // Se il documento non è ancora completamente caricato, attendi
            $(window).on('load', initializeAndFixStyles);
        }
    });

    /**
     * Inizializza il componente e applica gli stili corretti
     */
    function initializeAndFixStyles() {
        // Risolve i potenziali conflitti CSS applicando i nostri stili con priorità
        $('head').append('<style id="distinta-detail-priority-styles">' +
            '.card-body-movimenti-da-saldare { padding: 0 !important; z-index: 10 !important; position: relative !important; }' +
            '.card-body-movimenti-da-saldare .table { margin-bottom: 0 !important; }' +
            '.card-body-movimenti-da-saldare div[style*="max-height"] { max-height: 300px !important; overflow-y: auto !important; }' +
            '.importo-btn { min-width: 60px !important; flex: 1 0 22% !important; }' +
            '.card.border-warning.h-100 .card-header.bg-warning.text-white { background-color: #ffc107 !important; color: #212529 !important; }' +
        '</style>');

        // Inizializza l'applicazione
        initialize();

        // Controlla gli stili subito e dopo un secondo per sicurezza
        checkStyles();
        setTimeout(checkStyles, 1000);

        // Forzare un refresh CSSOM per applicare immediatamente tutti gli stili
        document.body.offsetHeight;
    }
    
})(window, document, jQuery);