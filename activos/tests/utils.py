"""Ayudas compartidas por los tests de Activos."""

from itertools import count

from activos.models import EmpleadoPortal

_nomina_ids = count(500_000)


def empleado_de(usuario):
    """El empleado de Nomina vinculado a una cuenta del Portal (lo crea si no hay).

    Muchas pruebas razonan sobre la cuenta (quien inicia sesion, a quien le
    llega el aviso); el activo apunta al empleado. Acepta tambien un
    EmpleadoPortal o None, que se devuelven tal cual.
    """
    if usuario is None or isinstance(usuario, EmpleadoPortal):
        return usuario
    existente = EmpleadoPortal.objects.filter(usuario=usuario).first()
    if existente:
        return existente
    nomina_id = next(_nomina_ids)
    return EmpleadoPortal.objects.create(
        nomina_id=nomina_id,
        cedula=f"V{nomina_id}",
        nombres=usuario.first_name or "Empleado",
        apellidos=usuario.last_name or str(nomina_id),
        activo=usuario.is_active,
        usuario=usuario,
    )
