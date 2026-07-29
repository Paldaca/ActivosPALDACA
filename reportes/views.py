from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from datetime import datetime
from activos.models import Activo
from .utils import generar_pdf, formatear_fecha, obtener_filtros_aplicados
from activos.decorators import requiere_modulo_paldaca

@requiere_modulo_paldaca
def generar_reporte_activos(request):
    """
    Genera un reporte PDF con todos los activos filtrados
    """
    try:
        # Obtener filtros de la request
        filtros = obtener_filtros_aplicados(request)
        
        # Construir queryset con los mismos filtros que la vista de activos
        queryset = Activo.objects.select_related(
            'subcategoria__categoria', 
            'ubicacion', 
            'usuario_asignado'
        ).all()
        
        # Aplicar filtros
        categoria_id = request.GET.get('categoria', '')
        subcategoria_id = request.GET.get('subcategoria', '')
        ubicacion_id = request.GET.get('ubicacion', '')
        estado = request.GET.get('estado', '')
        usuario_asignado_id = request.GET.get('usuario_asignado', '')
        buscar = request.GET.get('buscar', '')
        
        if categoria_id:
            queryset = queryset.filter(subcategoria__categoria_id=categoria_id)
        if subcategoria_id:
            queryset = queryset.filter(subcategoria_id=subcategoria_id)
        if ubicacion_id:
            queryset = queryset.filter(ubicacion_id=ubicacion_id)
        if estado:
            queryset = queryset.filter(estado=estado)
        # Mismo criterio que los chips del listado: el PDF debe reflejar
        # exactamente lo que el usuario está viendo en pantalla.
        asignacion = request.GET.get('asignacion', '')
        if asignacion == 'libre':
            queryset = queryset.filter(usuario_asignado__isnull=True)
        elif asignacion == 'asignado':
            queryset = queryset.filter(usuario_asignado__isnull=False)
        if usuario_asignado_id:
            queryset = queryset.filter(usuario_asignado_id=usuario_asignado_id)
        if buscar:
            queryset = queryset.filter(
                Q(codigo_inventario__icontains=buscar) |
                Q(marca__icontains=buscar) |
                Q(modelo__icontains=buscar) |
                Q(numero_serial__icontains=buscar) |
                Q(usuario_asignado__first_name__icontains=buscar) |
                Q(usuario_asignado__last_name__icontains=buscar) |
                Q(ubicacion__nombre__icontains=buscar)
            )
        
        # Preparar contexto para el template
        context = {
            'activos': queryset,
            'fecha_generacion': formatear_fecha(timezone.now().date()),
            'filtros_aplicados': ', '.join([f"{k}: {v}" for k, v in filtros.items()]) if filtros else None,
        }
        
        # Generar nombre del archivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"reporte_activos_{timestamp}.pdf"
        
        
        # Generar y retornar el PDF
        return generar_pdf('reportes/reporte_activos.html', context, filename)
        
    except Exception as e:
        messages.error(request, f'Error al generar el reporte: {str(e)}')
        return redirect('activos:activo-list')


@requiere_modulo_paldaca
def generar_nota_entrega(request):
    """
    Genera una nota de entrega PDF con los activos seleccionados
    """
    try:
        # Obtener IDs de activos seleccionados
        activos_ids = request.POST.getlist('activos_seleccionados')
        
        if not activos_ids:
            messages.error(request, 'Debe seleccionar al menos un activo para generar la nota de entrega.')
            return redirect('activos:activo-list')
        
        # Obtener los activos seleccionados
        activos = Activo.objects.select_related(
            'subcategoria__categoria', 
            'ubicacion', 
            'usuario_asignado'
        ).filter(id__in=activos_ids)
        
        # Obtener datos adicionales del formulario
        responsable_entrega = request.POST.get('responsable_entrega', '')
        observaciones = request.POST.get('observaciones', '')
        
        # Preparar contexto para el template
        context = {
            'activos': activos,
            'fecha_entrega': formatear_fecha(timezone.now().date()),
            'responsable_entrega': responsable_entrega,
            'observaciones': observaciones,
        }
        
        # Generar nombre del archivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"nota_entrega_{timestamp}.pdf"
        
        
        # Generar y retornar el PDF
        return generar_pdf('reportes/nota_entrega.html', context, filename)
        
    except Exception as e:
        messages.error(request, f'Error al generar la nota de entrega: {str(e)}')
        return redirect('activos:activo-list')

