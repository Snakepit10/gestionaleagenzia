from django.urls import path
from . import views
from . import views_conto_economico as ce

urlpatterns = [
    # Homepage (accessibile a tutti gli utenti autenticati)
    path('', views.home, name='home'),

    # Dashboard (accesso ristretto)
    path('dashboard/', views.dashboard, name='dashboard'),

    # Clienti
    path('clienti/', views.lista_clienti, name='lista_clienti'),
    path('clienti/nuovo/', views.nuovo_cliente, name='nuovo_cliente'),
    path('clienti/<int:pk>/', views.dettaglio_cliente, name='dettaglio_cliente'),
    path('clienti/<int:pk>/modifica/', views.modifica_cliente, name='modifica_cliente'),

    # Movimenti
    path('movimenti/', views.lista_movimenti, name='lista_movimenti'),
    path('movimenti/nuovo/', views.nuovo_movimento, name='nuovo_movimento'),
    path('movimenti/<int:pk>/salda/', views.salda_movimento, name='salda_movimento'),
    path('movimenti/<int:pk>/dettaglio/', views.dettaglio_movimento, name='dettaglio_movimento'),
    path('movimenti/<int:pk>/modifica/', views.modifica_movimento, name='modifica_movimento'),
    path('movimenti/<int:pk>/elimina/', views.elimina_movimento, name='elimina_movimento'),

    # Distinte
    path('distinte/', views.lista_distinte, name='lista_distinte'),
    path('distinte/nuova/', views.nuova_distinta, name='nuova_distinta'),
    path('distinte/<int:pk>/', views.dettaglio_distinta, name='dettaglio_distinta'),
    path('distinte/<int:pk>/chiudi/', views.chiudi_distinta, name='chiudi_distinta'),
    path('distinte/<int:pk>/verifica/', views.verifica_distinta, name='verifica_distinta'),
    path('distinte/<int:pk>/riapri/', views.riapri_distinta, name='riapri_distinta'),

    # Bilancio Finanziario
    path('bilancio/', views.bilancio_finanziario, name='bilancio_finanziario'),
    path('bilancio/conto/nuovo/', views.nuovo_conto, name='nuovo_conto'),
    path('bilancio/conto/<int:pk>/saldo/', views.modifica_saldo, name='modifica_saldo'),
    path('bilancio/conto/<int:pk>/modifica/', views.modifica_conto, name='modifica_conto'),
    path('bilancio/conto/<int:pk>/elimina/', views.elimina_conto, name='elimina_conto'),
    path('bilancio/<int:pk>/', views.dettaglio_bilancio, name='dettaglio_bilancio'),
    path('bilancio/giroconto/', views.effettua_giroconto, name='effettua_giroconto'),
    path('bilancio/movimenti/', views.lista_movimenti_conti, name='lista_movimenti_conti'),
    path('bilancio/movimenti/<int:pk>/elimina/', views.elimina_movimento_conti, name='elimina_movimento_conti'),

    # Riepilogo Crediti
    path('riepilogo-crediti/', views.riepilogo_crediti, name='riepilogo_crediti'),
    path('saldi-esterni/', views.estrazione_saldi, name='estrazione_saldi'),
    path('conti-servizio/azzeramento/', views.azzeramento_conti_servizio, name='azzeramento_conti_servizio'),
    path('api/cast/giorni/', views.api_giorni_mancanti, name='api_giorni_mancanti'),
    path('api/cast/saldi/', views.api_ricevi_saldi, name='api_ricevi_saldi'),
    path('api/saldo-esterno/salva/', views.salva_valore_esterno, name='salva_valore_esterno'),

    # Conto Economico (report mensili ricavi/spese)
    path('conto-economico/', ce.conto_economico, name='conto_economico'),
    path('conto-economico/apri/', ce.apri_mese, name='conto_economico_apri'),
    path('conto-economico/anno/<int:anno>/', ce.riepilogo_annuale, name='riepilogo_annuale'),
    path('conto-economico/consolidato/', ce.conto_economico_consolidato, name='conto_economico_consolidato'),
    # tassonomia globale (super-admin)
    path('conto-economico/categorie/', ce.categorie_spesa, name='categorie_spesa'),
    path('conto-economico/categorie/nuova/', ce.nuova_categoria_spesa, name='nuova_categoria_spesa'),
    path('conto-economico/categorie/<int:pk>/modifica/', ce.modifica_categoria_spesa, name='modifica_categoria_spesa'),
    path('conto-economico/categorie/<int:pk>/elimina/', ce.elimina_categoria_spesa, name='elimina_categoria_spesa'),
    path('conto-economico/prodotti/', ce.prodotti_ricavo, name='prodotti_ricavo'),
    path('conto-economico/prodotti/nuovo/', ce.nuovo_prodotto_ricavo, name='nuovo_prodotto_ricavo'),
    path('conto-economico/prodotti/<int:pk>/modifica/', ce.modifica_prodotto_ricavo, name='modifica_prodotto_ricavo'),
    path('conto-economico/prodotti/<int:pk>/elimina/', ce.elimina_prodotto_ricavo, name='elimina_prodotto_ricavo'),
    # dettaglio mese e operazioni
    path('conto-economico/<int:anno>/<int:mese>/', ce.conto_economico_mese, name='conto_economico_mese'),
    path('conto-economico/<int:anno>/<int:mese>/ricavi/', ce.conto_economico_ricavi, name='conto_economico_ricavi'),
    path('conto-economico/<int:anno>/<int:mese>/ricavi/nuova/', ce.nuova_voce_ricavo, name='nuova_voce_ricavo'),
    path('conto-economico/<int:anno>/<int:mese>/ricavi/<int:pk>/elimina/', ce.elimina_voce_ricavo, name='elimina_voce_ricavo'),
    path('conto-economico/<int:anno>/<int:mese>/costi/nuova/', ce.nuova_voce_costo, name='nuova_voce_costo'),
    path('conto-economico/<int:anno>/<int:mese>/costi/<int:pk>/elimina/', ce.elimina_voce_costo, name='elimina_voce_costo'),
    path('conto-economico/<int:anno>/<int:mese>/conto-spese/importa/', ce.importa_conto_spese, name='importa_conto_spese'),
    path('conto-economico/<int:anno>/<int:mese>/estratto/carica/', ce.carica_estratto, name='carica_estratto'),
    path('conto-economico/<int:anno>/<int:mese>/estratto/', ce.classifica_estratto, name='classifica_estratto'),

    # Logs
    path('logs/', views.lista_logs, name='lista_logs'),
    path('logs/<int:pk>/', views.dettaglio_log, name='dettaglio_log'),

    # API
    path('api/movimenti-cliente/', views.get_movimenti_cliente, name='api_movimenti_cliente'),
]