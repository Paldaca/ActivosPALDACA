"""Avisos al bus de notificaciones del Portal (alta y asignación de activos)."""

import urllib.error
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from activos.models import Activo, AvisoUsuarioInactivo
from activos.services import notificaciones_portal
from activos.services.avisos import (
    CODIGO_ACTIVO_ASIGNADO,
    CODIGO_ACTIVO_CREADO,
    CODIGO_USUARIO_INACTIVO,
    avisar_usuarios_inactivos_con_equipos,
    usuarios_inactivos_con_equipos,
)
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
    assert aviso["payload"]["url"].endswith(f"/activos/mis-activos/{act.pk}/")


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
    # Deep link a "Mis Activos": el custodio puede no ser administrador y no
    # tiene por qué poder abrir el listado general filtrado por query param.
    assert aviso["payload"]["url"].endswith("/activos/mis-activos/")


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


# =============================================================================
# usuario_inactivo_con_equipos (regla por reloj — enviar_notificaciones_activos)
# =============================================================================


def _desactivar(usuario):
    usuario.is_active = False
    usuario.save(update_fields=["is_active"])


@pytest.mark.django_db
def test_usuario_activo_con_equipos_no_es_candidato(catalogo):
    _crear_activo(catalogo, "INV-INACT-1", catalogo["usuario_a"])
    assert usuarios_inactivos_con_equipos() == []


@pytest.mark.django_db
def test_usuario_inactivo_sin_equipos_no_es_candidato(catalogo):
    _desactivar(catalogo["usuario_a"])
    assert usuarios_inactivos_con_equipos() == []


@pytest.mark.django_db
def test_usuario_inactivo_con_equipos_es_candidato(catalogo):
    _crear_activo(catalogo, "INV-INACT-2", catalogo["usuario_a"])
    _desactivar(catalogo["usuario_a"])
    assert usuarios_inactivos_con_equipos() == [catalogo["usuario_a"]]


@pytest.mark.django_db
def test_avisa_un_solo_usuario_con_deep_link_a_su_ficha(catalogo, emitir):
    _crear_activo(catalogo, "INV-INACT-3", catalogo["usuario_a"])
    _crear_activo(catalogo, "INV-INACT-4", catalogo["usuario_a"])
    _desactivar(catalogo["usuario_a"])

    avisados = avisar_usuarios_inactivos_con_equipos()

    assert avisados == 1
    [aviso] = _llamadas(emitir, CODIGO_USUARIO_INACTIVO)
    assert aviso["payload"]["usuario_ids"] == [catalogo["usuario_a"].pk]
    assert aviso["payload"]["url"].endswith(f"/usuarios/{catalogo['usuario_a'].pk}/perfil/")
    assert "2 equipos" in aviso["titulo"]
    assert AvisoUsuarioInactivo.objects.filter(usuario=catalogo["usuario_a"]).exists()


@pytest.mark.django_db
def test_avisa_varios_usuarios_en_un_solo_evento(catalogo, emitir):
    _crear_activo(catalogo, "INV-INACT-5", catalogo["usuario_a"])
    _crear_activo(catalogo, "INV-INACT-6", catalogo["usuario_b"])
    _desactivar(catalogo["usuario_a"])
    _desactivar(catalogo["usuario_b"])

    avisados = avisar_usuarios_inactivos_con_equipos()

    assert avisados == 2
    [aviso] = _llamadas(emitir, CODIGO_USUARIO_INACTIVO)
    assert sorted(aviso["payload"]["usuario_ids"]) == sorted(
        [catalogo["usuario_a"].pk, catalogo["usuario_b"].pk]
    )
    assert aviso["payload"]["url"].endswith("/usuarios/")


@pytest.mark.django_db
def test_no_repite_el_aviso_mientras_sigue_inactivo(catalogo, emitir):
    _crear_activo(catalogo, "INV-INACT-7", catalogo["usuario_a"])
    _desactivar(catalogo["usuario_a"])

    assert avisar_usuarios_inactivos_con_equipos() == 1
    assert avisar_usuarios_inactivos_con_equipos() == 0
    assert len(_llamadas(emitir, CODIGO_USUARIO_INACTIVO)) == 1


@pytest.mark.django_db
def test_vuelve_a_avisar_si_se_reactiva_y_recae(catalogo, emitir):
    """El marcador se libera en la corrida que ve al usuario ya reactivado.

    Si la reactivación y la nueva baja ocurren entre dos corridas del
    despachador (sin ninguna corrida en medio que la detecte), el sistema no
    tiene forma de saberlo: solo ve el estado actual. Por eso esta prueba
    simula la corrida diaria que sí alcanza a ver la reactivación.
    """
    _crear_activo(catalogo, "INV-INACT-8", catalogo["usuario_a"])
    _desactivar(catalogo["usuario_a"])
    assert avisar_usuarios_inactivos_con_equipos() == 1

    catalogo["usuario_a"].is_active = True
    catalogo["usuario_a"].save(update_fields=["is_active"])
    # Corrida intermedia: limpia el marcador (usuario activo, sin candidatos).
    assert avisar_usuarios_inactivos_con_equipos() == 0
    assert not AvisoUsuarioInactivo.objects.filter(usuario=catalogo["usuario_a"]).exists()

    _desactivar(catalogo["usuario_a"])

    assert avisar_usuarios_inactivos_con_equipos() == 1
    assert len(_llamadas(emitir, CODIGO_USUARIO_INACTIVO)) == 2


@pytest.mark.django_db
def test_deja_de_avisar_si_pierde_todo_el_equipo(catalogo, emitir):
    activo = _crear_activo(catalogo, "INV-INACT-9", catalogo["usuario_a"])
    _desactivar(catalogo["usuario_a"])
    assert avisar_usuarios_inactivos_con_equipos() == 1

    activo.usuario_asignado = None
    activo.save(update_fields=["usuario_asignado"])

    assert AvisoUsuarioInactivo.objects.filter(usuario=catalogo["usuario_a"]).exists()
    assert avisar_usuarios_inactivos_con_equipos() == 0
    assert not AvisoUsuarioInactivo.objects.filter(usuario=catalogo["usuario_a"]).exists()


@pytest.mark.django_db
def test_sin_candidatos_no_llama_al_portal(catalogo, emitir):
    assert avisar_usuarios_inactivos_con_equipos() == 0
    emitir.assert_not_called()


@pytest.mark.django_db
def test_comando_dry_run_no_envia_nada(catalogo, emitir):
    _crear_activo(catalogo, "INV-INACT-10", catalogo["usuario_a"])
    _desactivar(catalogo["usuario_a"])

    salida = StringIO()
    call_command(
        "enviar_notificaciones_activos",
        "--dry-run",
        "--ahora",
        stdout=salida,
    )
    emitir.assert_not_called()
    assert "se avisaría por 1 usuario" in salida.getvalue()


@pytest.mark.django_db
def test_comando_respeta_el_horario_salvo_con_ahora(catalogo, settings, emitir):
    _crear_activo(catalogo, "INV-INACT-11", catalogo["usuario_a"])
    _desactivar(catalogo["usuario_a"])

    hora_equivocada = (timezone.localtime().hour + 1) % 24
    with mock.patch(
        "activos.management.commands.enviar_notificaciones_activos.timezone.localtime"
    ) as localtime:
        localtime.return_value = timezone.localtime().replace(hour=hora_equivocada)
        call_command("enviar_notificaciones_activos")
    emitir.assert_not_called()

    call_command("enviar_notificaciones_activos", "--regla", "usuario_inactivo_con_equipos", "--ahora")
    emitir.assert_called_once()
