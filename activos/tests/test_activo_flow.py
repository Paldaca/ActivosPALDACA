"""
Flujo principal de activos: CRUD, reubicar, reasignar e historial (pytest-django).
"""
import html

import pytest
from django.urls import reverse

from activos.models import Activo, HistorialMovimiento


def _response_text(response):
    """Texto HTML decodificado y sin entidades, para comparar con textos del modelo."""
    return html.unescape(response.content.decode("utf-8"))


def _activo_from_create_redirect(response):
    pk = int(response["Location"].rstrip("/").split("/")[-1])
    return Activo.objects.get(pk=pk)


@pytest.mark.django_db
def test_vistas_activos_redirigen_si_no_hay_sesion(client, catalogo):
    urls = [
        reverse("activos:activo-list"),
        reverse("activos:activo-create"),
        reverse("activos:activo-detail", args=[1]),
    ]
    for url in urls:
        r = client.get(url)
        assert r.status_code == 302
        assert "login" in r.url.lower()


def _payload_activo(catalogo, **overrides):
    base = {
        "subcategoria": catalogo["subcategoria"].pk,
        "marca": "MarcaPy",
        "modelo": "ModeloPy",
        "numero_serial": "SN-PY-1",
        "codigo_inventario": "INV-PY-UNICO",
        "usuario_asignado": catalogo["usuario_a"].pk,
        "ubicacion": catalogo["ubicacion_almacen"].pk,
        "observaciones": "Nota pytest",
        "estado": Activo.EstadoActivo.ACTIVO,
    }
    base.update(overrides)
    return base


@pytest.mark.django_db
def test_crear_activo_con_generar_qr_redirige_a_pdf(client_auth, catalogo):
    url = reverse("activos:activo-create")
    data = _payload_activo(catalogo)
    data["generar_etiqueta_qr"] = "1"
    r = client_auth.post(url, data)
    assert r.status_code == 302
    assert reverse("reportes:etiquetas-pdf") in r["Location"]
    act = Activo.objects.get(marca="MarcaPy", modelo="ModeloPy")
    from activos.models import EtiquetaQR

    etiqueta = EtiquetaQR.objects.get(activo=act)
    assert etiqueta.estado == EtiquetaQR.EstadoEtiqueta.VINCULADA
    assert etiqueta.codigo_reservado == act.codigo_inventario
    assert f"ids={etiqueta.pk}" in r["Location"]


@pytest.mark.django_db
def test_crear_activo_sin_generar_qr_va_a_ficha(client_auth, catalogo):
    url = reverse("activos:activo-create")
    data = _payload_activo(catalogo, marca="SinQr", modelo="SinQr")
    r = client_auth.post(url, data)
    assert r.status_code == 302
    act = Activo.objects.get(marca="SinQr")
    assert r["Location"].endswith(reverse("activos:activo-detail", args=[act.pk]))
    from activos.models import EtiquetaQR

    assert not EtiquetaQR.objects.filter(activo=act).exists()


@pytest.mark.django_db
def test_crear_activo_exitoso(client_auth, catalogo):
    url = reverse("activos:activo-create")
    data = _payload_activo(catalogo)
    r = client_auth.post(url, data)
    assert r.status_code == 302
    act = _activo_from_create_redirect(r)
    assert r["Location"].endswith(reverse("activos:activo-detail", args=[act.pk]))
    assert act.marca == "MarcaPy"
    assert act.ubicacion_id == catalogo["ubicacion_almacen"].pk
    assert act.usuario_asignado_id == catalogo["usuario_a"].pk
    assert not act.historial_movimientos.exists()


@pytest.mark.django_db
def test_editar_activo_registra_reubicacion_y_reasignacion_en_historial(
    client_auth, catalogo, user
):
    act = Activo.objects.create(
        subcategoria=catalogo["subcategoria"],
        marca="M1",
        modelo="Mo1",
        codigo_inventario="INV-EDIT-HIST",
        usuario_asignado=catalogo["usuario_a"],
        ubicacion=catalogo["ubicacion_almacen"],
        estado=Activo.EstadoActivo.ACTIVO,
    )
    # Historial previo (carga inicial / datos legados) — la edición debe sumar entradas.
    HistorialMovimiento.objects.create(
        activo=act,
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.CREACION,
        descripcion="Alta manual en inventario (semilla de prueba)",
        usuario=user,
    )
    HistorialMovimiento.objects.create(
        activo=act,
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.ACTUALIZACION,
        descripcion="Movimiento previo al editar desde formulario",
        usuario=user,
    )
    assert act.historial_movimientos.count() == 2

    url = reverse("activos:activo-update", args=[act.pk])
    data = _payload_activo(
        catalogo,
        codigo_inventario="INV-EDIT-HIST",
        usuario_asignado=catalogo["usuario_b"].pk,
        ubicacion=catalogo["ubicacion_oficina"].pk,
        marca="M1-actualizada",
    )
    r = client_auth.post(url, data)
    assert r.status_code == 302

    act.refresh_from_db()
    assert act.ubicacion_id == catalogo["ubicacion_oficina"].pk
    assert act.usuario_asignado_id == catalogo["usuario_b"].pk

    tipos = list(
        act.historial_movimientos.order_by("id").values_list(
            "tipo_movimiento", flat=True
        )
    )
    assert tipos.count(HistorialMovimiento.TipoMovimiento.REUBICACION) == 1
    assert tipos.count(HistorialMovimiento.TipoMovimiento.REASIGNACION) == 1
    assert act.historial_movimientos.count() == 4

    ru = act.historial_movimientos.filter(
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.REUBICACION
    ).first()
    assert ru.usuario_id == user.pk
    assert catalogo["ubicacion_almacen"].nombre in ru.valor_anterior
    assert catalogo["ubicacion_oficina"].nombre in ru.valor_nuevo

    re = act.historial_movimientos.filter(
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.REASIGNACION
    ).first()
    assert re.usuario_id == user.pk
    # El historial guarda "Nombre Apellido", no el username: es la instantánea
    # de lo que la interfaz debe mostrar aunque el usuario cambie o se elimine.
    assert catalogo["usuario_a"].get_full_name() in re.valor_anterior
    assert catalogo["usuario_b"].get_full_name() in re.valor_nuevo
    assert catalogo["usuario_a"].username not in re.valor_anterior

    # La vista de historial debe cargar entradas previas + las generadas al editar.
    hist_url = reverse("activos:activo-historial", args=[act.pk])
    page = client_auth.get(hist_url)
    assert page.status_code == 200
    body = _response_text(page)
    assert "Alta manual en inventario (semilla de prueba)" in body
    assert "Movimiento previo al editar desde formulario" in body
    assert ru.descripcion in body
    assert re.descripcion in body


@pytest.mark.django_db
def test_reubicar_activo_crea_entrada_historial(client_auth, catalogo, user):
    act = Activo.objects.create(
        subcategoria=catalogo["subcategoria"],
        marca="M",
        modelo="Mo",
        codigo_inventario="INV-REUB",
        usuario_asignado=None,
        ubicacion=catalogo["ubicacion_almacen"],
        estado=Activo.EstadoActivo.ACTIVO,
    )
    url = reverse("activos:activo-reubicar", args=[act.pk])
    r = client_auth.post(
        url, {"ubicacion": catalogo["ubicacion_oficina"].pk}
    )
    assert r.status_code == 302
    assert act.historial_movimientos.count() == 1
    h = act.historial_movimientos.first()
    assert h.tipo_movimiento == HistorialMovimiento.TipoMovimiento.REUBICACION
    assert h.usuario_id == user.pk


@pytest.mark.django_db
def test_reasignar_activo_crea_entrada_historial(client_auth, catalogo, user):
    act = Activo.objects.create(
        subcategoria=catalogo["subcategoria"],
        marca="M",
        modelo="Mo",
        codigo_inventario="INV-REAS",
        usuario_asignado=catalogo["usuario_a"],
        ubicacion=catalogo["ubicacion_almacen"],
        estado=Activo.EstadoActivo.ACTIVO,
    )
    url = reverse("activos:activo-reasignar", args=[act.pk])
    r = client_auth.post(
        url, {"usuario_asignado": catalogo["usuario_b"].pk}
    )
    assert r.status_code == 302
    assert act.historial_movimientos.count() == 1
    h = act.historial_movimientos.first()
    assert h.tipo_movimiento == HistorialMovimiento.TipoMovimiento.REASIGNACION
    assert h.usuario_id == user.pk


@pytest.mark.django_db
def test_historial_vista_lista_movimientos(client_auth, catalogo):
    act = Activo.objects.create(
        subcategoria=catalogo["subcategoria"],
        marca="M",
        modelo="Mo",
        codigo_inventario="INV-HIST-VIEW",
        usuario_asignado=None,
        ubicacion=catalogo["ubicacion_almacen"],
        estado=Activo.EstadoActivo.ACTIVO,
    )
    HistorialMovimiento.objects.create(
        activo=act,
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.REUBICACION,
        descripcion="Movimiento de prueba",
        campo_modificado="ubicacion",
        valor_anterior="A",
        valor_nuevo="B",
    )
    url = reverse("activos:activo-historial", args=[act.pk])
    r = client_auth.get(url)
    assert r.status_code == 200
    assert "Movimiento de prueba" in _response_text(r)


@pytest.mark.django_db
def test_eliminar_activo(client_auth, catalogo):
    act = Activo.objects.create(
        subcategoria=catalogo["subcategoria"],
        marca="M",
        modelo="Mo",
        codigo_inventario="INV-DEL",
        usuario_asignado=None,
        ubicacion=catalogo["ubicacion_almacen"],
        estado=Activo.EstadoActivo.ACTIVO,
    )
    HistorialMovimiento.objects.create(
        activo=act,
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.ACTUALIZACION,
        descripcion="dummy",
    )
    pk = act.pk
    url = reverse("activos:activo-delete", args=[pk])
    r = client_auth.post(url, {})
    assert r.status_code == 302
    assert not Activo.objects.filter(pk=pk).exists()
    assert not HistorialMovimiento.objects.filter(activo_id=pk).exists()


@pytest.mark.django_db
def test_flujo_integrado_crear_editar_reubicar_reasignar_historial_eliminar(
    client_auth, catalogo,
):
    # Crear
    create_url = reverse("activos:activo-create")
    r = client_auth.post(create_url, _payload_activo(catalogo))
    assert r.status_code == 302
    act = _activo_from_create_redirect(r)
    codigo = act.codigo_inventario
    assert act.historial_movimientos.count() == 0

    # Editar (ubicación y asignación ya puestas en crear; solo marca)
    update_url = reverse("activos:activo-update", args=[act.pk])
    r = client_auth.post(
        update_url,
        _payload_activo(
            catalogo,
            codigo_inventario=codigo,
            marca="MarcaPostEdicion",
            ubicacion=catalogo["ubicacion_oficina"].pk,
            usuario_asignado=catalogo["usuario_b"].pk,
        ),
    )
    assert r.status_code == 302
    act.refresh_from_db()
    assert act.marca == "MarcaPostEdicion"
    assert act.historial_movimientos.count() == 2

    # Tras editar, el historial en pantalla incluye reubicación y reasignación.
    hist_url = reverse("activos:activo-historial", args=[act.pk])
    r_hist = client_auth.get(hist_url)
    assert r_hist.status_code == 200
    body = _response_text(r_hist)
    assert "Reubicación:" in body
    assert "Reasignación de usuario:" in body

    # Reubicar (sin cambio real → sin entrada extra)
    reub_url = reverse("activos:activo-reubicar", args=[act.pk])
    client_auth.post(
        reub_url, {"ubicacion": catalogo["ubicacion_oficina"].pk}
    )
    act.refresh_from_db()
    assert act.historial_movimientos.count() == 2

    # Reubicar con cambio
    client_auth.post(
        reub_url, {"ubicacion": catalogo["ubicacion_almacen"].pk}
    )
    act.refresh_from_db()
    assert act.historial_movimientos.count() == 3

    # Reasignar con cambio
    reas_url = reverse("activos:activo-reasignar", args=[act.pk])
    client_auth.post(
        reas_url, {"usuario_asignado": catalogo["usuario_a"].pk}
    )
    act.refresh_from_db()
    assert act.historial_movimientos.count() == 4

    # Historial en plantilla: todas las descripciones registradas hasta aquí.
    hist_url = reverse("activos:activo-historial", args=[act.pk])
    r = client_auth.get(hist_url)
    assert r.status_code == 200
    body = _response_text(r)
    for mov in act.historial_movimientos.order_by("-fecha_movimiento"):
        assert mov.descripcion in body

    # Eliminar
    del_url = reverse("activos:activo-delete", args=[act.pk])
    r = client_auth.post(del_url, {})
    assert r.status_code == 302
    assert not Activo.objects.filter(codigo_inventario=codigo).exists()
