from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView
)
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from .models import (
    SIN_RESPONSABLE,
    Activo,
    Categoria,
    EmpleadoPortal,
    HistorialMovimiento,
    SubCategoria,
    Ubicacion,
)
from .forms import (
    CategoriaForm, SubCategoriaForm, UbicacionForm,
    ActivoForm, ActivoFilterForm, ReasignarActivoForm, ReubicarActivoForm,
    empleados_asignables, etiqueta_empleado,
)
from .decorators import (
    AdminActivoRequiredMixin,
    ModuloActivoRequiredMixin,
    requiere_admin_activo,
    requiere_modulo_paldaca,
)
from .services.avisos import (
    avisar_activo_baja,
    avisar_activo_creado,
    avisar_activos_asignados,
    avisar_activos_desasignados,
)


def _url_de_retorno(request, url, fallback='activos:activo-list'):
    """Valida el `next` recibido para no convertirlo en un redirect abierto."""
    if url and url_has_allowed_host_and_scheme(
        url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return url
    return reverse(fallback)


def _url_con_constancia(url, ids):
    """Append ?constancia=1,2,3 keeping any filters already in the URL."""
    if not ids:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["constancia"] = ",".join(str(pk) for pk in ids)
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query),
        parts.fragment,
    ))


def _aplicar_planilla_historial(activo, usuario_nuevo, entrega_usuario, movimiento):
    """Store an audit snapshot on the movement when someone receives the asset."""
    if not usuario_nuevo or movimiento is None:
        return
    from reportes.services.asignacion import guardar_planilla_en_historial

    guardar_planilla_en_historial(
        activo,
        entrega_usuario=entrega_usuario,
        movimiento=movimiento,
    )


class SinPaginaDeBorradoMixin:
    """El borrado se confirma en un modal, no en una pantalla aparte.

    Evita una navegación completa (y su vuelta atrás) para una acción de un
    solo clic. La vista queda como endpoint POST; un GET directo — un enlace
    viejo, un marcador — devuelve al usuario a donde tiene sentido seguir
    trabajando en lugar de dejarlo en una página huérfana.
    """

    def get(self, request, *args, **kwargs):
        return redirect(self.get_redireccion_get())

    def get_redireccion_get(self):
        return self.success_url


def _resumen_inventario():
    """KPIs del encabezado, en una sola consulta.

    Los estados que ve el usuario se derivan de (estado, responsable):
    el modelo solo guarda AC / IN / EM. Un activo pendiente de vincular
    (fase 1, `usuario_legacy`) sigue contando como asignado.
    """
    return Activo.objects.aggregate(
        total=Count('id'),
        disponibles=Count('id', filter=Q(estado='AC') & SIN_RESPONSABLE),
        asignados=Count('id', filter=Q(estado='AC') & ~SIN_RESPONSABLE),
        mantenimiento=Count('id', filter=Q(estado='EM')),
        baja=Count('id', filter=Q(estado='IN')),
    )

# ============== VISTAS DE CATEGORÍA ==============
class CategoriaListView(AdminActivoRequiredMixin, ListView):
    model = Categoria
    template_name = 'activos/categoria/list.html'
    context_object_name = 'categorias'
    paginate_by = 20

    def get_queryset(self):
        # Contadores por anotación: evita una consulta por fila en la plantilla.
        # `order_by` explícito porque annotate() descarta el Meta.ordering y
        # dejaría la paginación sin un orden estable.
        return super().get_queryset().annotate(
            num_subcategorias=Count('subcategorias', distinct=True),
            num_activos=Count('subcategorias__activos', distinct=True),
        ).order_by('nombre')


class CategoriaCreateView(AdminActivoRequiredMixin, CreateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = 'activos/categoria/form.html'
    success_url = reverse_lazy('activos:categoria-list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Categoría creada exitosamente.')
        return super().form_valid(form)


class CategoriaUpdateView(AdminActivoRequiredMixin, UpdateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = 'activos/categoria/form.html'
    success_url = reverse_lazy('activos:categoria-list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Categoría actualizada exitosamente.')
        return super().form_valid(form)


class CategoriaDeleteView(SinPaginaDeBorradoMixin, AdminActivoRequiredMixin, DeleteView):
    model = Categoria
    success_url = reverse_lazy('activos:categoria-list')

    # Desde Django 4.0 `DeleteView.post()` llama a `form_valid()`, no a
    # `delete()`. La guarda vive aquí para que realmente se ejecute; de lo
    # contrario el PROTECT del modelo devolvería un 500.
    def form_valid(self, form):
        if self.object.subcategorias.exists():
            messages.error(
                self.request,
                f'No se puede eliminar la categoría "{self.object.nombre}" '
                'porque tiene subcategorías asociadas.',
            )
            return redirect('activos:categoria-list')

        messages.success(self.request, 'Categoría eliminada exitosamente.')
        return super().form_valid(form)


# ============== VISTAS DE SUBCATEGORÍA ==============

class SubCategoriaListView(AdminActivoRequiredMixin, ListView):
    model = SubCategoria
    template_name = 'activos/subcategoria/list.html'
    context_object_name = 'subcategorias'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related('categoria').annotate(
            num_activos=Count('activos', distinct=True),
        ).order_by('categoria__nombre', 'nombre')
        categoria_id = self.request.GET.get('categoria')
        if categoria_id:
            queryset = queryset.filter(categoria_id=categoria_id)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categorias'] = Categoria.objects.all()
        return context


class SubCategoriaCreateView(AdminActivoRequiredMixin, CreateView):
    model = SubCategoria
    form_class = SubCategoriaForm
    template_name = 'activos/subcategoria/form.html'
    success_url = reverse_lazy('activos:subcategoria-list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Subcategoría creada exitosamente.')
        return super().form_valid(form)


class SubCategoriaUpdateView(AdminActivoRequiredMixin, UpdateView):
    model = SubCategoria
    form_class = SubCategoriaForm
    template_name = 'activos/subcategoria/form.html'
    success_url = reverse_lazy('activos:subcategoria-list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Subcategoría actualizada exitosamente.')
        return super().form_valid(form)


class SubCategoriaDeleteView(SinPaginaDeBorradoMixin, AdminActivoRequiredMixin, DeleteView):
    model = SubCategoria
    success_url = reverse_lazy('activos:subcategoria-list')
    
    def form_valid(self, form):
        if self.object.activos.exists():
            messages.error(
                self.request,
                f'No se puede eliminar la subcategoría "{self.object}" '
                'porque tiene activos asociados.',
            )
            return redirect('activos:subcategoria-list')

        messages.success(self.request, 'Subcategoría eliminada exitosamente.')
        return super().form_valid(form)


# ============== VISTAS DE UBICACIÓN ==============

class UbicacionListView(AdminActivoRequiredMixin, ListView):
    model = Ubicacion
    template_name = 'activos/ubicacion/list.html'
    context_object_name = 'ubicaciones'
    paginate_by = 20

    def get_queryset(self):
        return super().get_queryset().annotate(
            num_activos=Count('activos', distinct=True),
        ).order_by('nombre')


class UbicacionCreateView(AdminActivoRequiredMixin, CreateView):
    model = Ubicacion
    form_class = UbicacionForm
    template_name = 'activos/ubicacion/form.html'
    success_url = reverse_lazy('activos:ubicacion-list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Ubicación creada exitosamente.')
        return super().form_valid(form)


class UbicacionUpdateView(AdminActivoRequiredMixin, UpdateView):
    model = Ubicacion
    form_class = UbicacionForm
    template_name = 'activos/ubicacion/form.html'
    success_url = reverse_lazy('activos:ubicacion-list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Ubicación actualizada exitosamente.')
        return super().form_valid(form)


class UbicacionDeleteView(SinPaginaDeBorradoMixin, AdminActivoRequiredMixin, DeleteView):
    model = Ubicacion
    success_url = reverse_lazy('activos:ubicacion-list')
    
    def form_valid(self, form):
        if self.object.activos.exists():
            messages.error(
                self.request,
                f'No se puede eliminar la ubicación "{self.object.nombre}" '
                'porque tiene activos asociados.',
            )
            return redirect('activos:ubicacion-list')

        messages.success(self.request, 'Ubicación eliminada exitosamente.')
        return super().form_valid(form)


# ============== VISTAS DE ACTIVO ==============

class ActivoListView(AdminActivoRequiredMixin, ListView):
    model = Activo
    template_name = 'activos/activo/list.html'
    context_object_name = 'activos'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'subcategoria__categoria', 'ubicacion', 'responsable', 'usuario_legacy'
        )
        
        # Filtros
        categoria_id = self.request.GET.get('categoria')
        subcategoria_id = self.request.GET.get('subcategoria')
        ubicacion_id = self.request.GET.get('ubicacion')
        estado = self.request.GET.get('estado')
        asignacion = self.request.GET.get('asignacion')
        responsable_id = self.request.GET.get('responsable')
        buscar = self.request.GET.get('buscar')

        if categoria_id:
            queryset = queryset.filter(subcategoria__categoria_id=categoria_id)
        if subcategoria_id:
            queryset = queryset.filter(subcategoria_id=subcategoria_id)
        if ubicacion_id:
            queryset = queryset.filter(ubicacion_id=ubicacion_id)
        if estado:
            queryset = queryset.filter(estado=estado)
        # Distingue "Disponible" (sin responsable) de "Asignado" sin tocar el modelo.
        if asignacion == 'libre':
            queryset = queryset.filter(SIN_RESPONSABLE)
        elif asignacion == 'asignado':
            queryset = queryset.exclude(SIN_RESPONSABLE)
        if responsable_id:
            queryset = queryset.filter(responsable_id=responsable_id)
        if buscar:
            # Buscar también por persona: "¿qué tiene asignado Ana?" es una
            # pregunta diaria y antes obligaba a recorrer la tabla a mano.
            queryset = queryset.filter(
                Q(codigo_inventario__icontains=buscar) |
                Q(marca__icontains=buscar) |
                Q(modelo__icontains=buscar) |
                Q(numero_serial__icontains=buscar) |
                Q(responsable__nombres__icontains=buscar) |
                Q(responsable__apellidos__icontains=buscar) |
                Q(responsable__cedula__icontains=buscar) |
                Q(usuario_legacy__first_name__icontains=buscar) |
                Q(usuario_legacy__last_name__icontains=buscar) |
                Q(ubicacion__nombre__icontains=buscar)
            )

        return queryset

    def _filtros_activos(self):
        """Filtros vigentes, ya resueltos a etiqueta legible.

        Alimenta las píldoras "quitar filtro" del listado: el usuario siempre
        ve por qué está viendo lo que ve, y puede deshacerlo en un clic.
        """
        get = self.request.GET
        pills = []

        def agregar(param, etiqueta, valor):
            if valor:
                pills.append({'param': param, 'etiqueta': etiqueta, 'valor': valor})

        agregar('buscar', 'Búsqueda', get.get('buscar'))

        if get.get('categoria'):
            obj = Categoria.objects.filter(pk=get['categoria']).first()
            agregar('categoria', 'Categoría', obj.nombre if obj else None)

        if get.get('subcategoria'):
            obj = SubCategoria.objects.filter(pk=get['subcategoria']).first()
            agregar('subcategoria', 'Subcategoría', obj.nombre if obj else None)

        if get.get('ubicacion'):
            obj = Ubicacion.objects.filter(pk=get['ubicacion']).first()
            agregar('ubicacion', 'Ubicación', obj.nombre if obj else None)

        if get.get('responsable'):
            obj = EmpleadoPortal.objects.filter(pk=get['responsable']).first()
            self._responsable_filtro = obj
            agregar('responsable', 'Responsable', obj.nombre_completo if obj else None)

        return pills

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = ActivoFilterForm(self.request.GET or None)

        # Resultados de la consulta actual (ya paginada arriba)
        paginator = context.get('paginator')
        context['total_activos'] = (
            paginator.count if paginator else self.get_queryset().count()
        )

        # KPIs sobre el inventario completo: el encabezado responde
        # "¿cómo está todo?", no "¿cómo está lo que filtré?".
        context['resumen'] = _resumen_inventario()
        context['filtros_activos'] = self._filtros_activos()
        context['hay_filtros'] = bool(context['filtros_activos'])

        # La lista completa de empleados se carga bajo demanda desde el drawer.
        context['responsable_filtro'] = getattr(self, '_responsable_filtro', None)
        context['ubicaciones'] = Ubicacion.objects.all()

        # Distribución (top 5 con activos)
        context['activos_por_categoria'] = Categoria.objects.annotate(
            total_activos=Count('subcategorias__activos')
        ).filter(total_activos__gt=0).order_by('-total_activos')[:5]

        context['activos_por_ubicacion'] = Ubicacion.objects.annotate(
            total_activos=Count('activos')
        ).filter(total_activos__gt=0).order_by('-total_activos')[:5]

        context['total_categorias'] = Categoria.objects.count()
        context['total_ubicaciones'] = Ubicacion.objects.count()
        context['total_activos_sistema'] = context['resumen']['total']

        return context


@require_GET
@requiere_admin_activo
def buscar_empleados_asignables(request):
    """Empleados de Nomina activos (tabla portal_empleado), para el combo de
    Responsable. Cada palabra debe coincidir con nombre, apellido, cedula o cargo."""
    query = (request.GET.get('q') or '').strip()[:80]
    try:
        page = max(1, int(request.GET.get('page', '1')))
    except ValueError:
        page = 1
    page_size = 20
    queryset = empleados_asignables()
    for palabra in query.split()[:5]:
        queryset = queryset.filter(
            Q(nombres__icontains=palabra)
            | Q(apellidos__icontains=palabra)
            | Q(cedula__icontains=palabra)
            | Q(cargo__icontains=palabra)
        )
    start = (page - 1) * page_size
    rows = list(queryset[start:start + page_size + 1])
    return JsonResponse({
        'results': [
            {'id': empleado.pk, 'text': etiqueta_empleado(empleado)}
            for empleado in rows[:page_size]
        ],
        'has_more': len(rows) > page_size,
    })


class ActivoDetailView(AdminActivoRequiredMixin, DetailView):
    model = Activo
    template_name = 'activos/activo/detail.html'
    context_object_name = 'activo'

    def get_queryset(self):
        return super().get_queryset().select_related(
            'subcategoria__categoria', 'ubicacion', 'responsable', 'usuario_legacy'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Últimos movimientos en la propia ficha: el historial completo sigue
        # teniendo su vista, pero lo habitual es querer ver los 5 recientes.
        context['movimientos_recientes'] = (
            self.object.historial_movimientos
            .select_related('usuario')
            .order_by('-fecha_movimiento')[:6]
        )
        context['total_movimientos'] = self.object.historial_movimientos.count()
        context['mantenimientos_recientes'] = list(
            self.object.mantenimientos.order_by('-fecha')[:10]
        )
        context['resumen_mantenimientos'] = (
            self.object.mantenimientos.aggregate(
                total=Count('id'),
                costo_total=Sum('costo'),
            )
        )
        context['ubicaciones'] = Ubicacion.objects.all()
        from activos.models import EtiquetaQR

        context['etiqueta_vigente'] = (
            self.object.etiquetas
            .filter(estado=EtiquetaQR.EstadoEtiqueta.VINCULADA)
            .order_by('-fecha_vinculacion')
            .first()
        )
        return context


class ActivoFormContextMixin:
    """Catálogos que necesita el alta express dentro del formulario de activos."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categorias_catalogo'] = Categoria.objects.all()
        return context


class ActivoCreateView(ActivoFormContextMixin, AdminActivoRequiredMixin, CreateView):
    model = Activo
    form_class = ActivoForm
    template_name = 'activos/activo/form.html'
    success_url = reverse_lazy('activos:activo-list')

    def form_valid(self, form):
        self.object = form.save()
        avisar_activo_creado(self.object, self.request.user)
        messages.success(
            self.request,
            f'Activo {self.object.codigo_inventario} creado exitosamente.',
        )

        guardar_y_nuevo = 'guardar_y_nuevo' in self.request.POST
        generar_qr = bool(self.request.POST.get('generar_etiqueta_qr'))
        etiqueta_pk = None

        if generar_qr:
            from django.core.exceptions import ValidationError

            from activos.services.etiquetas import crear_etiqueta_vinculada_para_activo

            try:
                etiqueta, creada = crear_etiqueta_vinculada_para_activo(
                    self.object,
                    creada_por=self.request.user,
                )
            except ValidationError as exc:
                messages.error(self.request, "; ".join(exc.messages))
                return redirect('activos:activo-detail', pk=self.object.pk)

            etiqueta_pk = etiqueta.pk
            if creada:
                messages.info(
                    self.request,
                    'Etiqueta QR generada. El PDF se abre en otra pestaña.',
                )
            else:
                messages.info(
                    self.request,
                    'Este activo ya tenía etiqueta vigente; se reimprime en otra pestaña.',
                )

        if guardar_y_nuevo:
            destino = reverse('activos:activo-create')
        else:
            destino = reverse('activos:activo-detail', kwargs={'pk': self.object.pk})

        if etiqueta_pk is not None:
            destino = f'{destino}?qr_pdf={etiqueta_pk}'
        return redirect(destino)


class ActivoUpdateView(ActivoFormContextMixin, AdminActivoRequiredMixin, UpdateView):
    model = Activo
    form_class = ActivoForm
    template_name = 'activos/activo/form.html'
    success_url = reverse_lazy('activos:activo-list')

    def form_valid(self, form):
        pk = self.object.pk
        activo_original = Activo.objects.select_related(
            'ubicacion', 'responsable', 'usuario_legacy'
        ).get(pk=pk)
        response = super().form_valid(form)
        activo_actualizado = self.object
        _registrar_reubicacion_en_historial(
            activo_actualizado,
            activo_original.ubicacion,
            activo_actualizado.ubicacion,
            self.request.user,
        )
        usuario_anterior = activo_original.persona_responsable
        movimiento = _registrar_reasignacion_en_historial(
            activo_actualizado,
            usuario_anterior,
            activo_actualizado.persona_responsable,
            self.request.user,
        )
        if (
            activo_actualizado.estado == Activo.EstadoActivo.INACTIVO
            and activo_original.estado != Activo.EstadoActivo.INACTIVO
        ):
            avisar_activo_baja(activo_actualizado, self.request.user)
        usuario_nuevo = activo_actualizado.responsable
        if movimiento and usuario_anterior:
            avisar_activos_desasignados([activo_actualizado], usuario_anterior, self.request.user)
        if movimiento and usuario_nuevo:
            avisar_activos_asignados([activo_actualizado], usuario_nuevo, self.request.user)
            try:
                _aplicar_planilla_historial(
                    activo_actualizado,
                    usuario_nuevo,
                    self.request.user,
                    movimiento,
                )
            except Exception as exc:
                messages.error(
                    self.request,
                    f"Se guardó el cambio, pero no se pudo archivar la planilla: {exc}",
                )
            else:
                messages.success(
                    self.request, 'Activo actualizado exitosamente.',
                )
                return redirect(_url_con_constancia(
                    reverse('activos:activo-detail', kwargs={'pk': pk}),
                    [pk],
                ))
        messages.success(self.request, 'Activo actualizado exitosamente.')
        return response


class ActivoDeleteView(SinPaginaDeBorradoMixin, AdminActivoRequiredMixin, DeleteView):
    model = Activo
    success_url = reverse_lazy('activos:activo-list')

    def get_queryset(self):
        return super().get_queryset().select_related(
            'subcategoria__categoria', 'ubicacion', 'responsable', 'usuario_legacy'
        )

    def get_redireccion_get(self):
        # Un GET aquí suele ser un enlace antiguo: se devuelve a la ficha, que
        # es donde vive el botón real de eliminar.
        return reverse('activos:activo-detail', kwargs={'pk': self.kwargs['pk']})

    def form_valid(self, form):
        # Textos y payload se arman ahora, con la fila todavía en pie
        # (BR-ACT-12: el historial se borra en cascada al eliminar).
        avisar_activo_baja(self.object, self.request.user, eliminado=True)
        messages.success(
            self.request,
            f'Activo {self.object.codigo_inventario} eliminado exitosamente.',
        )
        return super().form_valid(form)


def _registrar_reubicacion_en_historial(activo, ubicacion_anterior, ubicacion_nueva, usuario):
    """Si cambió la ubicación, registra una entrada de tipo reubicación (misma semántica que reubicar_activo)."""
    if (ubicacion_anterior.id if ubicacion_anterior else None) == (
        ubicacion_nueva.id if ubicacion_nueva else None
    ):
        return
    valor_anterior = ubicacion_anterior.nombre if ubicacion_anterior else 'Sin ubicación'
    valor_nuevo = ubicacion_nueva.nombre if ubicacion_nueva else 'Sin ubicación'
    HistorialMovimiento.objects.create(
        activo=activo,
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.REUBICACION,
        descripcion=f"Reubicación: {valor_anterior} -> {valor_nuevo}",
        campo_modificado='ubicacion',
        valor_anterior=valor_anterior,
        valor_nuevo=valor_nuevo,
        usuario=usuario if usuario and usuario.is_authenticated else None,
    )


def _misma_persona(a, b):
    """Compara responsables que pueden ser de dos tablas distintas en la fase 1
    (empleado o cuenta anterior sin vincular): mismo pk no basta."""
    if a is None or b is None:
        return a is b
    return type(a) is type(b) and a.pk == b.pk


def _registrar_reasignacion_en_historial(activo, usuario_anterior, usuario_nuevo, usuario):
    """Si cambió el responsable, registra reasignación (misma semántica que reasignar_activo)."""
    if _misma_persona(usuario_anterior, usuario_nuevo):
        return
    # El historial también respeta la regla: "Nombre Apellido", nunca username.
    valor_anterior = _nombre(usuario_anterior)
    valor_nuevo = _nombre(usuario_nuevo)
    return HistorialMovimiento.objects.create(
        activo=activo,
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.REASIGNACION,
        descripcion=f"Reasignación de responsable: {valor_anterior} -> {valor_nuevo}",
        campo_modificado='responsable',
        valor_anterior=valor_anterior,
        valor_nuevo=valor_nuevo,
        usuario=usuario if usuario and usuario.is_authenticated else None,
    )


# ============== VISTAS ESPECIALES DE ACTIVO ==============

@requiere_admin_activo
def reasignar_activo(request, pk):
    """Reasigna un activo a otra persona.

    Sirve a dos interfaces con el mismo endpoint: el drawer lateral (que envía
    `next` para volver al listado sin perder filtros) y la página completa, que
    queda como respaldo accesible y sin JavaScript.
    """
    activo = get_object_or_404(
        Activo.objects.select_related('subcategoria__categoria', 'ubicacion', 'responsable', 'usuario_legacy'),
        pk=pk,
    )
    destino = _url_de_retorno(
        request,
        request.POST.get('next') or request.GET.get('next'),
        fallback='activos:activo-list',
    )

    if request.method == 'POST':
        # Guardamos estado original desde BD antes de que el ModelForm
        # muta la instancia en memoria durante is_valid().
        activo_original = Activo.objects.select_related(
            'responsable', 'usuario_legacy'
        ).get(pk=pk)
        form = ReasignarActivoForm(request.POST, instance=activo)
        if form.is_valid():
            usuario_anterior = activo_original.persona_responsable
            # Reasignar es una decision explicita: aunque se elija "sin
            # asignar", cierra la asignacion anterior pendiente de vincular.
            form.instance.usuario_legacy = None
            activo_actualizado = form.save()
            usuario_nuevo = activo_actualizado.responsable

            movimiento = _registrar_reasignacion_en_historial(
                activo_actualizado,
                usuario_anterior,
                usuario_nuevo,
                request.user,
            )
            if usuario_anterior and movimiento is not None:
                avisar_activos_desasignados([activo_actualizado], usuario_anterior, request.user)
            if usuario_nuevo and movimiento is not None:
                avisar_activos_asignados([activo_actualizado], usuario_nuevo, request.user)
                try:
                    _aplicar_planilla_historial(
                        activo_actualizado,
                        usuario_nuevo,
                        request.user,
                        movimiento,
                    )
                except Exception as exc:
                    messages.error(
                        request,
                        f"Se reasignó el equipo, pero no se pudo archivar la planilla: {exc}",
                    )

            messages.success(
                request,
                f'{activo.codigo_inventario} · {_nombre(usuario_anterior)} → {_nombre(usuario_nuevo)}',
            )
            if request.POST.get('next'):
                destino_final = destino
            else:
                destino_final = reverse(
                    'activos:activo-detail', kwargs={'pk': pk}
                )
            if usuario_nuevo and movimiento is not None:
                destino_final = _url_con_constancia(
                    destino_final, [pk]
                )
            return redirect(destino_final)
    else:
        form = ReasignarActivoForm(instance=activo)

    return render(request, 'activos/activo/reasignar.html', {
        'form': form,
        'activo': activo,
        'next': destino,
    })


@requiere_admin_activo
def reubicar_activo(request, pk):
    """Reubica un activo. Mismo contrato que `reasignar_activo`."""
    activo = get_object_or_404(
        Activo.objects.select_related('subcategoria__categoria', 'ubicacion', 'responsable', 'usuario_legacy'),
        pk=pk,
    )
    destino = _url_de_retorno(
        request,
        request.POST.get('next') or request.GET.get('next'),
        fallback='activos:activo-list',
    )

    if request.method == 'POST':
        # Guardamos estado original desde BD antes de que el ModelForm
        # muta la instancia en memoria durante is_valid().
        activo_original = Activo.objects.select_related('ubicacion').get(pk=pk)
        form = ReubicarActivoForm(request.POST, instance=activo)
        if form.is_valid():
            ubicacion_anterior = activo_original.ubicacion
            activo_actualizado = form.save()
            ubicacion_nueva = activo_actualizado.ubicacion

            _registrar_reubicacion_en_historial(
                activo_actualizado,
                ubicacion_anterior,
                ubicacion_nueva,
                request.user,
            )

            messages.success(
                request,
                f'{activo.codigo_inventario} · {ubicacion_anterior} → {ubicacion_nueva}',
            )
            if request.POST.get('next'):
                return redirect(destino)
            return redirect('activos:activo-detail', pk=pk)
    else:
        form = ReubicarActivoForm(instance=activo)

    return render(request, 'activos/activo/reubicar.html', {
        'form': form,
        'activo': activo,
        'ubicaciones': Ubicacion.objects.all(),
        'next': destino,
    })


def _nombre(usuario):
    """Nombre y Apellido para los mensajes del sistema; nunca el username."""
    if not usuario:
        return 'Sin asignar'
    return (usuario.get_full_name() or '').strip() or usuario.username


@require_POST
@requiere_admin_activo
def crear_rapido(request, tipo):
    """Alta express de catálogo sin abandonar el formulario de activos.

    Antes, registrar un equipo cuya subcategoría o ubicación no existía obligaba
    a abrir otra pestaña, crear el catálogo, volver y recargar. Aquí se resuelve
    en el sitio y la opción nueva queda seleccionada al instante.
    """
    nombre = (request.POST.get('nombre') or '').strip()
    if not nombre:
        return JsonResponse(
            {'ok': False, 'errores': {'nombre': ['Escribe un nombre.']}},
            status=400,
        )

    if tipo == 'ubicacion':
        obj, creado = Ubicacion.objects.get_or_create(nombre=nombre)
        return JsonResponse({'ok': True, 'id': obj.pk, 'texto': obj.nombre, 'creado': creado})

    if tipo == 'categoria':
        obj, creado = Categoria.objects.get_or_create(nombre=nombre)
        return JsonResponse({'ok': True, 'id': obj.pk, 'texto': obj.nombre, 'creado': creado})

    if tipo == 'subcategoria':
        # La categoría puede elegirse o escribirse en el mismo paso: así el
        # caso "no existe nada todavía" no se convierte en tres formularios.
        categoria = None
        categoria_nueva = (request.POST.get('categoria_nueva') or '').strip()
        if categoria_nueva:
            categoria, _ = Categoria.objects.get_or_create(nombre=categoria_nueva)
        elif request.POST.get('categoria'):
            categoria = Categoria.objects.filter(pk=request.POST['categoria']).first()

        if categoria is None:
            return JsonResponse(
                {'ok': False, 'errores': {'categoria': ['Elige o escribe una categoría.']}},
                status=400,
            )

        form = SubCategoriaForm({
            'nombre': nombre,
            'prefijo': request.POST.get('prefijo', ''),
            'categoria': categoria.pk,
        })
        if not form.is_valid():
            return JsonResponse({'ok': False, 'errores': form.errors}, status=400)

        obj = form.save()
        return JsonResponse({
            'ok': True,
            'id': obj.pk,
            'texto': str(obj),
            'creado': True,
            'categoria': {'id': categoria.pk, 'texto': categoria.nombre},
        })

    return JsonResponse(
        {'ok': False, 'errores': {'__all__': ['Tipo de catálogo no soportado.']}},
        status=400,
    )


@require_POST
@requiere_admin_activo
def acciones_masivas(request):
    """Reasigna o reubica varios activos en un solo envío.

    Es el mayor ahorro de clics del módulo: entregar 8 equipos a una persona
    pasa de 8 flujos completos a una selección + una confirmación.
    """
    accion = request.POST.get('accion')
    ids = request.POST.getlist('activos')
    destino_id = (request.POST.get('destino') or '').strip()
    volver = _url_de_retorno(request, request.POST.get('next'))

    if not ids:
        messages.warning(request, 'No seleccionaste ningún activo.')
        return redirect(volver)

    activos = Activo.objects.select_related(
        'responsable', 'usuario_legacy', 'ubicacion'
    ).filter(pk__in=ids)
    cambios = 0

    if accion == 'reasignar':
        usuario = None
        if destino_id:
            usuario = empleados_asignables().filter(pk=destino_id).first()
            if usuario is None:
                messages.error(request, 'El empleado seleccionado no está disponible.')
                return redirect(volver)

        pendientes = []
        desasignados_por_anterior = {}
        with transaction.atomic():
            for activo in activos:
                anterior = activo.persona_responsable
                if _misma_persona(anterior, usuario):
                    continue
                activo.asignar(usuario)
                activo.save(update_fields=['responsable', 'usuario_legacy', 'fecha_actualizacion'])
                movimiento = _registrar_reasignacion_en_historial(
                    activo, anterior, usuario, request.user,
                )
                cambios += 1
                if anterior:
                    clave = (type(anterior), anterior.pk)
                    desasignados_por_anterior.setdefault(clave, (anterior, []))[1].append(activo)
                if usuario:
                    pendientes.append((activo, movimiento))

        for anterior, sus_activos in desasignados_por_anterior.values():
            avisar_activos_desasignados(sus_activos, anterior, request.user)
        avisar_activos_asignados([activo for activo, _ in pendientes], usuario, request.user)
        ids_constancia = []
        for activo, movimiento in pendientes:
            try:
                _aplicar_planilla_historial(
                    activo, usuario, request.user, movimiento,
                )
                ids_constancia.append(activo.pk)
            except Exception as exc:
                messages.error(
                    request,
                    f"No se pudo archivar la planilla de {activo.codigo_inventario}: {exc}",
                )
        messages.success(
            request,
            f'{cambios} activo(s) reasignado(s) a {_nombre(usuario)}.'
            if cambios else 'Los activos seleccionados ya tenían ese responsable.',
        )
        if ids_constancia:
            return redirect(_url_con_constancia(volver, ids_constancia))

    elif accion == 'reubicar':
        ubicacion = Ubicacion.objects.filter(pk=destino_id).first() if destino_id else None
        if ubicacion is None:
            messages.error(request, 'Selecciona una ubicación válida.')
            return redirect(volver)

        with transaction.atomic():
            for activo in activos:
                if activo.ubicacion_id == ubicacion.pk:
                    continue
                anterior = activo.ubicacion
                activo.ubicacion = ubicacion
                activo.save(update_fields=['ubicacion', 'fecha_actualizacion'])
                _registrar_reubicacion_en_historial(activo, anterior, ubicacion, request.user)
                cambios += 1

        messages.success(
            request,
            f'{cambios} activo(s) reubicado(s) en {ubicacion.nombre}.'
            if cambios else 'Los activos seleccionados ya estaban en esa ubicación.',
        )

    else:
        messages.error(request, 'Acción no reconocida.')

    return redirect(volver)


class ActivoHistorialView(AdminActivoRequiredMixin, DetailView):
    """Vista para mostrar el historial de movimientos de un activo"""
    model = Activo
    template_name = 'activos/activo/historial.html'
    context_object_name = 'activo'
    
    def get_queryset(self):
        return super().get_queryset().select_related(
            'subcategoria__categoria', 'ubicacion', 'responsable', 'usuario_legacy'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['historial'] = (
            self.object.historial_movimientos
            .select_related('usuario')
            .order_by('-fecha_movimiento')
        )
        return context


# ============== "MIS ACTIVOS" — vista propia del usuario dueño ==============
#
# A diferencia de todo lo anterior, estas dos vistas exigen solo acceso al
# módulo (ModuloActivoRequiredMixin), no rol administrador: son la única
# ventana al inventario que tiene un usuario sin ese rol, y muestran
# exclusivamente lo que tiene asignado (nunca el inventario completo).


class MisActivosListView(ModuloActivoRequiredMixin, ListView):
    """Los activos asignados al usuario que hace la petición. Nada más."""

    model = Activo
    template_name = 'activos/mis_activos/list.html'
    context_object_name = 'activos'
    paginate_by = 20

    def get_queryset(self):
        return (
            Activo.objects.filter(responsable__usuario=self.request.user)
            .select_related('subcategoria__categoria', 'ubicacion')
            .order_by('-fecha_actualizacion')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['en_mantenimiento'] = self.get_queryset().filter(estado='EM').count()
        return context


class MisActivoDetailView(ModuloActivoRequiredMixin, DetailView):
    """Ficha de solo lectura de un activo propio.

    El queryset ya filtra por dueño: pedir el detalle de un activo ajeno da
    404, igual que si no existiera — no se distingue "no es tuyo" de "no
    existe" para no confirmar la existencia de códigos de otras personas.
    """

    model = Activo
    template_name = 'activos/mis_activos/detail.html'
    context_object_name = 'activo'

    def get_queryset(self):
        return (
            Activo.objects.filter(responsable__usuario=self.request.user)
            .select_related('subcategoria__categoria', 'ubicacion')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['movimientos_recientes'] = (
            self.object.historial_movimientos.order_by('-fecha_movimiento')[:6]
        )
        context['mantenimientos_recientes'] = list(
            self.object.mantenimientos.order_by('-fecha')[:10]
        )
        from activos.models import EtiquetaQR

        context['etiqueta_vigente'] = (
            self.object.etiquetas
            .filter(estado=EtiquetaQR.EstadoEtiqueta.VINCULADA)
            .order_by('-fecha_vinculacion')
            .first()
        )
        return context
