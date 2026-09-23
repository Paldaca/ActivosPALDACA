"""Query budgets for the pages most often loaded inside the Portal iframe."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from activos.models import Activo, EmpleadoPortal


def _assert_query_budget(client, url, maximum):
    with CaptureQueriesContext(connection) as captured:
        response = client.get(url)
    assert response.status_code == 200
    assert len(captured) <= maximum, (
        f"{url} ejecutó {len(captured)} queries; presupuesto: {maximum}\n"
        + "\n".join(query["sql"] for query in captured.captured_queries)
    )


@pytest.mark.django_db
def test_presupuesto_listado_usuarios(client_auth, catalogo):
    EmpleadoPortal.objects.bulk_create([
        EmpleadoPortal(
            nomina_id=900 + index,
            cedula=f"V900{index:03d}",
            nombres="Persona",
            apellidos=f"{index:03d}",
            activo=True,
        )
        for index in range(30)
    ])
    _assert_query_budget(
        client_auth,
        reverse("usuarios:usuario-search"),
        # +1: AdminActivoRequiredMixin confirma rol administrador ademas del
        # acceso al modulo (activos/decorators.py). +1: conteo de activos
        # pendientes de vincular (fase 1 de la migracion a empleados).
        maximum=11,
    )


@pytest.mark.django_db
def test_presupuesto_perfil_usuario(client_auth, catalogo):
    Activo.objects.bulk_create([
        Activo(
            subcategoria=catalogo["subcategoria"],
            marca="Marca",
            modelo=f"Modelo {index}",
            codigo_inventario=f"PERF-{index:03d}",
            responsable=catalogo["empleado_a"],
            ubicacion=catalogo["ubicacion_almacen"],
        )
        for index in range(30)
    ])
    _assert_query_budget(
        client_auth,
        reverse(
            "usuarios:usuario-profile",
            args=[catalogo["empleado_a"].pk],
        ),
        # +1: AdminActivoRequiredMixin confirma rol administrador ademas del
        # acceso al modulo (activos/decorators.py).
        maximum=9,
    )


@pytest.mark.django_db
def test_presupuesto_listado_activos(client_auth, catalogo):
    _assert_query_budget(
        client_auth,
        reverse("activos:activo-list"),
        # +1: AdminActivoRequiredMixin confirma rol administrador ademas del
        # acceso al modulo (activos/decorators.py).
        maximum=17,
    )


@pytest.mark.django_db
def test_busqueda_asignables_es_paginada_y_solo_empleados_activos(client_auth, catalogo, crear_empleado):
    for index in range(25):
        crear_empleado("Prueba", f"Masiva {index:02d}")
    crear_empleado("Prueba", "De Baja", activo=False)

    payload = client_auth.get(reverse("activos:empleados-asignables"), {"q": "Prueba"}).json()
    assert len(payload["results"]) == 20
    assert payload["has_more"] is True
    assert all("De Baja" not in r["text"] for r in payload["results"])


@pytest.mark.django_db
def test_busqueda_asignables_por_nombre_y_apellido_en_cualquier_orden(client_auth, catalogo):
    for q in ("ana prueba", "prueba ana"):
        ids = [r["id"] for r in client_auth.get(
            reverse("activos:empleados-asignables"), {"q": q}
        ).json()["results"]]
        assert ids == [catalogo["empleado_a"].pk], q
