"""El contrato de esquema con `portal_empleado` se comprueba contra la tabla real."""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from activos.services.contrato_portal import columnas_esperadas, columnas_faltantes

pytestmark = pytest.mark.django_db


def test_la_tabla_completa_cumple_el_contrato():
    assert columnas_faltantes() == []


def test_detecta_una_columna_retirada():
    """Simula que el Portal quito `cargo` y `email` de su tabla."""
    esperadas = columnas_esperadas() - {"cargo", "email"}
    columnas = ", ".join(f'"{c}" varchar(10)' for c in sorted(esperadas))
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE TABLE portal_empleado_recortada ({columnas})")
    try:
        assert columnas_faltantes(tabla="portal_empleado_recortada") == ["cargo", "email"]
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE portal_empleado_recortada")


def test_tabla_inexistente_no_es_lo_mismo_que_columnas_faltantes():
    assert columnas_faltantes(tabla="tabla_que_no_existe") is None


def test_el_comando_pasa_con_la_tabla_completa():
    salida = StringIO()
    call_command("verificar_portal_empleado", stdout=salida)
    assert "cumple el contrato" in salida.getvalue()


def test_el_comando_falla_y_nombra_las_columnas_faltantes():
    with patch(
        "activos.management.commands.verificar_portal_empleado.columnas_faltantes",
        return_value=["cargo"],
    ):
        with pytest.raises(CommandError, match="cargo"):
            call_command("verificar_portal_empleado")


def test_el_comando_falla_si_la_tabla_no_existe():
    with patch(
        "activos.management.commands.verificar_portal_empleado.columnas_faltantes",
        return_value=None,
    ):
        with pytest.raises(CommandError, match="No existe la tabla"):
            call_command("verificar_portal_empleado")
