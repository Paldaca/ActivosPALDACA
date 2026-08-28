"""Gestión de etiquetas QR: generar lotes, listarlas y completarlas.

Vistas protegidas por el módulo, igual que el resto de `views.py`. Viven en un
fichero propio porque `views.py` ya ronda las 800 líneas y esta funcionalidad
es autocontenida: el único punto de contacto real con el inventario es el alta
del activo, que ocurre en `etiqueta_alta()`.
"""

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from .decorators import ModuloActivoRequiredMixin, requiere_modulo_paldaca
from .forms import AltaDesdeEtiquetaForm, GenerarEtiquetasForm
from .models import EtiquetaQR, HistorialMovimiento
from .services.codigos import reservar_codigos

_ESTADO_ETIQUETA_LABELS = dict(EtiquetaQR.EstadoEtiqueta.choices)


class EtiquetaListView(ModuloActivoRequiredMixin, ListView):
    """Parque de etiquetas emitidas, filtrable por estado."""

    model = EtiquetaQR
    template_name = "activos/etiqueta/list.html"
    context_object_name = "etiquetas"
    paginate_by = 30

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "subcategoria__categoria",
            "activo",
            "creada_por",
        )
        estado = (self.request.GET.get("estado") or "").upper()
        if estado in dict(EtiquetaQR.EstadoEtiqueta.choices):
            qs = qs.filter(estado=estado)

        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(codigo_reservado__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["form_generar"] = GenerarEtiquetasForm()
        estado_activo = (self.request.GET.get("estado") or "").upper()
        q = (self.request.GET.get("q") or "").strip()
        contexto["estado_activo"] = estado_activo
        contexto["q"] = q
        contexto["resumen"] = {
            "total": EtiquetaQR.objects.count(),
            "pendientes": EtiquetaQR.objects.filter(estado="PE").count(),
            "vinculadas": EtiquetaQR.objects.filter(estado="VI").count(),
            "anuladas": EtiquetaQR.objects.filter(estado="AN").count(),
        }

        filtros_activos = []
        if q:
            filtros_activos.append({
                "param": "q",
                "etiqueta": "Código",
                "valor": q,
            })
        if estado_activo in _ESTADO_ETIQUETA_LABELS:
            filtros_activos.append({
                "param": "estado",
                "etiqueta": "Estado",
                "valor": _ESTADO_ETIQUETA_LABELS[estado_activo],
            })
        contexto["filtros_activos"] = filtros_activos
        return contexto


@requiere_modulo_paldaca
def generar_etiquetas(request):
    """Aparta N códigos de una subcategoría y crea sus etiquetas.

    La reserva y la creación van en la MISMA transacción a propósito: los
    códigos que devuelve el servicio solo están garantizados mientras dure el
    bloqueo que los calculó. Persistirlos fuera reabriría la carrera que el
    servicio existe para cerrar.
    """
    if request.method != "POST":
        return redirect("activos:etiqueta-list")

    form = GenerarEtiquetasForm(request.POST)
    if not form.is_valid():
        for errores in form.errors.values():
            for error in errores:
                messages.error(request, error)
        return redirect("activos:etiqueta-list")

    subcategoria = form.cleaned_data["subcategoria"]
    cantidad = form.cleaned_data["cantidad"]

    with transaction.atomic():
        codigos = reservar_codigos(subcategoria, cantidad)
        EtiquetaQR.objects.bulk_create([
            EtiquetaQR(
                codigo_reservado=codigo,
                subcategoria=subcategoria,
                creada_por=request.user,
                # `bulk_create` se salta save(), de ahí el token explícito.
                token=EtiquetaQR.generar_token(),
            )
            for codigo in codigos
        ])
        # Se releen para obtener las claves primarias. MySQL —la base real de
        # la Suite— NO las devuelve en un bulk_create; SQLite sí, así que sin
        # esto el enlace al PDF sale con `ids=None,None,...` y solo falla en
        # producción.
        etiquetas = list(
            EtiquetaQR.objects.filter(codigo_reservado__in=codigos)
            .order_by("codigo_reservado")
        )

    messages.success(
        request,
        f"{cantidad} etiqueta(s) generada(s) para {subcategoria}: "
        f"{codigos[0]} … {codigos[-1]}."
        if cantidad > 1
        else f"Etiqueta {codigos[0]} generada para {subcategoria}.",
    )

    # Directo al PDF: quien genera un lote lo hace para imprimirlo ya.
    destino = reverse("reportes:etiquetas-pdf")
    return redirect(f"{destino}?ids={','.join(str(e.pk) for e in etiquetas)}")


@requiere_modulo_paldaca
def etiqueta_alta(request, token):
    """Completa los datos del activo de una etiqueta escaneada.

    Es la contrapartida con sesión de `/q/<token>/`: la ficha pública invita, y
    aquí se escribe. Cuelga de `/q/` y no de `/activos/` para heredar su
    exclusión del redirect al shell del Portal; si no, alguien con sesión que
    escanease desde el móvil acabaría rellenando el formulario dentro del
    iframe del Portal.
    """
    etiqueta = get_object_or_404(
        EtiquetaQR.objects.select_related("subcategoria__categoria"),
        token=token,
    )

    if etiqueta.estado == EtiquetaQR.EstadoEtiqueta.ANULADA:
        messages.error(
            request,
            f"La etiqueta {etiqueta.codigo_reservado} está anulada y no admite altas.",
        )
        return redirect("activos:etiqueta-list")

    # Reintento del formulario tras un envío que sí llegó (típico con mala
    # cobertura): no se duplica el activo, se lleva a la ficha que ya existe.
    if etiqueta.esta_vinculada:
        messages.info(
            request,
            f"{etiqueta.codigo_reservado} ya tiene sus datos cargados.",
        )
        return redirect("activos:activo-detail", pk=etiqueta.activo_id)

    if request.method == "POST":
        form = AltaDesdeEtiquetaForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                activo = form.save(commit=False)
                activo.subcategoria = etiqueta.subcategoria
                activo.codigo_inventario = etiqueta.codigo_reservado
                activo.save()

                etiqueta.vincular(activo)

                # A diferencia del alta de escritorio (BR-ACT-11), aquí SÍ se
                # deja rastro: registrar un equipo en campo, desde un móvil y
                # posiblemente por alguien distinto de quien lo compró, es
                # justo el evento que después se quiere poder reconstruir.
                HistorialMovimiento.objects.create(
                    activo=activo,
                    tipo_movimiento=HistorialMovimiento.TipoMovimiento.CREACION,
                    descripcion=(
                        f"Alta desde la etiqueta QR {etiqueta.codigo_reservado}."
                    ),
                    usuario=request.user,
                )

            messages.success(
                request,
                f"Activo {activo.codigo_inventario} registrado correctamente.",
            )
            destino = reverse("activos:activo-detail", kwargs={"pk": activo.pk})
            if activo.usuario_asignado_id:
                # Enganche para la constancia de asignación (fase pendiente,
                # sin implementar todavía): hoy `?constancia=` no lo lee nadie,
                # así que esto no ofrece nada en la ficha. Se deja el parámetro
                # para no tener que volver a tocar este punto de disparo
                # cuando se construya esa pieza.
                return redirect(f"{destino}?constancia={activo.pk}")
            return redirect(destino)
    else:
        form = AltaDesdeEtiquetaForm()

    return render(request, "activos/publico/alta.html", {
        "form": form,
        "etiqueta": etiqueta,
    })


@require_POST
@requiere_modulo_paldaca
def etiqueta_anular(request, pk):
    """Retira una etiqueta de circulación (adhesivo perdido o ilegible).

    El listado ofrece "Anular" incluso sobre una etiqueta todavía vinculada,
    como atajo a no obligar a desvincular primero. Si se usa ese atajo, el
    activo se queda sin rastro de que perdió su etiqueta vigente a menos que
    se registre aquí — igual que hace `etiqueta_desvincular` en su propio caso.
    """
    etiqueta = get_object_or_404(EtiquetaQR.objects.select_related("activo"), pk=pk)
    activo = etiqueta.activo

    with transaction.atomic():
        etiqueta.anular()
        if activo is not None:
            HistorialMovimiento.objects.create(
                activo=activo,
                tipo_movimiento=HistorialMovimiento.TipoMovimiento.ACTUALIZACION,
                descripcion=(
                    f"Etiqueta QR {etiqueta.codigo_reservado} anulada "
                    "estando vinculada a este activo."
                ),
                usuario=request.user,
            )

    messages.success(
        request,
        f"Etiqueta {etiqueta.codigo_reservado} anulada. Su código no se reutiliza.",
    )
    return redirect("activos:etiqueta-list")


@require_POST
@requiere_modulo_paldaca
def etiqueta_desvincular(request, pk):
    """Suelta el activo de una etiqueta pegada en el equipo equivocado."""
    etiqueta = get_object_or_404(EtiquetaQR.objects.select_related("activo"), pk=pk)
    activo = etiqueta.activo

    if activo is None:
        messages.warning(request, "Esa etiqueta no está vinculada a ningún activo.")
        return redirect("activos:etiqueta-list")

    with transaction.atomic():
        HistorialMovimiento.objects.create(
            activo=activo,
            tipo_movimiento=HistorialMovimiento.TipoMovimiento.ACTUALIZACION,
            descripcion=(
                f"Etiqueta QR {etiqueta.codigo_reservado} desvinculada de este activo."
            ),
            usuario=request.user,
        )
        etiqueta.desvincular()

    messages.success(
        request,
        f"Etiqueta {etiqueta.codigo_reservado} liberada; vuelve a estar pendiente.",
    )
    return redirect("activos:etiqueta-list")
