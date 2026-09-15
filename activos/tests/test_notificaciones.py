"""Avisos al bus de notificaciones del Portal (alta y asignación de activos)."""

import urllib.error
from unittest import mock

import pytest
from django.urls import reverse

from activos.models import Activo
from activos.services import notificaciones_portal
from activos.services.avisos import CODIGO_ACTIVO_ASIGNADO, CODIGO_ACTIVO_CREADO
from activos.tests.test_activo_flow import _payload_activo


@pytest.fixture
def emitir():
    with mock.patch.object(notificaciones_portal, "emitir_evento") as emitir:
        yield emitir


def _crear_activo(catalogo, codigo, usuario=None):
    return Activo.objects.create(
        subcategoria=catalogo["subcategoria"],
        marca="Dell",
        modelo="Latitude",
        codigo_inventario=codigo,
        usuario_asignado=usuario,
        ubicacion=catalogo["ubicacion_almacen"],
        estado=Activo.EstadoActivo.ACTIVO,
    )


def _llamadas(emitir, codigo):
    return [c.kwargs for c in emitir.call_args_list if c.kwargs["codigo"] == codigo]


def test_vector_de_firma_compartido_con_el_portal(settings):
    # Mismo vector que backend/notificaciones/tests.py del Portal.
    settings.SECRET_KEY = "clave-de-prueba-paldaca"
    assert (
        notificaciones_portal.firmar(b'{"codigo": "x"}', "hdt", "1700000000")
        == "3a9d0e031e7a715ce0336a9820b5f5afa39307eea7e5e78850b35b9b8f7b8a0d"
    )


@pytest.mark.django_db
def test_alta_con_custodio_emite_un_solo_aviso_con_su_id(
    client_auth, catalogo, user, emitir, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        r = client_auth.post(reverse("activos:activo-create"), _payload_activo(catalogo))
    assert r.status_code == 302
    act = Activo.objects.get(marca="MarcaPy")

    [aviso] = _llamadas(emitir, CODIGO_ACTIVO_CREADO)
    assert aviso["payload"]["usuario_ids"] == [catalogo["usuario_a"].pk]
    assert aviso["payload"]["activo_id"] == act.pk
    assert aviso["payload"]["url"].endswith(f"/activos/activos/{act.pk}/")
    assert aviso["emisor"] == user
    assert _llamadas(emitir, CODIGO_ACTIVO_ASIGNADO) == []


@pytest.mark.django_db
def test_alta_sin_custodio_solo_llega_a_admins(
    client_auth, catalogo, emitir, django_capture_on_commit_callbacks
):
    datos = _payload_activo(catalogo, usuario_asignado="")
    with django_capture_on_commit_callbacks(execute=True):
        client_auth.post(reverse("activos:activo-create"), datos)
    [aviso] = _llamadas(emitir, CODIGO_ACTIVO_CREADO)
    assert "usuario_ids" not in aviso["payload"]


@pytest.mark.django_db
def test_reasignar_avisa_al_nuevo_custodio(
    client_auth, catalogo, emitir, django_capture_on_commit_callbacks
):
    act = _crear_activo(catalogo, "INV-NOTIF-1", catalogo["usuario_a"])
    with django_capture_on_commit_callbacks(execute=True):
        client_auth.post(
            reverse("activos:activo-reasignar", args=[act.pk]),
            {"usuario_asignado": catalogo["usuario_b"].pk},
        )
    [aviso] = _llamadas(emitir, CODIGO_ACTIVO_ASIGNADO)
    assert aviso["payload"]["usuario_ids"] == [catalogo["usuario_b"].pk]
    assert "INV-NOTIF-1" in aviso["titulo"]
    assert "Luis" not in aviso["cuerpo"]  # el cuerpo nombra a quien asigna, no al custodio


@pytest.mark.django_db
def test_reasignar_al_mismo_custodio_o_desasignar_no_avisa(
    client_auth, catalogo, emitir, django_capture_on_commit_callbacks
):
    act = _crear_activo(catalogo, "INV-NOTIF-2", catalogo["usuario_a"])
    url = reverse("activos:activo-reasignar", args=[act.pk])
    with django_capture_on_commit_callbacks(execute=True):
        client_auth.post(url, {"usuario_asignado": catalogo["usuario_a"].pk})
        client_auth.post(url, {"usuario_asignado": ""})
    assert _llamadas(emitir, CODIGO_ACTIVO_ASIGNADO) == []


@pytest.mark.django_db
def test_asignacion_masiva_agrupa_en_un_aviso(
    client_auth, catalogo, emitir, django_capture_on_commit_callbacks
):
    activos = [_crear_activo(catalogo, f"INV-LOTE-{i}") for i in range(3)]
    with django_capture_on_commit_callbacks(execute=True):
        client_auth.post(
            reverse("activos:activo-acciones-masivas"),
            {
                "accion": "reasignar",
                "activos": [a.pk for a in activos],
                "destino": catalogo["usuario_b"].pk,
            },
        )
    [aviso] = _llamadas(emitir, CODIGO_ACTIVO_ASIGNADO)
    assert aviso["titulo"] == "Se te asignaron 3 activos"
    assert sorted(aviso["payload"]["activo_ids"]) == sorted(a.pk for a in activos)
    assert f"usuario_asignado={catalogo['usuario_b'].pk}" in aviso["payload"]["url"]


@pytest.mark.django_db
def test_portal_caido_no_impide_el_alta(
    client_auth, catalogo, settings, django_capture_on_commit_callbacks
):
    settings.PALDACA_NOTIFICACIONES_ACTIVAS = True
    settings.PALDACA_PORTAL_API_URL = "http://portal.test/api"
    with mock.patch.object(
        notificaciones_portal.urllib.request,
        "urlopen",
        side_effect=urllib.error.URLError("caido"),
    ) as urlopen:
        with django_capture_on_commit_callbacks(execute=True):
            r = client_auth.post(reverse("activos:activo-create"), _payload_activo(catalogo))
    assert r.status_code == 302
    assert Activo.objects.filter(marca="MarcaPy").exists()
    urlopen.assert_called_once()
