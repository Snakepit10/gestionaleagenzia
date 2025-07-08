/**
 * conteggio_cassa.js - Gestisce la funzionalità di conteggio parziale della cassa
 * Formula: Cassa = Saldo Terminale + Entrate - Uscite + Bevande
 */

(function(window, document, $) {
    'use strict';

    // Ottieni riferimenti agli elementi DOM
    const saldoTerminaleInput = document.getElementById('conteggio_saldo_terminale');
    const bevandeInput = document.getElementById('conteggio_bevande');
    const risultatoConteggio = document.getElementById('risultato_conteggio');
    const formulaConteggio = document.getElementById('formula_conteggio');
    
    // Salva i valori fissi
    let totaleEntrate = 0;
    let totaleUscite = 0;
    
    /**
     * Inizializza i valori delle entrate e uscite
     */
    function initializeValues() {
        // Questo metodo non è più necessario poiché useremo jQuery
        // che offre selettori più potenti per trovare gli elementi
    }
    
    /**
     * Formatta un numero con 2 decimali e simbolo euro
     * @param {number} value - Valore da formattare
     * @returns {string} - Valore formattato
     */
    function formatCurrency(value) {
        return value.toFixed(2).replace('.', ',') + ' €';
    }
    
    /**
     * Calcola il risultato del conteggio cassa secondo la formula
     * Cassa = Saldo Terminale + Entrate - Uscite + Bevande
     */
    function calcolaConteggioSaldo() {
        // Ottieni i valori dai campi input
        const saldoTerminale = parseFloat(saldoTerminaleInput.value) || 0;
        const bevande = parseFloat(bevandeInput.value) || 0;
        
        // Calcola il risultato
        const risultato = saldoTerminale + totaleEntrate - totaleUscite + bevande;
        
        // Aggiorna il testo della formula
        formulaConteggio.textContent = `${formatCurrency(saldoTerminale)} + ${formatCurrency(totaleEntrate)} - ${formatCurrency(totaleUscite)} + ${formatCurrency(bevande)} = ${formatCurrency(risultato)}`;
        
        // Aggiorna il risultato
        risultatoConteggio.textContent = formatCurrency(risultato);
        
        // Assegna una classe in base al valore
        if (risultato < 0) {
            risultatoConteggio.className = 'mb-0 display-6 text-danger';
        } else {
            risultatoConteggio.className = 'mb-0 display-6 text-success';
        }
    }
    
    /**
     * Inizializza gli event listener
     */
    function initEventListeners() {
        // Aggiungi listener per gli input
        if (saldoTerminaleInput) {
            saldoTerminaleInput.addEventListener('input', calcolaConteggioSaldo);
        }

        if (bevandeInput) {
            bevandeInput.addEventListener('input', calcolaConteggioSaldo);
        }

        // Aggiungi listener per il pulsante "Usa come valore cassa finale"
        const copiaValoreBtn = document.getElementById('copia_valore_cassa');
        if (copiaValoreBtn) {
            copiaValoreBtn.addEventListener('click', function() {
                // Ottieni il valore calcolato (senza il simbolo €)
                const valoreCassa = parseFloat(risultatoConteggio.textContent.replace('€', '').replace(',', '.').trim());

                // Cerca il campo cassa finale nella pagina (potrebbe essere nella pagina di chiusura distinta)
                const cassaFinaleInput = document.getElementById('id_cassa_finale');

                // Se il campo esiste, imposta il valore
                if (cassaFinaleInput) {
                    cassaFinaleInput.value = valoreCassa.toFixed(2);

                    // Mostra messaggio di successo
                    const successMsg = document.getElementById('copia_successo');
                    if (successMsg) {
                        successMsg.classList.remove('d-none');

                        // Nascondi il messaggio dopo 5 secondi
                        setTimeout(function() {
                            successMsg.classList.add('d-none');
                        }, 5000);
                    }

                    // Se c'è un pulsante per andare alla pagina di chiusura, evidenzialo
                    const chiudiDistintaBtn = document.querySelector('a[href*="chiudi_distinta"]');
                    if (chiudiDistintaBtn) {
                        chiudiDistintaBtn.classList.add('btn-pulse');

                        // Rimuovi la classe pulsante dopo 3 secondi
                        setTimeout(function() {
                            chiudiDistintaBtn.classList.remove('btn-pulse');
                        }, 3000);
                    }
                } else {
                    // Se non trova il campo nella pagina corrente, memorizza il valore nella sessionStorage
                    // per poterlo recuperare nella pagina di chiusura
                    sessionStorage.setItem('valoreCassaCalcolato', valoreCassa.toFixed(2));

                    // Trova il link alla pagina di chiusura distinta
                    const chiudiDistintaBtn = document.querySelector('a[href*="chiudi_distinta"]');
                    if (chiudiDistintaBtn) {
                        // Aggiungi una classe per evidenziare il pulsante
                        chiudiDistintaBtn.classList.add('btn-pulse');

                        // Mostra messaggio di successo con invito a cliccare sul pulsante
                        const successMsg = document.getElementById('copia_successo');
                        if (successMsg) {
                            successMsg.innerHTML = '<i class="fas fa-check-circle me-2"></i>Valore salvato! Ora clicca sul pulsante "Chiudi Distinta".';
                            successMsg.classList.remove('d-none');
                        }

                        // Simuliamo un click sul pulsante dopo 1.5 secondi
                        setTimeout(function() {
                            window.location.href = chiudiDistintaBtn.getAttribute('href');
                        }, 1500);
                    }
                }
            });
        }
    }
    
    /**
     * Inizializza la funzionalità
     */
    function initialize() {
        // Aspetta che jQuery sia completamente caricato
        if (!window.jQuery) {
            setTimeout(initialize, 100);
            return;
        }

        // Inizializza i valori fissi
        // Utilizziamo jQuery per selezionare elementi con il filtro :contains
        $('.form-label').each(function() {
            const label = $(this).text().trim();
            const value = $(this).next('.form-control-plaintext').text().trim();

            if (label === 'Entrate') {
                totaleEntrate = parseFloat(value.replace('€', '').trim()) || 0;
            } else if (label === 'Uscite') {
                totaleUscite = parseFloat(value.replace('€', '').trim()) || 0;
            }
        });

        // Inizializza gli event listener
        initEventListeners();

        // Calcola il risultato iniziale
        calcolaConteggioSaldo();
    }
    
    // Inizializza quando il documento è pronto
    $(document).ready(initialize);
    
})(window, document, jQuery);