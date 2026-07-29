from datetime import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.contrib import messages
from django.db.models import Q, Sum, Count
from django.http import HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from activos.models import Activo
from activos.decorators import ModuloActivoRequiredMixin, requiere_modulo_paldaca
from .models import Mantenimiento
from .forms import MantenimientoForm, MantenimientoFilterForm


def _url_de_retorno(request, url, fallback='mantenimientos:mantenimiento-list'):
    """Valida el destino de vuelta para no convertirlo en un redirect abierto.

    Antes se usaba HTTP_REFERER sin comprobar, así que una página externa podía
    encadenar la acción y devolver al usuario a donde quisiera.
    """
    if url and url_has_allowed_host_and_scheme(
        url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return url
    return reverse(fallback)

class MantenimientoListView(ModuloActivoRequiredMixin, ListView):
    """Vista de lista de mantenimientos"""
    model = Mantenimiento
    template_name = 'mantenimientos/mantenimiento_list.html'
    context_object_name = 'mantenimientos'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related('activo__subcategoria__categoria', 'activo__ubicacion')
        
        # Filtros
        estado = self.request.GET.get('estado', '')
        activo_id = self.request.GET.get('activo', '')
        buscar = self.request.GET.get('buscar', '')
        mes = self.request.GET.get('mes', '')
        año = self.request.GET.get('año', '')
        
        if estado:
            queryset = queryset.filter(estado=estado)
        if activo_id:
            queryset = queryset.filter(activo_id=activo_id)
        if buscar:
            queryset = queryset.filter(
                Q(tecnico__icontains=buscar) |
                Q(descripcion__icontains=buscar) |
                Q(activo__codigo_inventario__icontains=buscar)
            )
        if mes:
            queryset = queryset.filter(fecha__month=mes)
        if año:
            queryset = queryset.filter(fecha__year=año)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = MantenimientoFilterForm(self.request.GET or None)

        EN_PROCESO = Mantenimiento.EstadoMantenimiento.EN_PROCESO
        FINALIZADO = Mantenimiento.EstadoMantenimiento.FINALIZADO

        # Un único agregado para todo el panel. Antes se llamaba a
        # get_queryset() seis veces y se lanzaban ~8 consultas por carga.
        resumen = self.get_queryset().aggregate(
            total=Count('id'),
            en_proceso=Count('id', filter=Q(estado=EN_PROCESO)),
            finalizados=Count('id', filter=Q(estado=FINALIZADO)),
            costo_en_proceso=Sum('costo', filter=Q(estado=EN_PROCESO)),
            costo_finalizado=Sum('costo', filter=Q(estado=FINALIZADO)),
        )
        resumen['costo_en_proceso'] = resumen['costo_en_proceso'] or 0
        resumen['costo_finalizado'] = resumen['costo_finalizado'] or 0
        resumen['costo_total'] = resumen['costo_en_proceso'] + resumen['costo_finalizado']

        context['resumen'] = resumen
        context['total_mantenimientos'] = resumen['total']
        context['mantenimientos_en_proceso'] = resumen['en_proceso']
        context['mantenimientos_finalizados'] = resumen['finalizados']
        context['costo_en_proceso'] = resumen['costo_en_proceso']
        context['costo_finalizado'] = resumen['costo_finalizado']
        context['costo_total'] = resumen['costo_total']

        # Gasto real (solo finalizados) del mes y del año en curso
        hoy = datetime.now()
        globales = Mantenimiento.objects.filter(estado=FINALIZADO).aggregate(
            mes=Sum('costo', filter=Q(fecha__month=hoy.month, fecha__year=hoy.year)),
            anio=Sum('costo', filter=Q(fecha__year=hoy.year)),
        )
        context['gastos_mes_actual'] = globales['mes'] or 0
        context['gastos_año_actual'] = globales['anio'] or 0
        context['total_gastado_periodo'] = resumen['costo_finalizado']

        context['hay_filtros'] = any(
            self.request.GET.get(k) for k in ('estado', 'activo', 'buscar', 'mes', 'año')
        )
        return context

class MantenimientoCreateView(ModuloActivoRequiredMixin, CreateView):
    """Vista para crear un nuevo mantenimiento"""
    model = Mantenimiento
    form_class = MantenimientoForm
    template_name = 'mantenimientos/mantenimiento_form.html'
    success_url = reverse_lazy('mantenimientos:mantenimiento-list')
    
    def get_initial(self):
        """Pre-cargar el activo si viene por parámetro"""
        initial = super().get_initial()
        activo_id = self.request.GET.get('activo_id')
        if activo_id:
            initial['activo'] = activo_id
        return initial
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        activo_id = self.request.GET.get('activo_id')
        if activo_id:
            context['activo'] = get_object_or_404(Activo, pk=activo_id)
        return context
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Mantenimiento registrado para {self.object.activo.codigo_inventario}.',
        )
        return response

    def get_success_url(self):
        """Vuelve a la ficha del activo cuando se entró desde ella."""
        activo_id = self.request.GET.get('activo_id')
        if activo_id:
            return reverse('activos:activo-detail', kwargs={'pk': activo_id})
        return reverse('mantenimientos:mantenimiento-detail', kwargs={'pk': self.object.pk})


class MantenimientoUpdateView(ModuloActivoRequiredMixin, UpdateView):
    """Vista para actualizar un mantenimiento"""
    model = Mantenimiento
    form_class = MantenimientoForm
    template_name = 'mantenimientos/mantenimiento_form.html'
    success_url = reverse_lazy('mantenimientos:mantenimiento-list')
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Mantenimiento actualizado correctamente.')
        return response

    def get_success_url(self):
        return reverse('mantenimientos:mantenimiento-detail', kwargs={'pk': self.object.pk})

class MantenimientoDetailView(ModuloActivoRequiredMixin, DetailView):
    """Vista de detalle de un mantenimiento"""
    model = Mantenimiento
    template_name = 'mantenimientos/mantenimiento_detail.html'
    context_object_name = 'mantenimiento'
    
    def get_queryset(self):
        return super().get_queryset().select_related('activo__subcategoria__categoria', 'activo__ubicacion', 'activo__usuario_asignado')

@require_POST
@requiere_modulo_paldaca
def finalizar_mantenimiento(request, pk):
    """Cierra un mantenimiento en un clic.

    Es POST, no GET: cambia el estado del mantenimiento y puede devolver el
    activo a servicio. Como GET, cualquier precarga del navegador o un
    rastreador podía dispararlo, y no pasaba por CSRF.
    """
    mantenimiento = get_object_or_404(
        Mantenimiento.objects.select_related('activo'), pk=pk
    )
    destino = _url_de_retorno(request, request.POST.get('next'))

    if mantenimiento.estado == Mantenimiento.EstadoMantenimiento.EN_PROCESO:
        mantenimiento.estado = Mantenimiento.EstadoMantenimiento.FINALIZADO
        mantenimiento.save()
        messages.success(
            request,
            f'Mantenimiento de {mantenimiento.activo.codigo_inventario} finalizado. '
            f'Costo aplicado: ${mantenimiento.costo}.',
        )
    else:
        messages.warning(request, 'Este mantenimiento ya estaba finalizado.')

    return HttpResponseRedirect(destino)