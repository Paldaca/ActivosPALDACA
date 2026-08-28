"""Etiquetas QR: reserva de códigos, ciclo de vida y ficha pública.

El foco está en las dos cosas que pueden hacer daño de verdad si se rompen:
que dos activos acaben con el mismo código de inventario, y que la ficha
pública —la única vista anónima del proyecto— filtre algo que no debe.
"""

import html
import unittest.mock

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


# =============================================================================
# Estilo del símbolo: puntos, ojos redondeados y marca integrada
# =============================================================================

@pytest.mark.django_db
def test_el_svg_dibuja_puntos_ojos_y_marca(etiqueta):
    from activos.services.qr import LOGO_ESTATICO, ROJO, svg_en_linea

    svg = svg_en_linea(etiqueta, tamano_px=160)

    assert "<circle" in svg, "los módulos de datos van como puntos"
    assert svg.count(f'fill="{ROJO}"') >= 6, "tres ojos, anillo y núcleo cada uno"
    assert LOGO_ESTATICO in svg
    assert svg.rstrip().endswith("</svg>")


@pytest.mark.django_db
def test_los_ojos_se_dibujan_macizos_y_nunca_trazados(etiqueta):
    """El fallo que costó encontrar: un anillo trazado NO se lee.

    Dibujar el patrón de búsqueda con `stroke` en vez de con figuras macizas
    superpuestas deforma la proporción 1:1:3:1:1 que el lector usa para
    localizar el símbolo. El código sale bonito y no lo abre ningún teléfono.
    """
    from activos.services.qr import svg_en_linea

    svg = svg_en_linea(etiqueta)

    assert "stroke=" not in svg
    assert 'fill="none"' not in svg


@pytest.mark.django_db
def test_el_hueco_de_la_marca_no_lleva_placa(etiqueta):
    """La marca se integra apoyándose en el hueco, no parcheando encima."""
    from activos.services.qr import HUECO_MODULOS, plano

    p = plano(etiqueta)
    hx, hy, hlado = p.hueco

    assert hlado == HUECO_MODULOS
    # Ningún punto de datos cae dentro del hueco: por eso no hace falta taparlo.
    assert not [
        (x, y) for x, y in p.puntos
        if hx <= x <= hx + hlado and hy <= y <= hy + hlado
    ]


def test_la_correccion_de_errores_soporta_el_estilo():
    """Puntos y hueco central restan información: exige nivel H."""
    from activos.services.qr import NIVEL_CORRECCION

    assert NIVEL_CORRECCION == "h"


def test_el_hueco_no_invade_la_reserva_de_correccion():
    """Frontera medida decodificando símbolos reales con zxing, no teórica.

    9 módulos sobre 41 tapan ~4,8 % del área, muy por debajo del 30 % que
    recupera el nivel H. Si alguien agranda el hueco, esto salta antes que un
    adhesivo ilegible pegado a un equipo.
    """
    from activos.services.qr import DIAMETRO_PUNTO, HUECO_MODULOS

    assert HUECO_MODULOS <= 11
    # Puntos demasiado finos se pierden en papel antes que un cuadrado igual.
    assert DIAMETRO_PUNTO >= 0.8


@pytest.mark.django_db
def test_el_pdf_se_genera_aunque_falte_el_fichero_de_la_marca(etiqueta, monkeypatch):
    """Un despliegue sin la marca debe imprimir etiquetas válidas, no reventar."""
    from reportes.services import etiquetas as servicio

    monkeypatch.setattr(servicio.servicio_qr, "ruta_logo_disco", lambda: None)
    respuesta = servicio.generar_hoja_etiquetas([etiqueta])

    assert respuesta.content.startswith(b"%PDF")


def test_la_marca_existe_y_tiene_fondo_transparente():
    from PIL import Image

    from activos.services.qr import ruta_logo_disco

    ruta = ruta_logo_disco()
    assert ruta is not None, "falta core/static/core/img/marca_cp.png"

    imagen = Image.open(ruta)
    assert imagen.mode == "RGBA"
    # La esquina superior izquierda queda fuera del trazo de la marca.
    assert imagen.getpixel((0, 0))[3] == 0


# =============================================================================
# Enlace al PDF tras generar un lote
# =============================================================================

def _ids_del_enlace(respuesta):
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(respuesta["Location"]).query).get("ids", [""])[0]


@pytest.mark.django_db
def test_generar_lote_enlaza_el_pdf_con_ids_reales(client_auth, subcategoria):
    r = client_auth.post(reverse("activos:etiqueta-generar"), {
        "subcategoria": subcategoria.pk, "cantidad": 3,
    })

    ids = _ids_del_enlace(r)
    esperados = set(EtiquetaQR.objects.values_list("pk", flat=True))

    assert ids, "el enlace al PDF llegó sin ids"
    assert {int(i) for i in ids.split(",")} == esperados


@pytest.mark.django_db
def test_el_lote_no_depende_de_que_bulk_create_devuelva_las_claves(
    client_auth, subcategoria, monkeypatch
):
    """Reproduce sobre SQLite el comportamiento real de MySQL.

    `bulk_create` solo rellena las claves primarias en algunos backends.
    SQLite —donde corren estos tests— sí lo hace; MySQL, que es la base de la
    Suite, no. Por eso una versión anterior generaba el enlace como
    `?ids=None,None,None` y solo fallaba en producción, con el mensaje
    "No indicaste qué etiquetas imprimir".

    Aquí se vacían las claves a propósito: si alguien vuelve a leer los `pk`
    del resultado de `bulk_create`, este test cae.
    """
    original = EtiquetaQR.objects.bulk_create

    def bulk_create_sin_claves(objetos, *args, **kwargs):
        creados = original(objetos, *args, **kwargs)
        for objeto in creados:
            objeto.pk = None
        return creados

    monkeypatch.setattr(EtiquetaQR.objects, "bulk_create", bulk_create_sin_claves)

    r = client_auth.post(reverse("activos:etiqueta-generar"), {
        "subcategoria": subcategoria.pk, "cantidad": 3,
    })

    ids = _ids_del_enlace(r)
    assert ids and "None" not in ids
    assert {int(i) for i in ids.split(",")} == set(
        EtiquetaQR.objects.values_list("pk", flat=True)
    )


@pytest.mark.django_db
def test_el_pdf_del_lote_recien_generado_se_sirve(client_auth, subcategoria):
    """Recorre el flujo completo: generar, seguir el enlace y recibir el PDF."""
    r = client_auth.post(reverse("activos:etiqueta-generar"), {
        "subcategoria": subcategoria.pk, "cantidad": 2,
    })

    pdf = client_auth.get(r["Location"])

    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")


# =============================================================================
# Auditoría: transacción de creación de activo y anulación de etiquetas
# =============================================================================

@pytest.mark.django_db
def test_generar_codigo_y_guardar_ocurren_en_la_misma_transaccion(catalogo, subcategoria):
    """Regresión: el INSERT debe correr bajo el mismo bloqueo que calculó el código.

    `reservar_codigos()` abre y cierra su PROPIO `transaction.atomic()`: el
    `select_for_update()` que toma sobre la subcategoría solo protege mientras
    dura ESE bloque. Si `Activo.save()` no envuelve la generación del código y
    el `super().save()` en una transacción común, el bloqueo se libera justo
    antes del INSERT y dos altas manuales simultáneas para la misma
    subcategoría pueden volver a calcular el mismo siguiente número — la
    misma carrera que el servicio de reserva existe para cerrar.

    SQLite (donde corren estos tests) no implementa `SELECT ... FOR UPDATE`,
    así que no se puede reproducir la colisión con hilos reales. Se verifica
    en su lugar la propiedad que la hace imposible: que sigue abierta una
    transacción de `Activo.save()` en el momento en que `reservar_codigos()`
    hace su propia llamada interna a `transaction.atomic()` — es decir, que
    esta anida como savepoint dentro de la de `save()`, y no al revés.
    """
    from django.db import connection

    from activos.services import codigos as servicio_codigos

    profundidades = []
    original = servicio_codigos.reservar_codigos

    def envoltura(*args, **kwargs):
        profundidades.append(len(connection.savepoint_ids))
        return original(*args, **kwargs)

    with unittest.mock.patch.object(
        servicio_codigos, "reservar_codigos", side_effect=envoltura
    ):
        # `Activo._generar_codigo_inventario` importa la función dentro del
        # cuerpo del método, así que parchear el módulo del servicio basta.
        Activo.objects.create(
            subcategoria=subcategoria, marca="M", modelo="X",
            ubicacion=catalogo["ubicacion_almacen"],
        )

    assert profundidades, "reservar_codigos() no se llamó — revisa el parche"
    # >= 1 savepoint activo cuando entra reservar_codigos() prueba que YA
    # había una transacción abierta por Activo.save() antes de que el
    # servicio abriera la suya propia (que añadirá un segundo savepoint).
    assert profundidades[0] >= 1


@pytest.mark.django_db
def test_anular_etiqueta_vinculada_deja_rastro_en_historial(
    client_auth, etiqueta, catalogo, subcategoria
):
    """El listado permite anular directamente una etiqueta vinculada, sin
    pasar primero por 'Desvincular'. Ese atajo no debe perder auditoría.
    """
    activo = Activo.objects.create(
        subcategoria=subcategoria, marca="M", modelo="X",
        ubicacion=catalogo["ubicacion_almacen"],
    )
    etiqueta.vincular(activo)

    r = client_auth.post(reverse("activos:etiqueta-anular", args=[etiqueta.pk]))

    assert r.status_code == 302
    etiqueta.refresh_from_db()
    assert etiqueta.estado == EtiquetaQR.EstadoEtiqueta.ANULADA
    assert HistorialMovimiento.objects.filter(
        activo=activo,
        descripcion__icontains="anulada",
    ).exists()


@pytest.mark.django_db
def test_anular_etiqueta_pendiente_no_falla_sin_activo(client_auth, etiqueta):
    """Caso normal: anular una etiqueta que nunca se vinculó no debe reventar
    por intentar registrar historial sin activo al que atárselo.
    """
    r = client_auth.post(reverse("activos:etiqueta-anular", args=[etiqueta.pk]))

    assert r.status_code == 302
    etiqueta.refresh_from_db()
    assert etiqueta.estado == EtiquetaQR.EstadoEtiqueta.ANULADA


# =============================================================================
# Botones de la pantalla de gestión: visibles y con destino correcto
# =============================================================================

@pytest.mark.django_db
def test_boton_imprimir_no_usa_el_estilo_translucido(client_auth, etiqueta):
    """El estilo `--glass` es blanco translúcido, pensado para fondos de color
    (el hero). Sobre una fila de tabla blanca queda invisible: ese fue el
    motivo real por el que parecía no existir un botón para imprimir.
    """
    cuerpo = _texto(client_auth.get(reverse("activos:etiqueta-list")))
    assert "btn-pastel--glass" not in cuerpo


@pytest.mark.django_db
def test_fila_de_etiqueta_ofrece_imprimir_y_cargar_datos(client_auth, etiqueta):
    r = client_auth.get(reverse("activos:etiqueta-list"))
    cuerpo = _texto(r)

    assert f"ids={etiqueta.pk}" in cuerpo
    assert reverse("etiqueta-alta", args=[etiqueta.token]) in cuerpo


@pytest.mark.django_db
def test_fila_vinculada_ofrece_desvincular_en_el_menu(
    client_auth, etiqueta, catalogo, subcategoria
):
    activo = Activo.objects.create(
        subcategoria=subcategoria, marca="M", modelo="X",
        ubicacion=catalogo["ubicacion_almacen"],
    )
    etiqueta.vincular(activo)

    cuerpo = _texto(client_auth.get(reverse("activos:etiqueta-list")))
    assert reverse("activos:etiqueta-desvincular", args=[etiqueta.pk]) in cuerpo
    # Sin la etiqueta vinculada no se ofrece "Cargar datos": ya tiene sus datos.
    assert reverse("etiqueta-alta", args=[etiqueta.token]) not in cuerpo


@pytest.mark.django_db
def test_listado_de_etiquetas_usa_tarjetas_con_acciones_integradas(client_auth, etiqueta):
    """El listado ya no usa tabla + columna sticky `ax-col-actions`: cada
    etiqueta es una tarjeta con QR, estado y acciones en el propio pie.
    Así se evita el desborde móvil y se mantiene imprimir / cargar datos.
    """
    cuerpo = _texto(client_auth.get(reverse("activos:etiqueta-list")))
    assert "ax-etiqueta-card" in cuerpo
    assert "ax-etiqueta-grid" in cuerpo
    assert "ax-col-actions" not in cuerpo
    assert "Cargar datos" in cuerpo
    assert "ax-etiqueta-chips" in cuerpo


@pytest.mark.django_db
def test_filtro_por_estado_pendiente(client_auth, etiqueta):
    cuerpo = _texto(client_auth.get(reverse("activos:etiqueta-list"), {"estado": "PE"}))
    assert etiqueta.codigo_reservado in cuerpo
    assert "Filtros activos" in cuerpo
    assert "Pendiente" in cuerpo


# =============================================================================
# Caché del navegador: el CSS/JS versionado evita servir copias viejas
# =============================================================================

@pytest.mark.django_db
def test_el_listado_de_etiquetas_carga_css_con_version(client_auth, etiqueta):
    """Sin esto, un navegador puede seguir pintando una hoja de estilos vieja
    después de un cambio de código — pasó varias veces depurando esta misma
    pantalla: el fix ya estaba en el servidor y la pestaña no lo mostraba.
    """
    cuerpo = _texto(client_auth.get(reverse("activos:etiqueta-list")))
    assert "activos-ui.css?v=" in cuerpo
    assert "activos-ui.js?v=" in cuerpo
