from django.urls import path
from . import views

app_name = 'usuarios'

# Solo consulta: los empleados se gestionan en Nomina (ver usuarios/views.py).
urlpatterns = [
    path('', views.UsuarioSearchView.as_view(), name='usuario-search'),
    path('<int:pk>/perfil/', views.UsuarioProfileView.as_view(), name='usuario-profile'),
]
