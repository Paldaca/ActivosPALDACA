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
from .models import Categoria, SubCategoria, Ubicacion, Activo, HistorialMovimiento
from .forms import (
    CategoriaForm, SubCategoriaForm, UbicacionForm,
    ActivoForm, ActivoFilterForm, ReasignarActivoForm, ReubicarActivoForm,
    usuarios_asignables,
)
from .decorators import ModuloActivoRequiredMixin, requiere_modulo_paldaca


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

    Los estados que ve el usuario se derivan de (estado, usuario_asignado):
    el modelo solo guarda AC / IN / EM.
    """
    return Activo.objects.aggregate(
        total=Count('id'),
        disponibles=Count('id', filter=Q(estado='AC', usuario_asignado__isnull=True)),
        asignados=Count('id', filter=Q(estado='AC', usuario_asignado__isnull=False)),
        mantenimiento=Count('id', filter=Q(estado='EM')),
        baja=Count('id', filter=Q(estado='IN')),
    )

# ============== VISTAS DE CATEGORÍA ==============
class CategoriaListView(ModuloActivoRequiredMixin, ListView):
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


class CategoriaCreateView(ModuloActivoRequiredMixin, CreateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = 'activos/categoria/form.html'
    success_url = reverse_lazy('activos:categoria-list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Categoría creada exitosamente.')
        return super().form_valid(form)


class CategoriaUpdateView(ModuloActivoRequiredMixin, UpdateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = 'activos/categoria/form.html'
    success_url = reverse_lazy('activos:categoria-list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Categoría actualizada exitosamente.')
        return super().form_valid(form)


class CategoriaDeleteView(SinPaginaDeBorradoMixin, ModuloActivoRequiredMixin, DeleteView):
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

class SubCategoriaListView(ModuloActivoRequiredMixin, ListView):
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


class SubCategoriaCreateView(ModuloActivoRequiredMixin, CreateView):
    model = SubCategoria
    form_class = SubCategoriaForm
    template_name = 'activos/subcategoria/form.html'
    success_url = reverse_lazy('activos:subcategoria-list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Subcategoría creada exitosamente.')
        return super().form_valid(form)


class SubCategoriaUpdateView(ModuloActivoRequiredMixin, UpdateView):
    model = SubCategoria
    form_class = SubCategoriaForm
    template_name = 'activos/subcategoria/form.html'
    success_url = reverse_lazy('activos:subcategoria-list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Subcategoría actualizada exitosamente.')
        return super().form_valid(form)


class SubCategoriaDeleteView(SinPaginaDeBorradoMixin, ModuloActivoRequiredMixin, DeleteView):
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

class UbicacionListView(ModuloActivoRequiredMixin, ListView):
    model = Ubicacion
    template_name = 'activos/ubicacion/list.html'
    context_object_name = 'ubicaciones'
    paginate_by = 20

    def get_queryset(self):
        return super().get_queryset().annotate(
            num_activos=Count('activos', distinct=True),
        ).order_by('nombre')


class UbicacionCreateView(ModuloActivoRequiredMixin, CreateView):
    model = Ubicacion
    form_class = UbicacionForm
    template_name = 'activos/ubicacion/form.html'
    success_url = reverse_lazy('activos:ubicacion-list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Ubicación creada exitosamente.')
        return super().form_valid(form)


class UbicacionUpdateView(ModuloActivoRequiredMixin, UpdateView):
    model = Ubicacion
    form_class = UbicacionForm
    template_name = 'activos/ubicacion/form.html'
    success_url = reverse_lazy('activos:ubicacion-list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Ubicación actualizada exitosamente.')
        return super().form_valid(form)


class UbicacionDeleteView(SinPaginaDeBorradoMixin, ModuloActivoRequiredMixin, DeleteView):
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

class ActivoListView(ModuloActivoRequiredMixin, ListView):
    model = Activo
    template_name = 'activos/activo/list.html'
    context_object_name = 'activos'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'subcategoria__categoria', 'ubicacion', 'usuario_asignado'
        )
        
        # Filtros
        categoria_id = self.request.GET.get('categoria')
        subcategoria_id = self.request.GET.get('subcategoria')
        ubicacion_id = self.request.GET.get('ubicacion')
        estado = self.request.GET.get('estado')
        asignacion = self.request.GET.get('asignacion')
        usuario_id = self.request.GET.get('usuario_asignado')
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
            queryset = queryset.filter(usuario_asignado__isnull=True)
        elif asignacion == 'asignado':
            queryset = queryset.filter(usuario_asignado__isnull=False)
        if usuario_id:
            queryset = queryset.filter(usuario_asignado_id=usuario_id)
        if buscar:
            # Buscar también por persona: "¿qué tiene asignado Ana?" es una
            # pregunta diaria y antes obligaba a recorrer la tabla a mano.
            queryset = queryset.filter(
                Q(codigo_inventario__icontains=buscar) |
                Q(marca__icontains=buscar) |
                Q(modelo__icontains=buscar) |
                Q(numero_serial__icontains=buscar) |
                Q(usuario_asignado__first_name__icontains=buscar) |
                Q(usuario_asignado__last_name__icontains=buscar) |
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

        if get.get('usuario_asignado'):
            obj = usuarios_asignables().filter(pk=get['usuario_asignado']).first()
            self._usuario_filtro = obj
            agregar('usuario_asignado', 'Responsable', _nombre(obj) if obj else None)

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

        # La lista completa de personas se carga bajo demanda desde el drawer.
        context['usuario_filtro'] = getattr(self, '_usuario_filtro', None)
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
@requiere_modulo_paldaca
def buscar_usuarios_asignables(request):
    """Return a small, searchable page of assignable people."""
    query = (request.GET.get('q') or '').strip()[:80]
    try:
        page = max(1, int(request.GET.get('page', '1')))
    except ValueError:
        page = 1
    page_size = 20
    queryset = usuarios_asignables()
    if query:
        queryset = queryset.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(username__icontains=query)
            | Q(email__icontains=query)
        )
    start = (page - 1) * page_size
    rows = list(queryset[start:start + page_size + 1])
    return JsonResponse({
        'results': [
            {'id': user.pk, 'text': _nombre(user)}
            for user in rows[:page_size]
        ],
        'has_more': len(rows) > page_size,
    })


class ActivoDetailView(ModuloActivoRequiredMixin, DetailView):
    model = Activo
    template_name = 'activos/activo/detail.html'
    context_object_name = 'activo'

    def get_queryset(self):
        return super().get_queryset().select_related(
            'subcategoria__categoria', 'ubicacion', 'usuario_asignado'
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
        return context


class ActivoFormContextMixin:
    """Catálogos que necesita el alta express dentro del formulario de activos."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categorias_catalogo'] = Categoria.objects.all()
        return context


class ActivoCreateView(ActivoFormContextMixin, ModuloActivoRequiredMixin, CreateView):
    model = Activo
    form_class = ActivoForm
    template_name = 'activos/activo/form.html'
    success_url = reverse_lazy('activos:activo-list')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Activo {self.object.codigo_inventario} creado exitosamente.',
        )
        return response

    def get_success_url(self):
        # "Guardar y registrar otro": alta en serie sin volver al listado.
        if 'guardar_y_nuevo' in self.request.POST:
            return reverse('activos:activo-create')
        return reverse('activos:activo-detail', kwargs={'pk': self.object.pk})


class ActivoUpdateView(ActivoFormContextMixin, ModuloActivoRequiredMixin, UpdateView):
    model = Activo
    form_class = ActivoForm
    template_name = 'activos/activo/form.html'
    success_url = reverse_lazy('activos:activo-list')
    
    def form_valid(self, form):
        pk = self.object.pk
        activo_original = Activo.objects.select_related(
            'ubicacion', 'usuario_asignado'
        ).get(pk=pk)
        response = super().form_valid(form)
        activo_actualizado = self.object
        _registrar_reubicacion_en_historial(
            activo_actualizado,
            activo_original.ubicacion,
            activo_actualizado.ubicacion,
            self.request.user,
        )
        movimiento = _registrar_reasignacion_en_historial(
            activo_actualizado,
            activo_original.usuario_asignado,
            activo_actualizado.usuario_asignado,
            self.request.user,
        )
        messages.success(self.request, 'Activo actualizado exitosamente.')
        return response


class ActivoDeleteView(SinPaginaDeBorradoMixin, ModuloActivoRequiredMixin, DeleteView):
    model = Activo
    success_url = reverse_lazy('activos:activo-list')

    def get_queryset(self):
        return super().get_queryset().select_related(
            'subcategoria__categoria', 'ubicacion', 'usuario_asignado'
        )

    def get_redireccion_get(self):
        # Un GET aquí suele ser un enlace antiguo: se devuelve a la ficha, que
        # es donde vive el botón real de eliminar.
        return reverse('activos:activo-detail', kwargs={'pk': self.kwargs['pk']})

    def form_valid(self, form):
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


def _registrar_reasignacion_en_historial(activo, usuario_anterior, usuario_nuevo, usuario):
    """Si cambió el usuario asignado, registra reasignación (misma semántica que reasignar_activo)."""
    if (usuario_anterior.id if usuario_anterior else None) == (
        usuario_nuevo.id if usuario_nuevo else None
    ):
        return
    # El historial también respeta la regla: "Nombre Apellido", nunca username.
    valor_anterior = _nombre(usuario_anterior)
    valor_nuevo = _nombre(usuario_nuevo)
    return HistorialMovimiento.objects.create(
        activo=activo,
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.REASIGNACION,
        descripcion=f"Reasignación de usuario: {valor_anterior} -> {valor_nuevo}",
        campo_modificado='usuario_asignado',
        valor_anterior=valor_anterior,
        valor_nuevo=valor_nuevo,
        usuario=usuario if usuario and usuario.is_authenticated else None,
    )


# ============== VISTAS ESPECIALES DE ACTIVO ==============

@requiere_modulo_paldaca
def reasignar_activo(request, pk):
    """Reasigna un activo a otra persona.

    Sirve a dos interfaces con el mismo endpoint: el drawer lateral (que envía
    `next` para volver al listado sin perder filtros) y la página completa, que
    queda como respaldo accesible y sin JavaScript.
    """
    activo = get_object_or_404(
        Activo.objects.select_related('subcategoria__categoria', 'ubicacion', 'usuario_asignado'),
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
        activo_original = Activo.objects.select_related('usuario_asignado').get(pk=pk)
        form = ReasignarActivoForm(request.POST, instance=activo)
        if form.is_valid():
            usuario_anterior = activo_original.usuario_asignado
            activo_actualizado = form.save()
            usuario_nuevo = activo_actualizado.usuario_asignado

            movimiento = _registrar_reasignacion_en_historial(
                activo_actualizado,
                usuario_anterior,
                usuario_nuevo,
                request.user,
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
        'usuarios_asignables': usuarios_asignables(),
        'next': destino,
    })


@requiere_modulo_paldaca
def reubicar_activo(request, pk):
    """Reubica un activo. Mismo contrato que `reasignar_activo`."""
    activo = get_object_or_404(
        Activo.objects.select_related('subcategoria__categoria', 'ubicacion', 'usuario_asignado'),
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
@requiere_modulo_paldaca
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
@requiere_modulo_paldaca
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

    activos = Activo.objects.select_related('usuario_asignado', 'ubicacion').filter(pk__in=ids)
    cambios = 0

    if accion == 'reasignar':
        usuario = None
        if destino_id:
            usuario = usuarios_asignables().filter(pk=destino_id).first()
            if usuario is None:
                messages.error(request, 'La persona seleccionada no está disponible.')
                return redirect(volver)

        pendientes = []
        with transaction.atomic():
            for activo in activos:
                if activo.usuario_asignado_id == (usuario.pk if usuario else None):
                    continue
                anterior = activo.usuario_asignado
                activo.usuario_asignado = usuario
                activo.save(update_fields=['usuario_asignado', 'fecha_actualizacion'])
                movimiento = _registrar_reasignacion_en_historial(
                    activo, anterior, usuario, request.user,
                )
                cambios += 1
                if usuario:
                    pendientes.append(activo.pk)

        ids_constancia = pendientes
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


class ActivoHistorialView(ModuloActivoRequiredMixin, DetailView):
    """Vista para mostrar el historial de movimientos de un activo"""
    model = Activo
    template_name = 'activos/activo/historial.html'
    context_object_name = 'activo'
    
    def get_queryset(self):
        return super().get_queryset().select_related(
            'subcategoria__categoria', 'ubicacion', 'usuario_asignado'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['historial'] = (
            self.object.historial_movimientos
            .select_related('usuario')
            .order_by('-fecha_movimiento')
        )
        return context
