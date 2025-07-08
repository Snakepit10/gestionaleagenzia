// main.js - Funzionalità JS per Gestionale Agenzia

// Inizializzazioni comuni
$(document).ready(function() {
    // Inizializza tutti i select2
    $('.select2').select2({
        theme: 'bootstrap-5',
        placeholder: 'Seleziona...',
        allowClear: true
    });

    // Chiudi messaggi dopo 5 secondi
    setTimeout(function() {
        $('.alert').alert('close');
    }, 5000);

    // Tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
});

// Funzione per caricare i movimenti del cliente selezionato
function caricaMovimentiCliente(clienteId, containerId) {
    if (!clienteId) return;

    $.ajax({
        url: '/api/movimenti-cliente/',
        data: {
            'cliente_id': clienteId
        },
        dataType: 'json',
        success: function(data) {
            // Aggiorna le informazioni del cliente
            $('#info-cliente-nome').text(data.cliente.nome_completo);
            $('#info-cliente-saldo').text(data.cliente.saldo + ' €');
            $('#info-cliente-fido').text(data.cliente.fido_massimo + ' €');
            
            // Classe per il saldo (rosso se > 0)
            if (parseFloat(data.cliente.saldo) > 0) {
                $('#info-cliente-saldo').addClass('text-danger');
            } else {
                $('#info-cliente-saldo').removeClass('text-danger');
            }
            
            // Contenitore per i movimenti
            var $container = $('#' + containerId);
            $container.empty();
            
            // Se non ci sono movimenti
            if (data.movimenti.length === 0) {
                $container.append(
                    '<div class="text-center py-4">' +
                    '<i class="fas fa-check-circle text-success fa-3x mb-3"></i>' +
                    '<p class="mb-0">Nessun movimento da saldare per questo cliente</p>' +
                    '</div>'
                );
                return;
            }
            
            // Crea la tabella dei movimenti
            var $table = $('<table class="table table-sm table-hover mb-0"></table>');
            var $thead = $('<thead><tr><th>Tipo</th><th>Importo</th><th>Data</th><th>Azioni</th></tr></thead>');
            var $tbody = $('<tbody></tbody>');
            
            // Popola la tabella con i movimenti
            $.each(data.movimenti, function(index, movimento) {
                var importoClass = parseFloat(movimento.importo) < 0 ? 'text-danger' : 'text-success';
                
                $tbody.append(
                    '<tr>' +
                    '<td>' + movimento.tipo + '</td>' +
                    '<td class="' + importoClass + '">' + Math.abs(parseFloat(movimento.importo)).toFixed(2) + ' €</td>' +
                    '<td>' + movimento.data + '</td>' +
                    '<td>' +
                    '<a href="/movimenti/' + movimento.id + '/salda/" class="btn btn-sm btn-success">' +
                    '<i class="fas fa-check"></i> Salda</a>' +
                    '</td>' +
                    '</tr>'
                );
            });
            
            $table.append($thead).append($tbody);
            $container.append($table);
        },
        error: function(xhr, status, error) {
            console.error('Errore nel caricamento dei movimenti:', error);
            $('#' + containerId).html(
                '<div class="alert alert-danger">' +
                'Errore nel caricamento dei movimenti. Riprova più tardi.' +
                '</div>'
            );
        }
    });
}

// Funzione per calcolare i totali della distinta
function calcolaTotaliDistinta() {
    var cassaIniziale = parseFloat($('#id_cassa_iniziale').val()) || 0;
    var cassaFinale = parseFloat($('#id_cassa_finale').val()) || 0;
    var totaleEntrate = parseFloat($('#totale-entrate').text()) || 0;
    var totaleUscite = parseFloat($('#totale-uscite').text()) || 0;
    var totaleBevande = parseFloat($('#id_totale_bevande').val()) || 0;
    var saldoTerminale = parseFloat($('#id_saldo_terminale').val()) || 0;
    
    // Calcola la differenza di cassa
    var differenza = cassaFinale - cassaIniziale - totaleEntrate + totaleUscite + totaleBevande;
    
    // Se il saldo terminale è impostato, considera anche quello
    if (saldoTerminale) {
        differenza -= saldoTerminale;
    }
    
    // Aggiorna il campo differenza
    $('#differenza-cassa').text(differenza.toFixed(2) + ' €');
    
    // Cambia il colore in base alla differenza (rosso se non è zero)
    if (differenza !== 0) {
        $('#differenza-cassa').removeClass('text-success').addClass('text-danger');
    } else {
        $('#differenza-cassa').removeClass('text-danger').addClass('text-success');
    }
}

// Funzione per confermare eliminazione
function confermaEliminazione(url, messaggio) {
    if (confirm(messaggio || 'Sei sicuro di voler eliminare questo elemento?')) {
        window.location.href = url;
    }
    return false;
}

// Funzioni per l'esportazione dati
function esportaCSV(tableId, filename) {
    var csv = [];
    var rows = document.querySelectorAll('#' + tableId + ' tr');
    
    for (var i = 0; i < rows.length; i++) {
        var row = [], cols = rows[i].querySelectorAll('td, th');
        
        for (var j = 0; j < cols.length; j++) {
            // Pulisci il testo dalle formattazioni HTML
            var text = cols[j].innerText.replace(/(\r\n|\n|\r)/gm, '').replace(/,/g, ';');
            row.push('"' + text + '"');
        }
        
        csv.push(row.join(','));
    }
    
    // Scarica il file CSV
    downloadCSV(csv.join('\n'), filename);
}

function downloadCSV(csv, filename) {
    var csvFile;
    var downloadLink;
    
    // Crea il file CSV
    csvFile = new Blob([csv], {type: 'text/csv'});
    
    // Crea il link per il download
    downloadLink = document.createElement('a');
    downloadLink.download = filename;
    downloadLink.href = window.URL.createObjectURL(csvFile);
    downloadLink.style.display = 'none';
    
    // Aggiungi il link al DOM e avvia il download
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
}