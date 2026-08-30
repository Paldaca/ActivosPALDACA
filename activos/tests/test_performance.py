"""Query budgets for the pages most often loaded inside the Portal iframe."""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from activos.models import Activo


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
    user_model = get_user_model()
    user_model.objects.bulk_create([
        user_model(
            username=f"perf-{index}",
            first_name="Persona",
            last_name=f"{index:03d}",
            is_active=True,
        )
        for index in range(30)
    ])
    _assert_query_budget(
        client_auth,
        reverse("usuarios:usuario-search"),
        maximum=9,
    )


@pytest.mark.django_db
def test_presupuesto_perfil_usuario(client_auth, catalogo):
    Activo.objects.bulk_create([
        Activo(
            subcategoria=catalogo["subcategoria"],
            marca="Marca",
            modelo=f"Modelo {index}",
            codigo_inventario=f"PERF-{index:03d}",
            usuario_asignado=catalogo["usuario_a"],
            ubicacion=catalogo["ubicacion_almacen"],
        )
        for index in range(30)
    ])
    _assert_query_budget(
        client_auth,
        reverse(
            "usuarios:usuario-profile",
            args=[catalogo["usuario_a"].pk],
        ),
        maximum=8,
    )


@pytest.mark.django_db
def test_presupuesto_listado_activos(client_auth, catalogo):
    _assert_query_budget(
        client_auth,
        reverse("activos:activo-list"),
        maximum=16,
    )


@pytest.mark.django_db
def test_busqueda_asignables_es_paginada(client_auth, catalogo):
    response = client_auth.get(
        reverse("activos:usuarios-asignables"),
        {"q": "Prueba"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["results"]
    assert len(payload["results"]) <= 20
