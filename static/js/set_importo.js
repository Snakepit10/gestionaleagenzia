// Script per impostare il valore del campo importo tramite pulsanti
// Deve essere caricato PRIMA di distinta_detail.js ma DOPO jQuery

// Evita conflitti con altre variabili globali
(function(window, document, $) {
    'use strict';

    // Esporta funzione globale per compatibilità con onclick inline
    window.setImportoValue = function(value) {
        return ImportoRapido.setImportoValue(value);
    };

    // Namespace per evitare collisioni
    var ImportoRapido = {
        // Configurazione
        config: {
            activeClass: 'btn-success',
            inactiveClass: 'btn-dark',
            buttonSelector: '.importo-btn',
            animationClass: 'pulsato'
        },

        // Funzione principale per impostare il valore
        setImportoValue: function(value) {
            console.log('ImportoRapido: setImportoValue chiamato con valore', value);
            // Flag per tracciare il successo
            let success = false;

            // Metodo 1: prova per attributo name
            var inputsByName = document.getElementsByName('importo');
            if (inputsByName.length > 0) {
                for (var i = 0; i < inputsByName.length; i++) {
                    inputsByName[i].value = value;
                    // Trigger change event for jQuery plugins
                    $(inputsByName[i]).trigger('change');
                    success = true;
                }
                console.log('Importo impostato tramite name');
            }

            // Metodo 2: prova per id che contiene 'importo'
            var importoFields = document.querySelectorAll('input[id*="importo"]');
            if (importoFields.length > 0) {
                importoFields.forEach(function(field) {
                    field.value = value;
                    // Trigger change event for jQuery plugins
                    $(field).trigger('change');
                });
                success = true;
                console.log('Importo impostato tramite id contenente importo');
            }

            // Metodo 3: prova per id esatto
            var inputById = document.getElementById('id_importo');
            if (inputById) {
                inputById.value = value;
                // Trigger change event for jQuery plugins
                $(inputById).trigger('change');
                success = true;
                console.log('Importo impostato tramite id esatto');
            }

            // Metodo 4: prova a trovare qualsiasi input di tipo number
            var numberInputs = document.querySelectorAll('input[type="number"]');
            if (numberInputs.length > 0) {
                numberInputs[0].value = value;
                // Trigger change event for jQuery plugins
                $(numberInputs[0]).trigger('change');
                success = true;
                console.log('Importo impostato trovando il primo input numerico');
            }

            // Verifica se abbiamo avuto successo
            if (success) {
                // Effetto visivo di feedback
                ImportoRapido.highlightImportoButtons(value);
                return true;
            } else {
                console.error('Non è stato possibile trovare il campo importo');
                return false;
            }
        },

        // Funzione per evidenziare il pulsante cliccato
        highlightImportoButtons: function(value) {
            console.log('ImportoRapido: highlightImportoButtons chiamato');

            // Resetta tutti i pulsanti - prima con JavaScript puro
            document.querySelectorAll(ImportoRapido.config.buttonSelector).forEach(function(btn) {
                btn.classList.remove('active');
                btn.classList.remove(ImportoRapido.config.activeClass);
                btn.classList.add(ImportoRapido.config.inactiveClass);
            });

            // Attiva il pulsante corrispondente
            var activeBtn = document.querySelector(ImportoRapido.config.buttonSelector + '[data-value="' + value + '"]');
            if (activeBtn) {
                console.log('ImportoRapido: trovato pulsante attivo:', activeBtn);
                activeBtn.classList.remove(ImportoRapido.config.inactiveClass);
                activeBtn.classList.add('active', ImportoRapido.config.activeClass);

                // Anche con jQuery per maggiore compatibilità
                $(activeBtn)
                    .removeClass(ImportoRapido.config.inactiveClass)
                    .addClass('active ' + ImportoRapido.config.activeClass);

                // Aggiungiamo un effetto flash per indicare che è stato selezionato
                activeBtn.classList.add(ImportoRapido.config.animationClass);
                setTimeout(function() {
                    activeBtn.classList.remove(ImportoRapido.config.animationClass);
                }, 300);
            }

            // Effetto flash sul campo importo per feedback visivo
            var importoInputs = document.querySelectorAll('[name="importo"], input[id*="importo"], input[type="number"]');
            importoInputs.forEach(function(input) {
                $(input).addClass('bg-light')
                    .delay(300)
                    .queue(function() {
                        $(this).removeClass('bg-light').dequeue();
                    });
            });
        },

        // Inizializzazione degli event listener
        init: function() {
            console.log('ImportoRapido: inizializzazione');
            var self = this;

            // Assicurati che tutti i pulsanti abbiano l'event listener corretto
            $(self.config.buttonSelector).off('click').on('click', function() {
                var valore = $(this).data('value');
                console.log('ImportoRapido: pulsante cliccato con valore', valore);
                self.setImportoValue(valore);
            });

            // Assicurati che i pulsanti abbiano lo stile corretto iniziale
            $(self.config.buttonSelector).each(function() {
                $(this).addClass(self.config.inactiveClass);
            });

            console.log('ImportoRapido: inizializzazione completata');
        }
    };

    // Esposizione pubblica dell'oggetto
    window.ImportoRapido = ImportoRapido;

    // Metodo di inizializzazione che si assicura che jQuery sia pronto
    $(document).ready(function() {
        console.log('Document ready - inizializzando ImportoRapido');
        ImportoRapido.init();
    });

})(window, document, jQuery);