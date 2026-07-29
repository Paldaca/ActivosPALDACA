from django.urls import path
from . import views

app_name = 'activos'

urlpatterns = [
    # URLs de Categoría
    path('categorias/', views.CategoriaListView.as_view(), name='categoria-list'),
    path('categorias/crear/', views.CategoriaCreateView.as_view(), name='categoria-create'),
    path('categorias/<int:pk>/editar/', views.CategoriaUpdateView.as_view(), name='categoria-update'),
    path('categorias/<int:pk>/eliminar/', views.CategoriaDeleteView.as_view(), name='categoria-delete'),
    
    # URLs de SubCategoría
    path('subcategorias/', views.SubCategoriaListView.as_view(), name='subcategoria-list'),
    path('subcategorias/crear/', views.SubCategoriaCreateView.as_view(), name='subcategoria-create'),
    path('subcategorias/<int:pk>/editar/', views.SubCategoriaUpdateView.as_view(), name='subcategoria-update'),
    path('subcategorias/<int:pk>/eliminar/', views.SubCategoriaDeleteView.as_view(), name='subcategoria-delete'),
    
    # URLs de Ubicación
    path('ubicaciones/', views.UbicacionListView.as_view(), name='ubicacion-list'),
    path('ubicaciones/crear/', views.UbicacionCreateView.as_view(), name='ubicacion-create'),
    path('ubicaciones/<int:pk>/editar/', views.UbicacionUpdateView.as_view(), name='ubicacion-update'),
    path('ubicaciones/<int:pk>/eliminar/', views.UbicacionDeleteView.as_view(), name='ubicacion-delete'),
    
    # URLs de Activo
    path('', views.ActivoListView.as_view(), name='activo-list'),
    path('<int:pk>/', views.ActivoDetailView.as_view(), name='activo-detail'),
    path('crear/', views.ActivoCreateView.as_view(), name='activo-create'),
    path('<int:pk>/editar/', views.ActivoUpdateView.as_view(), name='activo-update'),
    path('<int:pk>/eliminar/', views.ActivoDeleteView.as_view(), name='activo-delete'),
    
    # URLs de acciones especiales
    path('<int:pk>/reasignar/', views.reasignar_activo, name='activo-reasignar'),
    path('<int:pk>/reubicar/', views.reubicar_activo, name='activo-reubicar'),
    path('<int:pk>/historial/', views.ActivoHistorialView.as_view(), name='activo-historial'),

    # Acciones en lote (reasignar / reubicar varios activos a la vez)
    path('acciones-masivas/', views.acciones_masivas, name='activo-acciones-masivas'),

    # Alta express de catálogo desde el formulario de activos (JSON)
    path('catalogo/<slug:tipo>/rapido/', views.crear_rapido, name='crear-rapido'),
]

