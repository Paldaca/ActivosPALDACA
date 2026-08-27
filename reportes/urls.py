from django.urls import path
from . import views

app_name = 'reportes'

urlpatterns = [
    # Reporte general de activos
    path('activos/', views.generar_reporte_activos, name='reporte-activos'),
    path('activos/excel/', views.exportar_activos_excel, name='reporte-activos-excel'),

    # Etiquetas QR (hoja Avery 5160 sobre Letter)
    path('etiquetas/', views.imprimir_etiquetas, name='etiquetas-pdf'),

    # Nota de entrega
    path('nota-entrega/', views.generar_nota_entrega, name='nota-entrega'),
]
