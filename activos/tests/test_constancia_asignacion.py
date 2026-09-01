"""Planilla de asignación: generación bajo demanda e historial auditable."""

import html
from io import BytesIO

import pytest
from django.core.files.storage import default_storage
from django.urls import reverse
from pypdf import PdfReader

from activos.models import Activo, HistorialMovimiento


def _texto(response):
    return html.unescape(response.content.decode("utf-8"))


def _pdf_texto(content):
    reader = PdfReader(BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _pdf_paginas(content):
    return len(PdfReader(BytesIO(content)).pages)


def _crear_activo(catalogo, codigo, usuario=None, serial=""):
    return Activo.objects.create(
        subcategoria=catalogo["subcategoria"],
        marca="Dell",
        modelo="Latitude",
        numero_serial=serial or codigo,
        codigo_inventario=codigo,
        usuario_asignado=usuario,
        ubicacion=catalogo["ubicacion_almacen"],
        estado=Activo.EstadoActivo.ACTIVO,
    )


@pytest.mark.django_db
def test_reasignar_archiva_planilla_en_historial(client_auth, catalogo):
    act = _crear_activo(catalogo, "INV-PLAN-1")
    url = reverse("activos:activo-reasignar", args=[act.pk])
    r = client_auth.post(
        url, {"usuario_asignado": catalogo["usuario_a"].pk}
    )
    assert r.status_code == 302
    assert f"constancia={act.pk}" in r.url
    reasig = act.historial_movimientos.filter(
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.REASIGNACION
    ).first()
    assert reasig.archivo_planilla
    assert default_storage.exists(reasig.archivo_planilla.name)


@pytest.mark.django_db
def test_editar_formulario_muestra_constancia(client_auth, catalogo):
    act = _crear_activo(catalogo, "INV-EDIT-FORM")
    r = client_auth.post(
        reverse("activos:activo-update", args=[act.pk]),
        {
            "subcategoria": act.subcategoria_id,
            "marca": act.marca,
            "modelo": act.modelo,
            "numero_serial": act.numero_serial,
            "usuario_asignado": catalogo["usuario_a"].pk,
            "ubicacion": act.ubicacion_id,
            "observaciones": "",
            "estado": act.estado,
        },
    )
    assert r.status_code == 302
    assert f"constancia={act.pk}" in r.url
    reasig = act.historial_movimientos.filter(
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.REASIGNACION
    ).first()
    assert reasig.archivo_planilla


@pytest.mark.django_db
def test_descargar_planilla_desde_historial(client_auth, catalogo):
    act = _crear_activo(catalogo, "INV-HIST-DL")
    client_auth.post(
        reverse("activos:activo-reasignar", args=[act.pk]),
        {"usuario_asignado": catalogo["usuario_a"].pk},
    )
    movimiento = act.historial_movimientos.filter(
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.REASIGNACION
    ).first()
    r = client_auth.get(
        reverse("reportes:planilla-historial", args=[movimiento.pk])
    )
    assert r.status_code == 200
    assert r["Content-Type"] == "application/pdf"
    assert 'inline' in r.get("Content-Disposition", "")
    assert 'inline' in r.get("Content-Disposition", "")
    contenido = b"".join(r.streaming_content)
    assert "INV-HIST-DL" in _pdf_texto(contenido)


@pytest.mark.django_db
def test_perfil_muestra_enlace_planilla(client_auth, catalogo):
    act = _crear_activo(
        catalogo, "INV-PLAN-PERFIL", usuario=catalogo["usuario_a"]
    )
    r = client_auth.get(
        reverse("usuarios:usuario-profile", args=[catalogo["usuario_a"].pk])
    )
    assert r.status_code == 200
    cuerpo = _texto(r)
    assert "Ver planilla" in cuerpo
    assert reverse("reportes:planilla-vigente", args=[act.pk]) in cuerpo
    assert reverse("reportes:constancia") in cuerpo


@pytest.mark.django_db
def test_constancia_post_genera_pdf_con_observaciones(client_auth, catalogo):
    act = _crear_activo(
        catalogo, "INV-PLAN-REGEN", usuario=catalogo["usuario_a"]
    )
    r = client_auth.post(
        reverse("reportes:constancia"),
        {
            "activos_seleccionados": [str(act.pk)],
            "observaciones": "Equipo revisado",
        },
    )
    assert r.status_code == 200
    assert r["Content-Type"] == "application/pdf"
    assert 'inline' in r.get("Content-Disposition", "")
    assert r.content.startswith(b"%PDF")
    cuerpo_pdf = _pdf_texto(r.content)
    assert "INV-PLAN-REGEN" in cuerpo_pdf
    assert "Equipo revisado" in cuerpo_pdf
    assert act.historial_movimientos.filter(
        archivo_planilla__isnull=False,
    ).count() == 0


@pytest.mark.django_db
def test_planilla_vigente_genera_pdf_al_vuelo(client_auth, catalogo):
    act = _crear_activo(
        catalogo, "INV-PLAN-GET", usuario=catalogo["usuario_a"]
    )
    r = client_auth.get(reverse("reportes:planilla-vigente", args=[act.pk]))
    assert r.status_code == 200
    assert r["Content-Type"] == "application/pdf"
    assert 'inline' in r.get("Content-Disposition", "")
    assert "INV-PLAN-GET" in _pdf_texto(r.content)


@pytest.mark.django_db
def test_liberar_no_ofrece_constancia(client_auth, catalogo):
    act = _crear_activo(
        catalogo, "INV-PLAN-LIB", usuario=catalogo["usuario_a"]
    )
    client_auth.post(
        reverse("activos:activo-reasignar", args=[act.pk]),
        {"usuario_asignado": catalogo["usuario_b"].pk},
    )
    r = client_auth.post(
        reverse("activos:activo-reasignar", args=[act.pk]),
        {"usuario_asignado": ""},
    )
    assert r.status_code == 302
    assert "constancia=" not in r.url


@pytest.mark.django_db
def test_perfil_varios_equipos_una_sola_planilla(
    client_auth, catalogo
):
    a = _crear_activo(
        catalogo, "INV-KIT-LAP", usuario=catalogo["usuario_a"], serial="SN-LAP"
    )
    b = _crear_activo(
        catalogo, "INV-KIT-MOU", usuario=catalogo["usuario_a"], serial="SN-MOU"
    )
    r = client_auth.post(
        reverse("reportes:constancia"),
        {"activos_seleccionados": [str(a.pk), str(b.pk)]},
    )
    assert r.status_code == 200
    assert r["Content-Type"] == "application/pdf"
    assert 'inline' in r.get("Content-Disposition", "")
    assert _pdf_paginas(r.content) == 1
    cuerpo_pdf = _pdf_texto(r.content)
    assert "INV-KIT-LAP" in cuerpo_pdf
    assert "INV-KIT-MOU" in cuerpo_pdf


@pytest.mark.django_db
def test_constancia_rechaza_responsables_distintos(client_auth, catalogo):
    a = _crear_activo(
        catalogo, "INV-MIX-A", usuario=catalogo["usuario_a"]
    )
    b = _crear_activo(
        catalogo, "INV-MIX-B", usuario=catalogo["usuario_b"]
    )
    r = client_auth.post(
        reverse("reportes:constancia"),
        {"activos_seleccionados": [str(a.pk), str(b.pk)]},
        follow=True,
    )
    assert r.status_code == 200
    assert "una sola persona" in _texto(r).lower()


@pytest.mark.django_db
def test_constancia_rechaza_sin_responsable(client_auth, catalogo):
    act = _crear_activo(catalogo, "INV-SIN-RESP")
    r = client_auth.post(
        reverse("reportes:constancia"),
        {"activos_seleccionados": [str(act.pk)]},
        follow=True,
    )
    assert r.status_code == 200
    assert "sin responsable" in _texto(r).lower()


@pytest.mark.django_db
def test_ficha_sin_responsable_no_muestra_boton_planilla(
    client_auth, catalogo
):
    act = _crear_activo(catalogo, "INV-SIN-BOTON")
    r = client_auth.get(reverse("activos:activo-detail", args=[act.pk]))
    cuerpo = _texto(r)
    assert reverse("reportes:constancia") not in cuerpo
    assert "Planilla de asignación" not in cuerpo


@pytest.mark.django_db
def test_ficha_con_responsable_muestra_boton_planilla(
    client_auth, catalogo
):
    act = _crear_activo(
        catalogo, "INV-CON-BOTON", usuario=catalogo["usuario_a"]
    )
    r = client_auth.get(reverse("activos:activo-detail", args=[act.pk]))
    cuerpo = _texto(r)
    assert reverse("reportes:constancia") in cuerpo
    assert "Planilla de asignación" in cuerpo


@pytest.mark.django_db
def test_get_constancia_descarga_pdf(client_auth, catalogo):
    act = _crear_activo(
        catalogo, "INV-GET-PDF", usuario=catalogo["usuario_a"]
    )
    r = client_auth.get(
        reverse("reportes:constancia") + f"?activos={act.pk}"
    )
    assert r.status_code == 200
    assert r["Content-Type"] == "application/pdf"
    assert 'inline' in r.get("Content-Disposition", "")


@pytest.mark.django_db
def test_aviso_constancia_en_ficha_tras_reasignar(client_auth, catalogo):
    act = _crear_activo(catalogo, "INV-AVISO")
    r = client_auth.post(
        reverse("activos:activo-reasignar", args=[act.pk]),
        {"usuario_asignado": catalogo["usuario_a"].pk},
    )
    ficha = client_auth.get(r.url)
    assert ficha.status_code == 200
    cuerpo = _texto(ficha)
    assert "Planilla lista" in cuerpo
    assert "Imprimir planilla" in cuerpo
