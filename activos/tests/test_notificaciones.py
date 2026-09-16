"""Avisos al bus de notificaciones del Portal (alta y asignación de activos)."""

import urllib.error
from datetime import timedelta
from io import StringIO
from unittest import mock

import pytest
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from activos.models import (
    Activo,
    AvisoPorUmbral,
    AvisoUsuarioInactivo,
    EtiquetaQR,
    HistorialMovimiento,
)
from activos.services import notificaciones_portal
from activos.services.avisos import (
    CODIGO_ACTIVO_ASIGNADO,
    CODIGO_ACTIVO_BAJA,
    CODIGO_ACTIVO_CREADO,
    CODIGO_ACTIVO_DESASIGNADO,
    CODIGO_ASIGNACION_SIN_PLANILLA,
    CODIGO_ETIQUETA_SIN_VINCULAR,
    CODIGO_MANTENIMIENTO_FINALIZADO,
    CODIGO_MANTENIMIENTO_INICIADO,
    CODIGO_USUARIO_INACTIVO,
    asignaciones_sin_planilla,
    avisar_asignaciones_sin_planilla,
    avisar_etiquetas_sin_vincular,
    avisar_usuarios_inactivos_con_equipos,
    etiquetas_sin_vincular,
    usuarios_inactivos_con_equipos,
)
from mantenimientos.models import Mantenimiento
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
def test_reasignar_avisa_al_nuevo_custodio_y_desasigna_al_anterior(
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

    [desaviso] = _llamadas(emitir, CODIGO_ACTIVO_DESASIGNADO)
    assert desaviso["payload"]["usuario_ids"] == [catalogo["usuario_a"].pk]
    assert "INV-NOTIF-1" in desaviso["titulo"]
    assert desaviso["payload"]["url"].endswith("/activos/mis-activos/")


@pytest.mark.django_db
def test_reasignar_al_mismo_custodio_no_avisa_nada(
    client_auth, catalogo, emitir, django_capture_on_commit_callbacks
):
    act = _crear_activo(catalogo, "INV-NOTIF-2", catalogo["usuario_a"])
    url = reverse("activos:activo-reasignar", args=[act.pk])
    with django_capture_on_commit_callbacks(execute=True):
        client_auth.post(url, {"usuario_asignado": catalogo["usuario_a"].pk})
    assert _llamadas(emitir, CODIGO_ACTIVO_ASIGNADO) == []
    assert _llamadas(emitir, CODIGO_ACTIVO_DESASIGNADO) == []


@pytest.mark.django_db
def test_reasignar_a_vacio_avisa_desasignado_al_anterior(
    client_auth, catalogo, emitir, django_capture_on_commit_callbacks
):
    act = _crear_activo(catalogo, "INV-NOTIF-2b", catalogo["usuario_a"])
    url = reverse("activos:activo-reasignar", args=[act.pk])
    with django_capture_on_commit_callbacks(execute=True):
        client_auth.post(url, {"usuario_asignado": ""})
    assert _llamadas(emitir, CODIGO_ACTIVO_ASIGNADO) == []
    [desaviso] = _llamadas(emitir, CODIGO_ACTIVO_DESASIGNADO)
    assert desaviso["payload"]["usuario_ids"] == [catalogo["usuario_a"].pk]


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
def test_asignacion_masiva_agrupa_desasignados_por_custodio_anterior(
    client_auth, catalogo, emitir, django_capture_on_commit_callbacks
):
    """Dos activos de usuario_a y uno de usuario_b, todos van a un tercero.

    Deben salir dos avisos de "ya no tienes a tu cargo": uno para usuario_a
    (agrupando sus 2 equipos) y otro para usuario_b (1 equipo) — no uno por
    activo.
    """
    de_a = [_crear_activo(catalogo, f"INV-LOTE-A{i}", catalogo["usuario_a"]) for i in range(2)]
    de_b = [_crear_activo(catalogo, "INV-LOTE-B1", catalogo["usuario_b"])]
    with django_capture_on_commit_callbacks(execute=True):
        client_auth.post(
            reverse("activos:activo-acciones-masivas"),
            {
                "accion": "reasignar",
                "activos": [a.pk for a in de_a + de_b],
                "destino": catalogo["usuario_b"].pk,
            },
        )
    avisos = _llamadas(emitir, CODIGO_ACTIVO_DESASIGNADO)
    assert len(avisos) == 1
    [aviso_a] = avisos
    assert aviso_a["payload"]["usuario_ids"] == [catalogo["usuario_a"].pk]
    assert sorted(aviso_a["payload"]["activo_ids"]) == sorted(a.pk for a in de_a)
    assert aviso_a["titulo"] == "Ya no tienes a tu cargo 2 activos"
    # usuario_b no se desasigna nada: ya tenía INV-LOTE-B1 y sigue siendo el
    # destino de la masiva, así que ese activo no cambia de dueño.


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
# Fase 1: mantenimiento, baja y eliminación (avisos de hecho)
# =============================================================================


def _crear_mantenimiento(activo, estado=Mantenimiento.EstadoMantenimiento.EN_PROCESO):
    return Mantenimiento.objects.create(
        activo=activo,
        tecnico="Técnico Pytest",
        telefono="000-0000",
        descripcion="Revisión de rutina",
        costo="10.00",
        estado=estado,
    )


@pytest.mark.django_db
def test_mantenimiento_iniciado_avisa_al_custodio(
    client_auth, catalogo, emitir, django_capture_on_commit_callbacks
):
    act = _crear_activo(catalogo, "INV-MNT-1", catalogo["usuario_a"])
    with django_capture_on_commit_callbacks(execute=True):
        client_auth.post(
            reverse("mantenimientos:mantenimiento-create"),
            {
                "activo": act.pk,
                "tecnico": "Juan Técnico",
                "telefono": "555-1234",
                "descripcion": "Cambio de pantalla",
                "costo": "50.00",
                "estado": Mantenimiento.EstadoMantenimiento.EN_PROCESO,
            },
        )
    [aviso] = _llamadas(emitir, CODIGO_MANTENIMIENTO_INICIADO)
    assert aviso["payload"]["usuario_ids"] == [catalogo["usuario_a"].pk]
    assert aviso["payload"]["url"].endswith(f"/activos/mis-activos/{act.pk}/")
    assert "INV-MNT-1" in aviso["titulo"]


@pytest.mark.django_db
def test_mantenimiento_sin_custodio_no_avisa(
    client_auth, catalogo, emitir, django_capture_on_commit_callbacks
):
    act = _crear_activo(catalogo, "INV-MNT-2")
    with django_capture_on_commit_callbacks(execute=True):
        client_auth.post(
            reverse("mantenimientos:mantenimiento-create"),
            {
                "activo": act.pk,
                "tecnico": "Juan Técnico",
                "telefono": "555-1234",
                "descripcion": "Cambio de pantalla",
                "costo": "50.00",
                "estado": Mantenimiento.EstadoMantenimiento.EN_PROCESO,
            },
        )
    assert _llamadas(emitir, CODIGO_MANTENIMIENTO_INICIADO) == []


@pytest.mark.django_db
def test_finalizar_mantenimiento_avisa_al_custodio(
    client_auth, catalogo, emitir, django_capture_on_commit_callbacks
):
    act = _crear_activo(catalogo, "INV-MNT-3", catalogo["usuario_a"])
    mant = _crear_mantenimiento(act)
    with django_capture_on_commit_callbacks(execute=True):
        client_auth.post(reverse("mantenimientos:mantenimiento-finalizar", args=[mant.pk]))
    [aviso] = _llamadas(emitir, CODIGO_MANTENIMIENTO_FINALIZADO)
    assert aviso["payload"]["usuario_ids"] == [catalogo["usuario_a"].pk]
    assert aviso["payload"]["url"].endswith(f"/activos/mis-activos/{act.pk}/")
    assert "INV-MNT-3" in aviso["titulo"]


@pytest.mark.django_db
def test_finalizar_mantenimiento_ya_finalizado_no_avisa_de_nuevo(
    client_auth, catalogo, emitir, django_capture_on_commit_callbacks
):
    act = _crear_activo(catalogo, "INV-MNT-4", catalogo["usuario_a"])
    mant = _crear_mantenimiento(act, estado=Mantenimiento.EstadoMantenimiento.FINALIZADO)
    with django_capture_on_commit_callbacks(execute=True):
        client_auth.post(reverse("mantenimientos:mantenimiento-finalizar", args=[mant.pk]))
    assert _llamadas(emitir, CODIGO_MANTENIMIENTO_FINALIZADO) == []


@pytest.mark.django_db
def test_editar_a_inactivo_avisa_baja_a_custodio(
    client_auth, catalogo, emitir, django_capture_on_commit_callbacks
):
    act = _crear_activo(catalogo, "INV-BAJA-1", catalogo["usuario_a"])
    data = _payload_activo(
        catalogo,
        codigo_inventario="INV-BAJA-1",
        usuario_asignado=catalogo["usuario_a"].pk,
        estado=Activo.EstadoActivo.INACTIVO,
    )
    with django_capture_on_commit_callbacks(execute=True):
        client_auth.post(reverse("activos:activo-update", args=[act.pk]), data)
    [aviso] = _llamadas(emitir, CODIGO_ACTIVO_BAJA)
    assert aviso["payload"]["usuario_ids"] == [catalogo["usuario_a"].pk]
    assert aviso["payload"]["activo_id"] == act.pk
    assert "INV-BAJA-1" in aviso["titulo"]
    assert aviso["payload"]["url"].endswith(f"/activos/activos/{act.pk}/")


@pytest.mark.django_db
def test_editar_sin_cambiar_estado_no_avisa_baja(
    client_auth, catalogo, emitir, django_capture_on_commit_callbacks
):
    act = _crear_activo(catalogo, "INV-BAJA-2", catalogo["usuario_a"])
    data = _payload_activo(
        catalogo,
        codigo_inventario="INV-BAJA-2",
        usuario_asignado=catalogo["usuario_a"].pk,
        marca="Marca actualizada",
        estado=Activo.EstadoActivo.ACTIVO,
    )
    with django_capture_on_commit_callbacks(execute=True):
        client_auth.post(reverse("activos:activo-update", args=[act.pk]), data)
    assert _llamadas(emitir, CODIGO_ACTIVO_BAJA) == []


@pytest.mark.django_db
def test_eliminar_activo_avisa_antes_de_borrar_la_fila(
    client_auth, catalogo, emitir, django_capture_on_commit_callbacks
):
    act = _crear_activo(catalogo, "INV-BAJA-3", catalogo["usuario_a"])
    pk = act.pk
    with django_capture_on_commit_callbacks(execute=True):
        client_auth.post(reverse("activos:activo-delete", args=[pk]))
    assert not Activo.objects.filter(pk=pk).exists()
    [aviso] = _llamadas(emitir, CODIGO_ACTIVO_BAJA)
    assert aviso["payload"]["usuario_ids"] == [catalogo["usuario_a"].pk]
    assert aviso["payload"]["activo_id"] == pk
    assert aviso["payload"]["codigo_activo"] == "INV-BAJA-3"
    assert aviso["payload"]["url"].endswith("/activos/activos/")


@pytest.mark.django_db
def test_eliminar_activo_sin_custodio_no_incluye_usuario_ids(
    client_auth, catalogo, emitir, django_capture_on_commit_callbacks
):
    act = _crear_activo(catalogo, "INV-BAJA-4")
    with django_capture_on_commit_callbacks(execute=True):
        client_auth.post(reverse("activos:activo-delete", args=[act.pk]))
    [aviso] = _llamadas(emitir, CODIGO_ACTIVO_BAJA)
    assert "usuario_ids" not in aviso["payload"]


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


# =============================================================================
# etiqueta_sin_vincular (regla por reloj)
# =============================================================================


def _crear_etiqueta(catalogo, codigo, *, creada_por=None, dias_atras=0, estado=None):
    etiqueta = EtiquetaQR.objects.create(
        codigo_reservado=codigo,
        subcategoria=catalogo["subcategoria"],
        creada_por=creada_por,
        estado=estado or EtiquetaQR.EstadoEtiqueta.PENDIENTE,
    )
    if dias_atras:
        EtiquetaQR.objects.filter(pk=etiqueta.pk).update(
            fecha_creacion=timezone.now() - timedelta(days=dias_atras)
        )
        etiqueta.refresh_from_db()
    return etiqueta


@pytest.mark.django_db
def test_etiqueta_reciente_no_es_candidata(catalogo):
    _crear_etiqueta(catalogo, "INV-ETQ-1", dias_atras=1)
    assert etiquetas_sin_vincular(dias=30) == []


@pytest.mark.django_db
def test_etiqueta_vieja_pendiente_es_candidata(catalogo):
    etiqueta = _crear_etiqueta(catalogo, "INV-ETQ-2", dias_atras=31)
    assert etiquetas_sin_vincular(dias=30) == [etiqueta]


@pytest.mark.django_db
def test_etiqueta_vinculada_no_es_candidata(catalogo):
    _crear_etiqueta(
        catalogo, "INV-ETQ-3", dias_atras=31, estado=EtiquetaQR.EstadoEtiqueta.VINCULADA
    )
    assert etiquetas_sin_vincular(dias=30) == []


@pytest.mark.django_db
def test_avisa_etiqueta_con_creador_incluye_su_id(catalogo, emitir):
    _crear_etiqueta(catalogo, "INV-ETQ-4", creada_por=catalogo["usuario_a"], dias_atras=31)

    incluidas = avisar_etiquetas_sin_vincular()

    assert incluidas == 1
    [aviso] = _llamadas(emitir, CODIGO_ETIQUETA_SIN_VINCULAR)
    assert aviso["payload"]["usuario_ids"] == [catalogo["usuario_a"].pk]
    assert "INV-ETQ-4" in aviso["titulo"]
    assert aviso["payload"]["url"].endswith("/activos/etiquetas/")


@pytest.mark.django_db
def test_etiqueta_sin_creador_no_incluye_usuario_ids(catalogo, emitir):
    _crear_etiqueta(catalogo, "INV-ETQ-5", dias_atras=31)

    avisar_etiquetas_sin_vincular()

    [aviso] = _llamadas(emitir, CODIGO_ETIQUETA_SIN_VINCULAR)
    assert "usuario_ids" not in aviso["payload"]


@pytest.mark.django_db
def test_avisa_etiquetas_agrupa_por_creador_en_eventos_separados(catalogo, emitir):
    _crear_etiqueta(catalogo, "INV-ETQ-6", creada_por=catalogo["usuario_a"], dias_atras=31)
    _crear_etiqueta(catalogo, "INV-ETQ-7", creada_por=catalogo["usuario_a"], dias_atras=31)
    _crear_etiqueta(catalogo, "INV-ETQ-8", creada_por=catalogo["usuario_b"], dias_atras=31)

    incluidas = avisar_etiquetas_sin_vincular()

    assert incluidas == 3
    avisos = _llamadas(emitir, CODIGO_ETIQUETA_SIN_VINCULAR)
    assert len(avisos) == 2
    por_usuario = {a["payload"]["usuario_ids"][0]: a for a in avisos}
    assert len(por_usuario[catalogo["usuario_a"].pk]["payload"]["etiqueta_ids"]) == 2
    assert len(por_usuario[catalogo["usuario_b"].pk]["payload"]["etiqueta_ids"]) == 1


@pytest.mark.django_db
def test_no_repite_aviso_etiqueta_mientras_sigue_pendiente(catalogo, emitir):
    _crear_etiqueta(catalogo, "INV-ETQ-9", dias_atras=31)

    assert avisar_etiquetas_sin_vincular() == 1
    assert avisar_etiquetas_sin_vincular() == 0
    assert len(_llamadas(emitir, CODIGO_ETIQUETA_SIN_VINCULAR)) == 1


@pytest.mark.django_db
def test_deja_de_avisar_etiqueta_si_se_vincula(catalogo, emitir):
    etiqueta = _crear_etiqueta(catalogo, "INV-ETQ-10", dias_atras=31)
    assert avisar_etiquetas_sin_vincular() == 1

    etiqueta.estado = EtiquetaQR.EstadoEtiqueta.VINCULADA
    etiqueta.save(update_fields=["estado"])

    assert AvisoPorUmbral.objects.filter(
        regla=AvisoPorUmbral.REGLA_ETIQUETA_SIN_VINCULAR, objeto_id=etiqueta.pk
    ).exists()
    assert avisar_etiquetas_sin_vincular() == 0
    assert not AvisoPorUmbral.objects.filter(
        regla=AvisoPorUmbral.REGLA_ETIQUETA_SIN_VINCULAR, objeto_id=etiqueta.pk
    ).exists()


# =============================================================================
# asignacion_sin_planilla (regla por reloj)
# =============================================================================


def _crear_movimiento_reasignacion(activo, *, con_planilla=False, dias_atras=0):
    movimiento = HistorialMovimiento.objects.create(
        activo=activo,
        tipo_movimiento=HistorialMovimiento.TipoMovimiento.REASIGNACION,
        descripcion="Reasignación de prueba",
    )
    if con_planilla:
        movimiento.archivo_planilla.save(
            "planilla.pdf", ContentFile(b"%PDF-1.4"), save=True
        )
    if dias_atras:
        HistorialMovimiento.objects.filter(pk=movimiento.pk).update(
            fecha_movimiento=timezone.now() - timedelta(days=dias_atras)
        )
        movimiento.refresh_from_db()
    return movimiento


@pytest.mark.django_db
def test_reasignacion_reciente_no_es_candidata(catalogo):
    act = _crear_activo(catalogo, "INV-PLA-1", catalogo["usuario_a"])
    _crear_movimiento_reasignacion(act, dias_atras=1)
    assert asignaciones_sin_planilla(dias=7) == []


@pytest.mark.django_db
def test_reasignacion_vieja_sin_planilla_es_candidata(catalogo):
    act = _crear_activo(catalogo, "INV-PLA-2", catalogo["usuario_a"])
    movimiento = _crear_movimiento_reasignacion(act, dias_atras=8)
    assert asignaciones_sin_planilla(dias=7) == [movimiento]


@pytest.mark.django_db
def test_reasignacion_con_planilla_no_es_candidata(catalogo):
    act = _crear_activo(catalogo, "INV-PLA-3", catalogo["usuario_a"])
    _crear_movimiento_reasignacion(act, dias_atras=8, con_planilla=True)
    assert asignaciones_sin_planilla(dias=7) == []


@pytest.mark.django_db
def test_avisa_una_reasignacion_con_deep_link_a_ficha_admin(catalogo, emitir):
    act = _crear_activo(catalogo, "INV-PLA-4", catalogo["usuario_a"])
    _crear_movimiento_reasignacion(act, dias_atras=8)

    avisados = avisar_asignaciones_sin_planilla()

    assert avisados == 1
    [aviso] = _llamadas(emitir, CODIGO_ASIGNACION_SIN_PLANILLA)
    assert "INV-PLA-4" in aviso["titulo"]
    assert aviso["payload"]["url"].endswith(f"/activos/activos/{act.pk}/")
    assert "usuario_ids" not in aviso["payload"]


@pytest.mark.django_db
def test_avisa_varias_reasignaciones_en_un_solo_evento(catalogo, emitir):
    act1 = _crear_activo(catalogo, "INV-PLA-5", catalogo["usuario_a"])
    act2 = _crear_activo(catalogo, "INV-PLA-6", catalogo["usuario_b"])
    _crear_movimiento_reasignacion(act1, dias_atras=8)
    _crear_movimiento_reasignacion(act2, dias_atras=8)

    avisados = avisar_asignaciones_sin_planilla()

    assert avisados == 2
    [aviso] = _llamadas(emitir, CODIGO_ASIGNACION_SIN_PLANILLA)
    assert len(aviso["payload"]["movimiento_ids"]) == 2
    assert aviso["payload"]["url"].endswith("/activos/")


@pytest.mark.django_db
def test_no_repite_aviso_planilla_mientras_no_se_archive(catalogo, emitir):
    act = _crear_activo(catalogo, "INV-PLA-7", catalogo["usuario_a"])
    _crear_movimiento_reasignacion(act, dias_atras=8)

    assert avisar_asignaciones_sin_planilla() == 1
    assert avisar_asignaciones_sin_planilla() == 0
    assert len(_llamadas(emitir, CODIGO_ASIGNACION_SIN_PLANILLA)) == 1


@pytest.mark.django_db
def test_deja_de_avisar_planilla_si_se_archiva(catalogo, emitir):
    act = _crear_activo(catalogo, "INV-PLA-8", catalogo["usuario_a"])
    movimiento = _crear_movimiento_reasignacion(act, dias_atras=8)
    assert avisar_asignaciones_sin_planilla() == 1

    movimiento.archivo_planilla.save("planilla.pdf", ContentFile(b"%PDF-1.4"), save=True)

    assert AvisoPorUmbral.objects.filter(
        regla=AvisoPorUmbral.REGLA_ASIGNACION_SIN_PLANILLA, objeto_id=movimiento.pk
    ).exists()
    assert avisar_asignaciones_sin_planilla() == 0
    assert not AvisoPorUmbral.objects.filter(
        regla=AvisoPorUmbral.REGLA_ASIGNACION_SIN_PLANILLA, objeto_id=movimiento.pk
    ).exists()


# =============================================================================
# Despachador: las dos reglas nuevas
# =============================================================================


@pytest.mark.django_db
def test_comando_ejecuta_etiqueta_sin_vincular(catalogo, emitir):
    _crear_etiqueta(catalogo, "INV-ETQ-CMD", dias_atras=31)
    call_command(
        "enviar_notificaciones_activos", "--regla", "etiqueta_sin_vincular", "--ahora"
    )
    assert len(_llamadas(emitir, CODIGO_ETIQUETA_SIN_VINCULAR)) == 1


@pytest.mark.django_db
def test_comando_ejecuta_asignacion_sin_planilla(catalogo, emitir):
    act = _crear_activo(catalogo, "INV-PLA-CMD", catalogo["usuario_a"])
    _crear_movimiento_reasignacion(act, dias_atras=8)
    call_command(
        "enviar_notificaciones_activos", "--regla", "asignacion_sin_planilla", "--ahora"
    )
    assert len(_llamadas(emitir, CODIGO_ASIGNACION_SIN_PLANILLA)) == 1


@pytest.mark.django_db
def test_comando_dry_run_etiqueta_no_envia_nada(catalogo, emitir):
    _crear_etiqueta(catalogo, "INV-ETQ-CMD2", dias_atras=31)
    salida = StringIO()
    call_command(
        "enviar_notificaciones_activos",
        "--regla", "etiqueta_sin_vincular",
        "--ahora",
        "--dry-run",
        stdout=salida,
    )
    emitir.assert_not_called()
    assert "se avisaría por 1 etiqueta(s)" in salida.getvalue()
