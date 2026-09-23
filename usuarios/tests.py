import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.models import Modulo, UsuarioModulo

UserModel = get_user_model()


@pytest.fixture
def usuario_activos_admin(db, client):
    user = UserModel.objects.create_user(
        username="admin-activos",
        email="admin-activos@test.com",
        password="test-pass-123",
        first_name="Admin",
        last_name="Activos",
        rol=UserModel.ROL_ADMINISTRADOR,
    )
    modulo, _ = Modulo.objects.get_or_create(
        codigo="activos", defaults={"nombre": "Activos"}
    )
    UsuarioModulo.objects.get_or_create(usuario=user, modulo=modulo)
    client.force_login(user)
    return user


@pytest.mark.django_db
def test_usuarios_requiere_sesion(client):
    response = client.get(reverse("usuarios:usuario-search"))
    assert response.status_code == 302
    assert "login" in response.url.lower()


@pytest.mark.django_db
def test_busqueda_de_empleados(usuario_activos_admin, client, crear_empleado):
    crear_empleado("Juan", "Pérez")
    response = client.get(reverse("usuarios:usuario-search"), {"buscar": "juan pérez"})
    assert response.status_code == 200
    assert b"Juan" in response.content


@pytest.mark.django_db
def test_no_existe_ruta_para_crear_usuario_desde_activos(usuario_activos_admin, client):
    """Las personas son empleados de Nomina: Activos no las crea."""
    with pytest.raises(Exception):
        reverse("usuarios:usuario-create")


@pytest.mark.django_db
def test_listado_por_defecto_excluye_empleados_de_baja(usuario_activos_admin, client, crear_empleado):
    crear_empleado("Ana", "Normal")
    crear_empleado("Pedro", "DeBaja", activo=False)
    response = client.get(reverse("usuarios:usuario-search"))
    assert b"Normal" in response.content
    assert b"DeBaja" not in response.content


@pytest.mark.django_db
def test_de_baja_con_equipos_aparece_en_su_filtro(usuario_activos_admin, client, crear_empleado):
    from activos.models import Activo, Categoria, SubCategoria, Ubicacion

    baja = crear_empleado("Pedro", "DeBaja", activo=False)
    cat = Categoria.objects.create(nombre="Computacion")
    sub = SubCategoria.objects.create(nombre="Laptop", prefijo="LAP", categoria=cat)
    ubi = Ubicacion.objects.create(nombre="Oficina")
    Activo.objects.create(subcategoria=sub, marca="HP", modelo="X", ubicacion=ubi, responsable=baja)
    response = client.get(reverse("usuarios:usuario-search"), {"estado": "baja_con_activos"})
    assert list(response.context["usuarios"]) == [baja]


@pytest.mark.django_db
def test_empleados_asignables_excluye_empleados_de_baja(crear_empleado):
    from activos.forms import empleados_asignables

    activo = crear_empleado("Ana", "Normal")
    crear_empleado("Pedro", "DeBaja", activo=False)
    assert list(empleados_asignables()) == [activo]


@pytest.mark.django_db
def test_no_se_puede_elegir_un_empleado_de_baja_pero_si_conservarlo(crear_empleado):
    from activos.forms import ReasignarActivoForm
    from activos.models import Activo, Categoria, SubCategoria, Ubicacion

    cat = Categoria.objects.create(nombre="Computacion")
    sub = SubCategoria.objects.create(nombre="Laptop", prefijo="LAP", categoria=cat)
    ubi = Ubicacion.objects.create(nombre="Oficina")
    baja = crear_empleado("Pedro", "DeBaja", activo=False)
    otro = crear_empleado("Luis", "Otro")

    libre = Activo.objects.create(subcategoria=sub, marca="HP", modelo="X", ubicacion=ubi)
    form = ReasignarActivoForm({"responsable": baja.pk}, instance=libre)
    assert not form.is_valid()

    # Ya asignado a alguien que luego se dio de baja: el formulario lo acepta
    # sin cambios, para poder editar el activo; reasignar a otro sigue abierto.
    suyo = Activo.objects.create(subcategoria=sub, marca="HP", modelo="Y", ubicacion=ubi, responsable=baja)
    assert ReasignarActivoForm({"responsable": baja.pk}, instance=suyo).is_valid()
    assert ReasignarActivoForm({"responsable": otro.pk}, instance=suyo).is_valid()
