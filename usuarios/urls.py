from django.urls import path
from . import views

app_name = 'usuarios'

urlpatterns = [
    # Vista principal con buscador
    path('', views.UsuarioSearchView.as_view(), name='usuario-search'),

    # Perfil de usuario
    path('<int:pk>/perfil/', views.UsuarioProfileView.as_view(), name='usuario-profile'),

    # Alta y edición
    path('crear/', views.UsuarioCreateView.as_view(), name='usuario-create'),
    path('<int:pk>/editar/', views.UsuarioUpdateView.as_view(), name='usuario-update'),

    # Baja lógica: core_usuario es la identidad SSO compartida y no se elimina.
    path('<int:pk>/estado/', views.cambiar_estado_usuario, name='usuario-estado'),
]
