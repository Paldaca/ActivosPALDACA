"""Etiquetas QR: reserva de códigos, ciclo de vida y ficha pública.

El foco está en las dos cosas que pueden hacer daño de verdad si se rompen:
que dos activos acaben con el mismo código de inventario, y que la ficha
pública —la única vista anónima del proyecto— filtre algo que no debe.
"""

import html

import pytest
from django.urls import reverse

from activos.models import Activo, EtiquetaQR, HistorialMovimiento, SubCategoria
from activos.services.codigos import reservar_codigos


def _texto(response):
    return html.unescape(response.content.decode("utf-8"))


@pytest.fixture
def subcategoria(catalogo):
    """Subcategoría con prefijo real: la del `catalogo` lo deja vacío."""
    return SubCategoria.objects.create(
        nombre="Portátiles QR",
        prefijo="LAP",
        categoria=catalogo["categoria"],
    )


@pytest.fixture
def etiqueta(subcategoria):
    return EtiquetaQR.objects.create(
        codigo_reservado=reservar_codigos(subcategoria, 1)[0],
        subcategoria=subcategoria,
    )


# =============================================================================
# Reserva de códigos
# =============================================================================

@pytest.mark.django_db
def test_reserva_devuelve_codigos_consecutivos(subcategoria):
    assert reservar_codigos(subcategoria, 3) == [
        "PAL-LAP-001", "PAL-LAP-002", "PAL-LAP-003",
    ]


@pytest.mark.django_db
def test_reserva_respeta_codigos_ya_apartados_por_etiquetas(subcategoria):
    """El fallo que motivó el servicio: una etiqueta impresa ocupa su número.

    Sin esto, imprimir etiquetas y dar de alta un activo por el camino manual
    producirían el mismo código y el segundo `save()` reventaría por unicidad.
    """
    EtiquetaQR.objects.create(
        codigo_reservado="PAL-LAP-001", subcategoria=subcategoria
    )
    assert reservar_codigos(subcategoria, 1) == ["PAL-LAP-002"]


@pytest.mark.django_db
def test_alta_normal_no_reutiliza_codigo_de_etiqueta(subcategoria, catalogo):
    EtiquetaQR.objects.create(
        codigo_reservado="PAL-LAP-001", subcategoria=subcategoria
    )
    activo = Activo.objects.create(
        subcategoria=subcategoria,
        marca="M", modelo="X",
        ubicacion=catalogo["ubicacion_almacen"],
    )
    assert activo.codigo_inventario == "PAL-LAP-002"


@pytest.mark.django_db
def test_reserva_continua_despues_del_numero_999(subcategoria):
    """El sufijo es texto, así que un MAX() en SQL ordenaría 1000 antes que 999."""
    EtiquetaQR.objects.create(
        codigo_reservado="PAL-LAP-999", subcategoria=subcategoria
    )
    assert reservar_codigos(subcategoria, 1) == ["PAL-LAP-1000"]


@pytest.mark.django_db
def test_reserva_rechaza_cantidad_invalida(subcategoria):
    with pytest.raises(ValueError):
        reservar_codigos(subcategoria, 0)


# =============================================================================
# Ciclo de vida de la etiqueta
# =============================================================================

@pytest.mark.django_db
def test_token_se_genera_solo_y_es_unico(subcategoria):
    a = EtiquetaQR.objects.create(codigo_reservado="PAL-LAP-001", subcategoria=subcategoria)
    b = EtiquetaQR.objects.create(codigo_reservado="PAL-LAP-002", subcategoria=subcategoria)
    assert a.token and b.token and a.token != b.token


@pytest.mark.django_db
def test_vincular_es_idempotente(etiqueta, catalogo, subcategoria):
    activo = Activo.objects.create(
        subcategoria=subcategoria, marca="M", modelo="X",
        ubicacion=catalogo["ubicacion_almacen"],
    )
    etiqueta.vincular(activo)
    primera_fecha = etiqueta.fecha_vinculacion

    etiqueta.vincular(activo)
    etiqueta.refresh_from_db()

    assert etiqueta.estado == EtiquetaQR.EstadoEtiqueta.VINCULADA
    assert etiqueta.fecha_vinculacion == primera_fecha


@pytest.mark.django_db
def test_etiqueta_anulada_no_admite_vinculacion(etiqueta, catalogo, subcategoria):
    from django.core.exceptions import ValidationError

    activo = Activo.objects.create(
        subcategoria=subcategoria, marca="M", modelo="X",
        ubicacion=catalogo["ubicacion_almacen"],
    )
    etiqueta.anular()
    with pytest.raises(ValidationError):
        etiqueta.vincular(activo)


@pytest.mark.django_db
def test_anular_no_libera_el_codigo(etiqueta, subcategoria):
    """Reutilizar el número dejaría dos adhesivos distintos con el mismo impreso."""
    etiqueta.anular()
    assert reservar_codigos(subcategoria, 1) == ["PAL-LAP-002"]


# =============================================================================
# Ficha pública — la única vista anónima del proyecto
# =============================================================================

@pytest.mark.django_db
def test_ficha_publica_visible_sin_sesion(client, etiqueta, catalogo, subcategoria):
    activo = Activo.objects.create(
        subcategoria=subcategoria, marca="Lenovo", modelo="T14",
        ubicacion=catalogo["ubicacion_almacen"],
        usuario_asignado=catalogo["usuario_a"],
        observaciones="SECRETO-INTERNO-NO-PUBLICAR",
    )
    etiqueta.vincular(activo)

    r = client.get(reverse("etiqueta-publica", args=[etiqueta.token]))
    cuerpo = _texto(r)

    assert r.status_code == 200
    assert activo.codigo_inventario in cuerpo
    assert "Lenovo" in cuerpo
    # Se acordó publicar nombre y apellido del responsable.
    assert "Ana Prueba" in cuerpo
    # Y nada más: las observaciones pueden llevar notas internas.
    assert "SECRETO-INTERNO-NO-PUBLICAR" not in cuerpo


@pytest.mark.django_db
def test_ficha_publica_no_ofrece_gestion_a_anonimos(client, etiqueta, catalogo, subcategoria):
    activo = Activo.objects.create(
        subcategoria=subcategoria, marca="Lenovo", modelo="T14",
        ubicacion=catalogo["ubicacion_almacen"],
    )
    etiqueta.vincular(activo)

    cuerpo = _texto(client.get(reverse("etiqueta-publica", args=[etiqueta.token])))
    assert reverse("activos:activo-reasignar", args=[activo.pk]) not in cuerpo


@pytest.mark.django_db
def test_ficha_publica_de_etiqueta_pendiente_invita_a_cargar(client, etiqueta):
    r = client.get(reverse("etiqueta-publica", args=[etiqueta.token]))
    assert r.status_code == 200
    assert "Cargar los datos" in _texto(r)


@pytest.mark.django_db
def test_ficha_publica_de_etiqueta_anulada_no_revela_nada(client, etiqueta, catalogo, subcategoria):
    activo = Activo.objects.create(
        subcategoria=subcategoria, marca="Lenovo", modelo="T14",
        ubicacion=catalogo["ubicacion_almacen"],
    )
    etiqueta.vincular(activo)
    etiqueta.anular()

    cuerpo = _texto(client.get(reverse("etiqueta-publica", args=[etiqueta.token])))
    assert "ya no está en uso" in cuerpo
    assert "Lenovo" not in cuerpo


@pytest.mark.django_db
def test_token_inexistente_devuelve_404(client):
    r = client.get(reverse("etiqueta-publica", args=["token-que-no-existe"]))
    assert r.status_code == 404


@pytest.mark.django_db
def test_ficha_publica_pide_no_indexar(client, etiqueta):
    r = client.get(reverse("etiqueta-publica", args=[etiqueta.token]))
    assert "noindex" in r["X-Robots-Tag"]


# =============================================================================
# Alta desde la etiqueta
# =============================================================================

@pytest.mark.django_db
def test_alta_desde_etiqueta_exige_sesion(client, etiqueta):
    r = client.get(reverse("etiqueta-alta", args=[etiqueta.token]))
    assert r.status_code == 302
    assert "login" in r.url.lower()


@pytest.mark.django_db
def test_alta_desde_etiqueta_usa_el_codigo_reservado(client_auth, etiqueta, catalogo):
    r = client_auth.post(reverse("etiqueta-alta", args=[etiqueta.token]), {
        "marca": "Lenovo",
        "modelo": "T14",
        "numero_serial": "SN-QR-1",
        "ubicacion": catalogo["ubicacion_almacen"].pk,
        "usuario_asignado": "",
        "observaciones": "",
    })
    assert r.status_code == 302

    etiqueta.refresh_from_db()
    activo = etiqueta.activo

    assert activo is not None
    assert activo.codigo_inventario == "PAL-LAP-001"
    assert activo.subcategoria_id == etiqueta.subcategoria_id
    assert etiqueta.estado == EtiquetaQR.EstadoEtiqueta.VINCULADA


@pytest.mark.django_db
def test_alta_desde_etiqueta_deja_rastro_en_historial(client_auth, etiqueta, catalogo):
    """A diferencia del alta de escritorio (BR-ACT-11), esta vía sí audita."""
    client_auth.post(reverse("etiqueta-alta", args=[etiqueta.token]), {
        "marca": "Lenovo", "modelo": "T14", "numero_serial": "",
        "ubicacion": catalogo["ubicacion_almacen"].pk,
        "usuario_asignado": "", "observaciones": "",
    })
    etiqueta.refresh_from_db()
    assert HistorialMovimiento.objects.filter(
        activo=etiqueta.activo,
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.CREACION,
    ).exists()


@pytest.mark.django_db
def test_reenviar_el_alta_no_duplica_el_activo(client_auth, etiqueta, catalogo):
    """Mala cobertura en campo: el mismo formulario puede llegar dos veces."""
    datos = {
        "marca": "Lenovo", "modelo": "T14", "numero_serial": "",
        "ubicacion": catalogo["ubicacion_almacen"].pk,
        "usuario_asignado": "", "observaciones": "",
    }
    client_auth.post(reverse("etiqueta-alta", args=[etiqueta.token]), datos)
    client_auth.post(reverse("etiqueta-alta", args=[etiqueta.token]), datos)

    assert Activo.objects.filter(codigo_inventario="PAL-LAP-001").count() == 1


@pytest.mark.django_db
def test_alta_con_responsable_ofrece_la_constancia(client_auth, etiqueta, catalogo):
    r = client_auth.post(reverse("etiqueta-alta", args=[etiqueta.token]), {
        "marca": "Lenovo", "modelo": "T14", "numero_serial": "",
        "ubicacion": catalogo["ubicacion_almacen"].pk,
        "usuario_asignado": catalogo["usuario_a"].pk,
        "observaciones": "",
    })
    assert "constancia=" in r["Location"]


@pytest.mark.django_db
def test_alta_sin_responsable_no_ofrece_constancia(client_auth, etiqueta, catalogo):
    r = client_auth.post(reverse("etiqueta-alta", args=[etiqueta.token]), {
        "marca": "Lenovo", "modelo": "T14", "numero_serial": "",
        "ubicacion": catalogo["ubicacion_almacen"].pk,
        "usuario_asignado": "", "observaciones": "",
    })
    assert "constancia=" not in r["Location"]


# =============================================================================
# Generación e impresión de lotes
# =============================================================================

@pytest.mark.django_db
def test_generar_lote_crea_etiquetas_y_lleva_al_pdf(client_auth, subcategoria):
    r = client_auth.post(reverse("activos:etiqueta-generar"), {
        "subcategoria": subcategoria.pk,
        "cantidad": 5,
    })
    assert r.status_code == 302
    assert reverse("reportes:etiquetas-pdf") in r["Location"]
    assert EtiquetaQR.objects.filter(subcategoria=subcategoria).count() == 5


@pytest.mark.django_db
def test_generar_lote_exige_sesion(client, subcategoria):
    r = client.post(reverse("activos:etiqueta-generar"), {
        "subcategoria": subcategoria.pk, "cantidad": 2,
    })
    assert r.status_code == 302
    assert "login" in r.url.lower()
    assert EtiquetaQR.objects.count() == 0


@pytest.mark.django_db
def test_hoja_de_etiquetas_devuelve_un_pdf(client_auth, subcategoria):
    client_auth.post(reverse("activos:etiqueta-generar"), {
        "subcategoria": subcategoria.pk, "cantidad": 3,
    })
    ids = ",".join(str(pk) for pk in EtiquetaQR.objects.values_list("pk", flat=True))

    r = client_auth.get(f"{reverse('reportes:etiquetas-pdf')}?ids={ids}")

    assert r.status_code == 200
    assert r["Content-Type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")


@pytest.mark.django_db
def test_el_qr_apunta_a_la_url_publica_absoluta(etiqueta, settings):
    from activos.services.qr import url_publica

    settings.PALDACA_PUBLIC_BASE_URL = "https://activos.cpaldaca.com"
    destino = url_publica(etiqueta)

    assert destino == f"https://activos.cpaldaca.com/q/{etiqueta.token}/"
    # La URL impresa debe caber holgada en un adhesivo de 25 mm.
    assert len(destino) < 60


# =============================================================================
# Etiquetado del inventario ya existente
# =============================================================================

@pytest.mark.django_db
def test_comando_etiqueta_activos_existentes(subcategoria, catalogo):
    """Al revés que el flujo normal: el código ya existe, no se aparta uno nuevo."""
    from django.core.management import call_command

    activo = Activo.objects.create(
        subcategoria=subcategoria, marca="M", modelo="X",
        ubicacion=catalogo["ubicacion_almacen"],
    )
    call_command("etiquetar_activos", verbosity=0)

    etiqueta = EtiquetaQR.objects.get(activo=activo)
    assert etiqueta.codigo_reservado == activo.codigo_inventario
    assert etiqueta.estado == EtiquetaQR.EstadoEtiqueta.VINCULADA
    assert etiqueta.fecha_vinculacion is not None


@pytest.mark.django_db
def test_comando_no_duplica_etiquetas(subcategoria, catalogo):
    from django.core.management import call_command

    Activo.objects.create(
        subcategoria=subcategoria, marca="M", modelo="X",
        ubicacion=catalogo["ubicacion_almacen"],
    )
    call_command("etiquetar_activos", verbosity=0)
    call_command("etiquetar_activos", verbosity=0)

    assert EtiquetaQR.objects.count() == 1


@pytest.mark.django_db
def test_comando_dry_run_no_escribe(subcategoria, catalogo):
    from django.core.management import call_command

    Activo.objects.create(
        subcategoria=subcategoria, marca="M", modelo="X",
        ubicacion=catalogo["ubicacion_almacen"],
    )
    call_command("etiquetar_activos", "--dry-run", verbosity=0)

    assert EtiquetaQR.objects.count() == 0


# =============================================================================
# Pantalla de gestión
# =============================================================================

@pytest.mark.django_db
def test_listado_de_etiquetas_pinta_el_qr(client_auth, etiqueta):
    """Cubre la plantilla y el tag: un QR mal formado rompe aquí, no en la calle."""
    r = client_auth.get(reverse("activos:etiqueta-list"))
    cuerpo = _texto(r)

    assert r.status_code == 200
    assert etiqueta.codigo_reservado in cuerpo
    assert "<svg" in cuerpo


@pytest.mark.django_db
def test_listado_de_etiquetas_filtra_por_estado(client_auth, etiqueta, subcategoria):
    otra = EtiquetaQR.objects.create(
        codigo_reservado=reservar_codigos(subcategoria, 1)[0], subcategoria=subcategoria
    )
    otra.anular()

    cuerpo = _texto(client_auth.get(reverse("activos:etiqueta-list"), {"estado": "AN"}))
    assert otra.codigo_reservado in cuerpo
    assert etiqueta.codigo_reservado not in cuerpo


@pytest.mark.django_db
def test_listado_de_etiquetas_exige_sesion(client):
    r = client.get(reverse("activos:etiqueta-list"))
    assert r.status_code == 302
    assert "login" in r.url.lower()
