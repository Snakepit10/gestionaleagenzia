from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView
from django.urls import reverse_lazy
from django.http import JsonResponse

def health_check(request):
    return JsonResponse({"status": "healthy", "service": "gestionale-agenzia"})

urlpatterns = [
    path('health/', health_check, name='health_check'),
    path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='app/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='logout_complete'), name='logout'),
    path('logout/complete/', TemplateView.as_view(template_name='app/logout.html'), name='logout_complete'),
    path('', include('app.urls')),
]