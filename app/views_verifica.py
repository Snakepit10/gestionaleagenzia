@login_required
@user_passes_test(is_manager_or_admin)
def verifica_distinta(request, pk):
    distinta = get_object_or_404(DistintaCassa, pk=pk)
    
    if distinta.stato != 'chiusa':
        messages.error(request, 'Questa distinta non può essere verificata.')
        return redirect('dettaglio_distinta', pk=distinta.pk)
    
    if request.method == 'POST':
        form = VerificaDistintaForm(request.POST, instance=distinta)
        if form.is_valid():
            # Dati prima della verifica per il log
            distinta_before = {
                'operatore': distinta.operatore.username,
                'data': distinta.data.strftime('%d/%m/%Y'),
                'ora_inizio': distinta.ora_inizio.strftime('%H:%M'),
                'ora_fine': distinta.ora_fine.strftime('%H:%M') if distinta.ora_fine else "",
                'stato': 'chiusa',
                'cassa_iniziale': str(distinta.cassa_iniziale),
                'cassa_finale': str(distinta.cassa_finale) if distinta.cassa_finale else "0.00",
                'differenza_cassa': str(distinta.differenza_cassa) if distinta.differenza_cassa else "0.00"
            }
            
            distinta = form.save(commit=False)
            distinta.stato = 'verificata'
            distinta.verificata_da = request.user
            distinta.data_verifica = timezone.now()
            distinta.save()
            
            # Dati dopo la verifica per il log
            distinta_after = {
                'operatore': distinta.operatore.username,
                'data': distinta.data.strftime('%d/%m/%Y'),
                'ora_inizio': distinta.ora_inizio.strftime('%H:%M'),
                'ora_fine': distinta.ora_fine.strftime('%H:%M') if distinta.ora_fine else "",
                'stato': 'verificata',
                'cassa_iniziale': str(distinta.cassa_iniziale),
                'cassa_finale': str(distinta.cassa_finale) if distinta.cassa_finale else "0.00",
                'differenza_cassa': str(distinta.differenza_cassa) if distinta.differenza_cassa else "0.00",
                'verificata_da': distinta.verificata_da.username,
                'data_verifica': distinta.data_verifica.strftime('%d/%m/%Y %H:%M'),
                'note_verifica': distinta.note_verifica if distinta.note_verifica else ""
            }
            
            # Registra l'azione nei log
            ActivityLog.log_action(
                user=request.user,
                obj=distinta,
                action='status_change',
                description=f"Verifica Distinta N° {distinta.pk} da parte di {request.user.username}",
                data_before=distinta_before,
                data_after=distinta_after
            )
            
            messages.success(request, f'Distinta N° {distinta.pk} verificata con successo!')
            return redirect('lista_distinte')
    else:
        form = VerificaDistintaForm(instance=distinta)
    
    context = {
        'form': form,
        'distinta': distinta,
        'titolo': 'Verifica Distinta'
    }
    
    return render(request, 'app/verifica_distinta.html', context)