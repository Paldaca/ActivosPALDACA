"""Fase 1: las asignaciones anteriores (cuenta del Portal) pasan a empleados."""

from io import StringIO

import pytest
from django.core.management import call_command

from activos.models import Activo, EmpleadoPortal
from activos.services.responsables import vincular_responsables


def _activo(catalogo, codigo, legacy):
    return Activo.objects.create(
        subcategoria=catalogo["subcategoria"],
        marca="Dell",
        modelo="Latitude",
        codigo_inventario=codigo,
        usuario_legacy=legacy,
        ubicacion=catalogo["ubicacion_almacen"],
    )


@pytest.mark.django_db
def test_vincula_por_la_cuenta_del_empleado_y_deja_pendiente_al_resto(catalogo, django_user_model):
    sin_empleado = django_user_model.objects.create_user(username="huerfano", password="x")
    vinculable = _activo(catalogo, "INV-LEG-1", catalogo["usuario_a"])
    pendiente = _activo(catalogo, "INV-LEG-2", sin_empleado)

    assert vincular_responsables(Activo, EmpleadoPortal) == 1

    vinculable.refresh_from_db()
    pendiente.refresh_from_db()
    assert vinculable.responsable == catalogo["empleado_a"]
    assert vinculable.usuario_legacy is None
    assert pendiente.responsable is None
    assert pendiente.usuario_legacy == sin_empleado
    assert pendiente.pendiente_de_vincular
    assert pendiente.tiene_responsable


@pytest.mark.django_db
def test_no_toca_activos_que_ya_tienen_responsable(catalogo):
    activo = _activo(catalogo, "INV-LEG-3", catalogo["usuario_a"])
    activo.responsable = catalogo["empleado_b"]
    activo.save()
    assert vincular_responsables(Activo, EmpleadoPortal) == 0
    activo.refresh_from_db()
    assert activo.responsable == catalogo["empleado_b"]


@pytest.mark.django_db
def test_comando_lista_los_pendientes(catalogo, django_user_model):
    sin_empleado = django_user_model.objects.create_user(
        username="huerfano", password="x", first_name="Sin", last_name="Ficha"
    )
    _activo(catalogo, "INV-LEG-4", sin_empleado)
    salida = StringIO()
    call_command("vincular_responsables", stdout=salida)
    assert "Sin Ficha" in salida.getvalue()
    assert "1 persona(s)" in salida.getvalue()


@pytest.mark.django_db
def test_reasignar_cierra_la_asignacion_anterior(client_auth, catalogo, django_user_model):
    from django.urls import reverse

    sin_empleado = django_user_model.objects.create_user(username="huerfano", password="x")
    activo = _activo(catalogo, "INV-LEG-5", sin_empleado)
    client_auth.post(
        reverse("activos:activo-reasignar", args=[activo.pk]),
        {"responsable": catalogo["empleado_a"].pk},
    )
    activo.refresh_from_db()
    assert activo.responsable == catalogo["empleado_a"]
    assert activo.usuario_legacy is None
    assert activo.historial_movimientos.filter(tipo_movimiento="RE").exists()


@pytest.mark.django_db
def test_editar_otro_campo_no_pierde_la_asignacion_pendiente(client_auth, catalogo, django_user_model):
    from django.urls import reverse
    from activos.tests.test_activo_flow import _payload_activo

    sin_empleado = django_user_model.objects.create_user(username="huerfano", password="x")
    activo = _activo(catalogo, "INV-LEG-6", sin_empleado)
    datos = _payload_activo(catalogo, responsable="")
    datos["marca"] = "Otra"
    client_auth.post(reverse("activos:activo-update", args=[activo.pk]), datos)
    activo.refresh_from_db()
    assert activo.marca == "Otra"
    assert activo.usuario_legacy == sin_empleado
