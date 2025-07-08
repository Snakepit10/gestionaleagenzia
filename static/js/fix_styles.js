/**
 * fix_styles.js - Script per risolvere problemi di stile e funzionalità
 * Questo script deve essere caricato per ULTIMO in modo da avere la precedenza su tutti gli altri script
 * Versione ottimizzata per evitare problemi di performance
 */

(function(window, document, $) {
    'use strict';
    
    // Flag per tenere traccia se gli stili sono già stati applicati
    var stylesApplied = false;
    var isProcessing = false;
    var initialized = false;
    
    // Funzione principale che verrà eseguita all'avvio
    function fixAllStyles() {
        // Se stiamo già elaborando, usciamo per evitare chiamate ricorsive
        if (isProcessing) return;

        isProcessing = true;

        // 1. FIX IMPORTO RAPIDO BUTTONS - Solo al primo caricamento
        if (!initialized) {
            $('.importo-btn').each(function() {
                var $btn = $(this);

                // Rimuove tutti i gestori di eventi esistenti solo la prima volta
                $btn.off('click');

                // Aggiunge l'handler di eventi che funziona sempre
                $btn.on('click', function() {
                    var valore = parseInt($(this).data('value'), 10);

                    // Rimuovi l'evidenziazione da tutti i bottoni
                    $('.importo-btn').removeClass('active').css({
                        'background-color': '#212529',
                        'border-color': '#212529',
                        'font-weight': 'normal'
                    });

                    // Evidenzia questo bottone
                    $(this).addClass('active').css({
                        'background-color': '#198754',
                        'border-color': '#198754',
                        'font-weight': 'bold'
                    });

                    // Imposta il valore nell'input
                    setImportoValueRobust(valore);
                });
            });
        }

        // Applica gli stili ai bottoni di importo
        $('.importo-btn').each(function() {
            var $btn = $(this);
            $btn.css({
                'background-color': $btn.hasClass('active') ? '#198754' : '#212529',
                'border-color': $btn.hasClass('active') ? '#198754' : '#212529',
                'color': 'white',
                'min-width': '60px'
            });
        });

        // 2. FIX BADGE STYLES per entrambe le sezioni
        // Prima applica stili di base a TUTTI i badge
        $('.badge').css({
            'display': 'inline-block',
            'padding': '0.25em 0.4em',
            'font-size': '75%',
            'font-weight': '700',
            'line-height': '1',
            'text-align': 'center',
            'white-space': 'nowrap',
            'vertical-align': 'baseline',
            'border-radius': '0.25rem'
        });

        // Poi applica stili specifici per tipo
        $('.badge-schedina, .badge[style*="background-color: #7b0828"]').css({
            'background-color': '#7b0828',
            'color': 'white'
        });

        $('.badge-ricarica, .badge[style*="background-color: #ffc107"]').css({
            'background-color': '#ffc107',
            'color': '#000'
        });

        $('.badge-prelievo, .badge[style*="background-color: #6f42c1"]').css({
            'background-color': '#6f42c1',
            'color': 'white'
        });

        $('.badge-incasso-credito, .badge[style*="background-color: #198754"]').css({
            'background-color': '#198754',
            'color': 'white'
        });

        $('.badge-pagamento-debito, .badge[style*="background-color: #fd7e14"]').css({
            'background-color': '#fd7e14',
            'color': 'white'
        });

        // 3. FIX BUTTON SALDA E SALDA TUTTI
        $('.btn-salda-movimento, .btn-salda-tutti').css({
            'background-color': '#198754',
            'border-color': '#198754',
            'color': 'white',
            'display': 'inline-block'
        });

        // 4. FIX COLORAZIONE TESTO IMPORTI - anche qui più specifici
        $('.text-danger, td.text-danger, td[class*="text-danger"]').css('color', '#dc3545');
        $('.text-success, td.text-success, td[class*="text-success"]').css('color', '#198754');
        $('.fw-bold, td.fw-bold, [class*="fw-bold"]').css('font-weight', '700');

        // 5. APPLICA STILI SPECIFICI ALLA SEZIONE "MOVIMENTI DA SALDARE"
        // Questa chiamata gestisce in modo specifico la sezione dei movimenti da saldare
        // che potrebbe essere stata caricata dinamicamente via AJAX
        if ($('.card-body-movimenti-da-saldare').length > 0) {
            applyStylesToMovimentiDaSaldare();
        }

        stylesApplied = true;
        isProcessing = false;
        initialized = true;
    }
    
    // Imposta il valore dell'importo in modo robusto
    function setImportoValueRobust(value) {
        var success = false;
        
        // Strategia 1: input[id="id_importo"]
        var input = document.getElementById('id_importo');
        if (input) {
            input.value = value;
            $(input).trigger('change');
            return true;
        }
        
        // Strategia 2: input[name="importo"]
        var inputs = document.getElementsByName('importo');
        if (inputs.length > 0) {
            inputs[0].value = value;
            $(inputs[0]).trigger('change');
            return true;
        }
        
        // Strategia 3: qualsiasi input numerico nel form
        var formInputs = document.querySelectorAll('form input[type="number"]');
        if (formInputs.length > 0) {
            formInputs[0].value = value;
            $(formInputs[0]).trigger('change');
            return true;
        }
        
        return false;
    }
    
    // Funzione per caricare i dati del cliente
    function caricaDatiCliente(clienteId) {
        if (!clienteId) return;
        
        $.ajax({
            url: "/api/movimenti-cliente/",
            data: { 'cliente_id': clienteId },
            dataType: 'json',
            success: function(data) {
                // Mostra i dati del cliente
                renderClienteInfo(data);
                
                // Riapplica gli stili dopo che i dati sono stati caricati
                setTimeout(fixAllStyles, 100);
            },
            error: function() {
                // In caso di errore, mostra un messaggio
                $('.card-body-movimenti-da-saldare').html(
                    '<div class="text-center py-4">' +
                    '<i class="fas fa-exclamation-circle text-danger fa-3x mb-3"></i>' +
                    '<p class="mb-0">Errore nel caricamento dei dati del cliente</p>' +
                    '</div>'
                );
            }
        });
    }
    
    // Funzione dedicata per applicare gli stili alla sezione "Movimenti da saldare"
    function applyStylesToMovimentiDaSaldare() {
        // Applica stili specifici ai badge nella sezione movimenti da saldare
        $('.card-body-movimenti-da-saldare .badge').each(function() {
            var $badge = $(this);
            // Imposta stili di base
            $badge.css({
                'display': 'inline-block',
                'padding': '0.25em 0.4em',
                'font-size': '75%',
                'font-weight': '700',
                'line-height': '1',
                'text-align': 'center',
                'white-space': 'nowrap',
                'vertical-align': 'baseline',
                'border-radius': '0.25rem'
            });

            // Applica colori in base alla classe o tipo
            if ($badge.hasClass('badge-schedina') || $badge.attr('class').indexOf('schedina') !== -1) {
                $badge.css({
                    'background-color': '#7b0828',
                    'color': 'white'
                });
            } else if ($badge.hasClass('badge-ricarica') || $badge.attr('class').indexOf('ricarica') !== -1) {
                $badge.css({
                    'background-color': '#ffc107',
                    'color': '#000'
                });
            } else if ($badge.hasClass('badge-prelievo') || $badge.attr('class').indexOf('prelievo') !== -1) {
                $badge.css({
                    'background-color': '#6f42c1',
                    'color': 'white'
                });
            } else if ($badge.hasClass('badge-incasso-credito') || $badge.attr('class').indexOf('incasso-credito') !== -1) {
                $badge.css({
                    'background-color': '#198754',
                    'color': 'white'
                });
            } else if ($badge.hasClass('badge-pagamento-debito') || $badge.attr('class').indexOf('pagamento-debito') !== -1) {
                $badge.css({
                    'background-color': '#fd7e14',
                    'color': 'white'
                });
            }
        });

        // Applica stili per bottoni salda
        $('.card-body-movimenti-da-saldare .btn-salda-movimento, .card-body-movimenti-da-saldare .btn-salda-tutti').css({
            'background-color': '#198754',
            'border-color': '#198754',
            'color': 'white',
            'display': 'inline-block'
        });

        // Applica stili agli importi
        $('.card-body-movimenti-da-saldare .text-danger').css('color', '#dc3545');
        $('.card-body-movimenti-da-saldare .text-success').css('color', '#198754');
        $('.card-body-movimenti-da-saldare .fw-bold').css('font-weight', '700');
    }

    // Funzione per renderizzare le informazioni del cliente
    function renderClienteInfo(data) {
        // Contenitore per i dati del cliente
        var container = $('.card-body-movimenti-da-saldare');
        if (!container.length) return;

        // Se non ci sono dati o cliente
        if (!data || !data.cliente) {
            container.html(
                '<div class="text-center py-4">' +
                '<i class="fas fa-user-circle text-muted fa-3x mb-3"></i>' +
                '<p class="mb-0">Seleziona un cliente per vedere i movimenti da saldare</p>' +
                '</div>'
            );
            return;
        }

        // Crea l'header con i dati del cliente
        var headerHtml =
            '<div class="p-3 bg-light border-bottom">' +
            '<div class="row align-items-center">' +
            '<div class="col">' +
            '<h5 class="mb-1">' + data.cliente.nome_completo + '</h5>' +
            '<div class="d-flex">' +
            '<span class="me-3">Saldo: <strong class="' +
            (parseFloat(data.cliente.saldo) < 0 ? 'text-danger' : 'text-success') +
            '">' + data.cliente.saldo + ' €</strong></span>' +
            '<span>Fido: <strong>' + data.cliente.fido_massimo + ' €</strong></span>' +
            '</div></div>';

        // Aggiungi il pulsante "Salda Tutti" se ci sono movimenti
        if (data.movimenti && data.movimenti.length > 0) {
            headerHtml += '<div class="col-auto">' +
                '<button type="button" class="btn btn-success btn-sm btn-salda-tutti" id="salda-tutti-movimenti" data-cliente="' + data.cliente.id + '">' +
                '<i class="fas fa-check-double me-1"></i> Salda Tutti' +
                '</button>' +
                '</div>';
        }

        headerHtml += '</div></div>';

        // Se ci sono movimenti da mostrare
        if (data.movimenti && data.movimenti.length > 0) {
            var tableHtml = '<div style="max-height: 300px; overflow-y: auto;">' +
                '<table class="table table-sm table-hover mb-0">' +
                '<thead><tr><th>Tipo</th><th>Importo</th><th>Data</th><th>Azioni</th></tr></thead>' +
                '<tbody>';

            data.movimenti.forEach(function(movimento) {
                var importoClass = parseFloat(movimento.importo) < 0 ? 'text-danger' : 'text-success';
                var importoValore = Math.abs(parseFloat(movimento.importo)).toFixed(2);

                // Determina il tipo e il nome display
                var tipo = movimento.tipo || '';
                var tipoDisplay = movimento.tipo_display || tipo.charAt(0).toUpperCase() + tipo.slice(1).replace(/_/g, ' ');

                // Determina la classe del badge in base al tipo
                var badgeClass = 'badge-secondary';
                if (movimento.tipo === 'schedina') badgeClass = 'badge-schedina';
                else if (movimento.tipo === 'ricarica') badgeClass = 'badge-ricarica';
                else if (movimento.tipo === 'prelievo') badgeClass = 'badge-prelievo';
                else if (movimento.tipo === 'incasso_credito') badgeClass = 'badge-incasso-credito';
                else if (movimento.tipo === 'pagamento_debito') badgeClass = 'badge-pagamento-debito';

                // Corretto handling del segno dell'importo basato sul tipo di movimento
                var importoValore = Math.abs(parseFloat(movimento.importo)).toFixed(2);

                tableHtml += '<tr>' +
                    '<td><span class="badge ' + badgeClass + '">' + tipoDisplay + '</span></td>' +
                    '<td class="' + importoClass + ' fw-bold">' + importoValore + ' €</td>' +
                    '<td>' + movimento.data + '</td>' +
                    '<td>' +
                    '<a href="javascript:void(0)" class="btn btn-sm btn-success btn-salda-movimento me-1" data-id="' + movimento.id + '">' +
                    '<i class="fas fa-check"></i> Salda</a>' +
                    '<a href="/movimenti/' + movimento.id + '/modifica/" class="btn btn-sm btn-info" title="Dettagli">' +
                    '<i class="fas fa-info-circle"></i></a>' +
                    '</td>' +
                    '</tr>';
            });

            tableHtml += '</tbody></table></div>';
            container.html(headerHtml + tableHtml);

            // Attiva gli event listeners per i pulsanti di saldo
            activateSaldaListeners();

            // Applica gli stili specifici alla sezione movimenti da saldare
            applyStylesToMovimentiDaSaldare();
        } else {
            container.html(headerHtml +
                '<div class="card-body text-center py-4">' +
                '<i class="fas fa-check-circle text-success fa-3x mb-3"></i>' +
                '<p class="mb-0">Nessun movimento da saldare per questo cliente</p>' +
                '</div>'
            );
        }
    }
    
    // Attiva i listener per i pulsanti "Salda" e "Salda Tutti"
    function activateSaldaListeners() {
        // Bottoni "Salda movimento"
        $('.btn-salda-movimento').off('click').on('click', function() {
            var movimentoId = $(this).data('id');
            saldaMovimento(movimentoId);
        });
        
        // Bottone "Salda tutti"
        $('.btn-salda-tutti').off('click').on('click', function() {
            var clienteId = $(this).data('cliente');
            saldaTuttiMovimenti(clienteId);
        });
    }
    
    // Funzione per saldare tutti i movimenti di un cliente specifico
    function saldaTuttiMovimenti(clienteId) {
        // Ottieni tutti gli ID dei movimenti da saldare solo per il cliente selezionato
        var movimentiIds = [];

        // Solo nella sezione "Movimenti da saldare" - container card-body-movimenti-da-saldare
        $('.card-body-movimenti-da-saldare .btn-salda-movimento').each(function() {
            movimentiIds.push($(this).data('id'));
        });
        
        // Se non ci sono movimenti da saldare, esci
        if (movimentiIds.length === 0) {
            alert('Non ci sono movimenti da saldare per questo cliente.');
            return;
        }
        
        // Disabilita il pulsante per evitare doppi click
        $('.btn-salda-tutti').prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> Saldamento in corso...');
        
        // Salda ogni movimento in sequenza
        saldaMovimentiInSequenza(movimentiIds, 0);
    }
    
    // Funzione ricorsiva per saldare i movimenti in sequenza
    function saldaMovimentiInSequenza(movimentiIds, index) {
        // Se abbiamo finito tutti i movimenti, riabilita il pulsante e ricarica i dati del cliente
        if (index >= movimentiIds.length) {
            $('.btn-salda-tutti').prop('disabled', false).html('<i class="fas fa-check-double me-1"></i> Salda Tutti');

            // Ricarica i dati del cliente dopo aver completato tutti i saldi
            var clienteId = $('#id_cliente').val();
            if (clienteId) {
                setTimeout(function() {
                    caricaDatiCliente(clienteId);
                    // Applica gli stili dopo il caricamento dei dati
                    setTimeout(function() {
                        applyStylesToMovimentiDaSaldare();
                        fixAllStyles();
                    }, 600);
                }, 500);
            }

            return;
        }

        // Ottieni l'ID del movimento corrente
        var movimentoId = movimentiIds[index];

        // Salda il movimento
        $.ajax({
            url: '/movimenti/' + movimentoId + '/salda/',
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            success: function(data) {
                // Nascondi e rimuovi la riga del movimento saldato dalla sezione movimenti da saldare
                $('.card-body-movimenti-da-saldare .btn-salda-movimento[data-id="' + movimentoId + '"]').closest('tr').fadeOut(400, function() {
                    $(this).remove();
                });

                // Aggiorna il saldo mostrato nell'intestazione se disponibile
                if (data && data.cliente && data.cliente.saldo !== undefined) {
                    var saldoClass = parseFloat(data.cliente.saldo) < 0 ? 'text-danger' : 'text-success';
                    $('.p-3.bg-light.border-bottom .me-3 strong').attr('class', saldoClass).text(data.cliente.saldo + ' €');
                }

                // Aggiorna lo stato nei movimenti della distinta senza nascondere le righe
                // Prima proviamo ad aggiornare le righe nella tabella principale
                $('#lista-movimenti table tr').each(function() {
                    // Verifica se l'ID nella prima colonna corrisponde all'ID del movimento saldato
                    if ($(this).find('td:first').text().trim() === movimentoId.toString()) {
                        // Aggiorna solo lo stato a "Saldato" nella colonna 6
                        $(this).find('td:nth-child(6)').html('<span class="badge bg-success">Saldato</span>');
                        // Nascondi solo il pulsante Salda, non l'intera riga
                        $(this).find('.btn-salda-movimento').hide();
                    }
                });

                // Aggiorna anche nei tabs "Entrate" e "Uscite"
                $('.tab-content .tab-pane table tr').each(function() {
                    // Verifica se questa riga contiene il pulsante Salda con l'ID corretto
                    var saldaButton = $(this).find('.btn-salda-movimento[data-id="' + movimentoId + '"]');
                    if (saldaButton.length > 0) {
                        // Aggiorna solo lo stato a "Saldato" senza nascondere la riga
                        $(this).find('td:nth-child(6)').html('<span class="badge bg-success">Saldato</span>');
                        // Nascondi solo il pulsante Salda
                        saldaButton.hide();
                    }
                });

                // Procedi con il prossimo movimento dopo una breve pausa
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
    
    // Funzione per saldare un singolo movimento
    function saldaMovimento(movimentoId) {
        $.ajax({
            url: '/movimenti/' + movimentoId + '/salda/',
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            success: function(data) {
                // Mostra messaggio di successo
                var alertHtml = '<div class="alert alert-success alert-dismissible fade show" role="alert">' +
                    (data.message || 'Movimento saldato con successo') +
                    '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>' +
                    '</div>';
                $('.container > .row:first').after(alertHtml);

                // Nascondi la riga del movimento saldato nella sezione movimenti da saldare
                $('.card-body-movimenti-da-saldare .btn-salda-movimento[data-id="' + movimentoId + '"]').closest('tr').fadeOut(400, function() {
                    // Rimuovi effettivamente la riga dal DOM dopo la fine dell'animazione
                    $(this).remove();
                });

                // Auto-chiudi l'alert dopo 5 secondi
                setTimeout(function() {
                    $('.alert').alert('close');
                }, 5000);

                // Aggiorna il saldo del cliente nell'intestazione se presente nei dati ricevuti
                if (data.cliente && data.cliente.saldo !== undefined) {
                    var saldoClass = parseFloat(data.cliente.saldo) < 0 ? 'text-danger' : 'text-success';
                    $('.p-3.bg-light.border-bottom .me-3 strong').attr('class', saldoClass).text(data.cliente.saldo + ' €');
                }

                // Ricarica i dati del cliente completi dopo un breve ritardo
                var clienteId = $('#id_cliente').val();
                if (clienteId) {
                    setTimeout(function() {
                        caricaDatiCliente(clienteId);
                        // Applica gli stili dopo il caricamento dei dati
                        setTimeout(applyStylesToMovimentiDaSaldare, 600);
                    }, 500);
                }

                // Aggiorna lo stato nei movimenti della distinta senza nascondere le righe
                // Prima proviamo ad aggiornare le righe nella tabella principale
                $('#lista-movimenti table tr').each(function() {
                    // Verifica se l'ID nella prima colonna corrisponde all'ID del movimento saldato
                    if ($(this).find('td:first').text().trim() === movimentoId.toString()) {
                        // Aggiorna solo lo stato a "Saldato" nella colonna 6
                        $(this).find('td:nth-child(6)').html('<span class="badge bg-success">Saldato</span>');
                        // Nascondi solo il pulsante Salda, non l'intera riga
                        $(this).find('.btn-salda-movimento').hide();
                    }
                });

                // Aggiorna anche nei tabs "Entrate" e "Uscite"
                $('.tab-content .tab-pane table tr').each(function() {
                    // Verifica se questa riga contiene il pulsante Salda con l'ID corretto
                    var saldaButton = $(this).find('.btn-salda-movimento[data-id="' + movimentoId + '"]');
                    if (saldaButton.length > 0) {
                        // Aggiorna solo lo stato a "Saldato" senza nascondere la riga
                        $(this).find('td:nth-child(6)').html('<span class="badge bg-success">Saldato</span>');
                        // Nascondi solo il pulsante Salda
                        saldaButton.hide();
                    }
                });

                // Applica gli stili dopo tutte le modifiche al DOM
                setTimeout(fixAllStyles, 700);
            },
            error: function() {
                // Mostra messaggio di errore
                var alertHtml = '<div class="alert alert-danger alert-dismissible fade show" role="alert">' +
                    'Errore durante il saldo del movimento' +
                    '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>' +
                    '</div>';
                $('.container > .row:first').after(alertHtml);
            }
        });
    }
    
    // Configura un MutationObserver per monitorare cambiamenti nella sezione movimenti da saldare
    function setupMutationObserver() {
        // Verifica che la funzionalità sia supportata
        if (!window.MutationObserver) return;

        // Seleziona il contenitore dei movimenti da saldare
        var movimentiContainer = document.querySelector('.card-body-movimenti-da-saldare');
        if (!movimentiContainer) return;

        // Crea un nuovo osservatore
        var observer = new MutationObserver(function(mutations) {
            // Applica gli stili quando vengono rilevate modifiche
            applyStylesToMovimentiDaSaldare();
        });

        // Configurazione dell'osservatore (monitora tutte le modifiche al contenuto)
        var config = {
            attributes: true,
            childList: true,
            subtree: true,
            characterData: true
        };

        // Avvia l'osservazione
        observer.observe(movimentiContainer, config);
    }

    // Funzione di inizializzazione principale
    function initialize() {
        // Applica immediatamente le correzioni
        fixAllStyles();

        // Aggiungiamo un event listener per qualsiasi click sulla pagina
        document.addEventListener('click', function() {
            // Ricontrolla gli stili dopo 100ms
            setTimeout(fixAllStyles, 100);
        });

        // Gestione select del cliente
        $('#id_cliente').on('change', function() {
            var clienteId = $(this).val();
            if (clienteId) {
                // Aggiorna l'URL senza ricaricare la pagina
                var newUrl = window.location.pathname + "?cliente=" + clienteId;
                history.pushState({}, '', newUrl);

                // Carica i dati del cliente tramite AJAX
                caricaDatiCliente(clienteId);

                // Applica stili dopo un breve ritardo per consentire all'AJAX di completarsi
                setTimeout(function() {
                    applyStylesToMovimentiDaSaldare();
                    fixAllStyles();
                }, 800);
            }
        });

        // Gestione pulsanti salda
        activateSaldaListeners();

        // Sostituisci la funzione globale setImportoValue per compatibilità
        window.setImportoValue = setImportoValueRobust;

        // Carica automaticamente i dati del cliente se l'URL ha un parametro cliente
        var urlParams = new URLSearchParams(window.location.search);
        var clienteParam = urlParams.get('cliente');
        if (clienteParam) {
            $('#id_cliente').val(clienteParam).trigger('change');
        }

        // Configura l'observer per monitorare cambiamenti nella sezione movimenti da saldare
        // dopo che il DOM è stato completamente caricato
        setTimeout(setupMutationObserver, 1000);
    }
    
    // Esegui quando il documento è pronto
    $(document).ready(function() {
        // Inizializza una sola volta
        initialize();

        // Ricontrolla dopo 1 secondo per sicurezza
        setTimeout(fixAllStyles, 1000);

        // Imposta un controllo periodico ogni 3 secondi per garantire la coerenza degli stili
        // Questo aiuta con elementi dinamici che potrebbero essere stati caricati o modificati
        // dopo l'inizializzazione
        setInterval(function() {
            // Verifica se ci sono elementi nella sezione movimenti da saldare e applica stili
            if ($('.card-body-movimenti-da-saldare').length > 0) {
                applyStylesToMovimentiDaSaldare();
            }
            // Riapplica tutti gli stili per ogni evenienza
            fixAllStyles();
        }, 3000);
    });
    
})(window, document, jQuery);