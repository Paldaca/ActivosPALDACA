import pytest
from django.contrib.auth import get_user_model

from activos.models import Categoria, EmpleadoPortal, SubCategoria, Ubicacion
from core.models import Modulo, UsuarioModulo


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """`portal_empleado` es del Portal (EmpleadoPortal es `managed = False`):
    las migraciones de Activos no la crean, asi que se crea aqui."""
    from django.db import connection

    with django_db_blocker.unblock():
        with connection.schema_editor() as editor:
            editor.create_model(EmpleadoPortal)


_nomina_ids = iter(range(1, 10**6))


@pytest.fixture
def crear_empleado(db):
    """Fabrica de empleados de Nomina (en produccion los escribe solo Nomina)."""

    def _crear(nombres="Empleado", apellidos="Prueba", usuario=None, **extra):
        nomina_id = next(_nomina_ids)
        datos = {
            "nomina_id": nomina_id,
            "cedula": f"V{nomina_id:08d}",
            "nombres": nombres,
            "apellidos": apellidos,
            "cargo": "Tecnico",
            "activo": True,
            "usuario": usuario,
        }
        datos.update(extra)
        return EmpleadoPortal.objects.create(**datos)

    return _crear


@pytest.fixture
def user(db):
    """Usuario de pruebas con acceso a Activos y rol administrador.

    La inmensa mayoría de este suite ejercita pantallas de gestión
    (crear/editar/reasignar/etc.), que ahora exigen `rol=administrador`
    (`AdminActivoRequiredMixin`). Un usuario sin ese rol solo ve
    `activos:mis-activos-*`; para esos casos usar `usuario_normal`.
    """
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username="pytest_user",
        email="pytest@example.com",
        password="test-pass-123",
        rol=user_model.ROL_ADMINISTRADOR,
    )
    modulo, _ = Modulo.objects.get_or_create(
        codigo="activos", defaults={"nombre": "Activos"}
    )
    UsuarioModulo.objects.get_or_create(usuario=user, modulo=modulo)
    return user


@pytest.fixture
def client_auth(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def usuario_normal(db):
    """Acceso a Activos SIN rol administrador: solo puede ver sus propios activos."""
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username="pytest_user_normal",
        email="pytest-normal@example.com",
        password="test-pass-123",
    )
    modulo, _ = Modulo.objects.get_or_create(
        codigo="activos", defaults={"nombre": "Activos"}
    )
    UsuarioModulo.objects.get_or_create(usuario=user, modulo=modulo)
    return user


@pytest.fixture
def client_normal(client, usuario_normal):
    client.force_login(usuario_normal)
    return client


@pytest.fixture(autouse=True)
def media_tmp(tmp_path, settings):
    """Isolate uploaded planillas from the project media folder."""
    root = tmp_path / "media"
    root.mkdir()
    settings.MEDIA_ROOT = root
    return root


@pytest.fixture
def catalogo(db, crear_empleado):
    """Categoría, subcategoría, dos ubicaciones y dos empleados asignables.

    Cada empleado tiene cuenta del Portal (`usuario_a` / `usuario_b`): así las
    pruebas de "mis activos" y de avisos tienen a quién iniciar sesión o avisar.
    """
    user_model = get_user_model()
    cat = Categoria.objects.create(nombre="Categoría Pytest")
    sub = SubCategoria.objects.create(nombre="Sub Pytest", categoria=cat)
    u_almacen = Ubicacion.objects.create(nombre="Ubicación Almacén Pytest")
    u_oficina = Ubicacion.objects.create(nombre="Ubicación Oficina Pytest")
    ua = user_model.objects.create_user(
        username="V-PYTEST-001",
        email="ana-pytest@example.com",
        password="test-pass-123",
        first_name="Ana",
        last_name="Prueba",
    )
    ub = user_model.objects.create_user(
        username="V-PYTEST-002",
        email="luis-pytest@example.com",
        password="test-pass-123",
        first_name="Luis",
        last_name="Prueba",
    )
    return {
        "categoria": cat,
        "subcategoria": sub,
        "ubicacion_almacen": u_almacen,
        "ubicacion_oficina": u_oficina,
        "usuario_a": ua,
        "usuario_b": ub,
        "empleado_a": crear_empleado("Ana", "Prueba", usuario=ua),
        "empleado_b": crear_empleado("Luis", "Prueba", usuario=ub),
    }
