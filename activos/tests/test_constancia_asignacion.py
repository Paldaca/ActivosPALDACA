"""Planilla de asignación: generación, vigencia e historial."""

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
def test_reasignar_guarda_planilla_vigente(client_auth, catalogo):
    act = _crear_activo(catalogo, "INV-PLAN-1")
    url = reverse("activos:activo-reasignar", args=[act.pk])
    r = client_auth.post(
        url, {"usuario_asignado": catalogo["usuario_a"].pk}
    )
    assert r.status_code == 302
    assert f"constancia={act.pk}" in r.url
    act.refresh_from_db()
    assert act.planilla_pdf
    assert default_storage.exists(act.planilla_pdf.name)
    reasig = act.historial_movimientos.filter(
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.REASIGNACION
    ).first()
    assert reasig.archivo_planilla
    assert reasig.archivo_planilla.name == act.planilla_pdf.name


@pytest.mark.django_db
def test_perfil_muestra_planilla_vigente(client_auth, catalogo):
    act = _crear_activo(catalogo, "INV-PLAN-PERFIL")
    client_auth.post(
        reverse("activos:activo-reasignar", args=[act.pk]),
        {"usuario_asignado": catalogo["usuario_a"].pk},
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
def test_regenerar_reemplaza_vigente_y_conserva_historial(
    client_auth, catalogo
):
    act = _crear_activo(catalogo, "INV-PLAN-REGEN")
    client_auth.post(
        reverse("activos:activo-reasignar", args=[act.pk]),
        {"usuario_asignado": catalogo["usuario_a"].pk},
    )
    act.refresh_from_db()
    anterior = act.planilla_pdf.name
    assert anterior

    r = client_auth.post(
        reverse("reportes:constancia"),
        {
            "activos_seleccionados": [str(act.pk)],
            "observaciones": "Equipo revisado",
        },
    )
    assert r.status_code == 200
    assert r["Content-Type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    cuerpo_pdf = _pdf_texto(r.content)
    assert "INV-PLAN-REGEN" in cuerpo_pdf
    assert "Equipo revisado" in cuerpo_pdf

    act.refresh_from_db()
    assert act.planilla_pdf.name != anterior
    assert default_storage.exists(anterior)
    assert default_storage.exists(act.planilla_pdf.name)

    reasig = act.historial_movimientos.get(
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.REASIGNACION
    )
    planilla = act.historial_movimientos.get(
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.PLANILLA
    )
    assert reasig.archivo_planilla.name == anterior
    assert planilla.archivo_planilla.name == act.planilla_pdf.name


@pytest.mark.django_db
def test_liberar_limpia_planilla_vigente(client_auth, catalogo):
    act = _crear_activo(
        catalogo, "INV-PLAN-LIB", usuario=catalogo["usuario_a"]
    )
    client_auth.post(
        reverse("activos:activo-reasignar", args=[act.pk]),
        {"usuario_asignado": catalogo["usuario_b"].pk},
    )
    act.refresh_from_db()
    assert act.planilla_pdf

    r = client_auth.post(
        reverse("activos:activo-reasignar", args=[act.pk]),
        {"usuario_asignado": ""},
    )
    assert r.status_code == 302
    assert "constancia=" not in r.url
    act.refresh_from_db()
    assert not act.planilla_pdf


@pytest.mark.django_db
def test_perfil_varios_equipos_una_planilla_por_pagina(
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
    assert _pdf_paginas(r.content) == 2
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
def test_get_constancia_descarga_pdf_sin_guardar_otra_vez(
    client_auth, catalogo
):
    act = _crear_activo(catalogo, "INV-GET-PDF")
    client_auth.post(
        reverse("activos:activo-reasignar", args=[act.pk]),
        {"usuario_asignado": catalogo["usuario_a"].pk},
    )
    r = client_auth.get(
        reverse("reportes:constancia") + f"?activos={act.pk}"
    )
    assert r.status_code == 200
    assert r["Content-Type"] == "application/pdf"
    assert act.historial_movimientos.filter(
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.PLANILLA
    ).count() == 0


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
