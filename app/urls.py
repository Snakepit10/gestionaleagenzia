from django.urls import path
from . import views

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
    path('bilancio/conto/<int:pk>/modifica/', views.modifica_conto, name='modifica_conto'),
    path('bilancio/conto/<int:pk>/saldo/', views.modifica_saldo, name='modifica_saldo'),
    path('bilancio/<int:pk>/', views.dettaglio_bilancio, name='dettaglio_bilancio'),
    path('bilancio/giroconto/', views.effettua_giroconto, name='effettua_giroconto'),
    path('bilancio/movimenti/', views.lista_movimenti_conti, name='lista_movimenti_conti'),

    # Logs
    path('logs/', views.lista_logs, name='lista_logs'),
    path('logs/<int:pk>/', views.dettaglio_log, name='dettaglio_log'),

    # API
    path('api/movimenti-cliente/', views.get_movimenti_cliente, name='api_movimenti_cliente'),
]