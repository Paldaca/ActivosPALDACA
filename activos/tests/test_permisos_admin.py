"""Un usuario sin rol administrador en Activos solo ve sus propios activos.

`user`/`client_auth` (conftest.py) son administradores; `usuario_normal`/
`client_normal` tienen acceso al módulo pero no ese rol.
"""

import pytest
from django.urls import reverse

from activos.models import Activo
from activos.tests.utils import empleado_de


def _crear_activo(catalogo, codigo, usuario=None):
    return Activo.objects.create(
        subcategoria=catalogo["subcategoria"],
        marca="Dell",
        modelo="Latitude",
        codigo_inventario=codigo,
        responsable=empleado_de(usuario),
        ubicacion=catalogo["ubicacion_almacen"],
        estado=Activo.EstadoActivo.ACTIVO,
    )


VISTAS_DE_GESTION = [
    ("activos:activo-list", []),
    ("activos:activo-create", []),
    ("activos:categoria-list", []),
    ("activos:subcategoria-list", []),
    ("activos:ubicacion-list", []),
    ("activos:etiqueta-list", []),
    ("mantenimientos:mantenimiento-list", []),
    ("usuarios:usuario-search", []),
]


@pytest.mark.django_db
@pytest.mark.parametrize("nombre_url,args", VISTAS_DE_GESTION)
def test_usuario_normal_no_entra_a_vistas_de_gestion(client_normal, nombre_url, args):
    respuesta = client_normal.get(reverse(nombre_url, args=args))
    assert respuesta.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("nombre_url,args", VISTAS_DE_GESTION)
def test_admin_si_entra_a_vistas_de_gestion(client_auth, nombre_url, args):
    respuesta = client_auth.get(reverse(nombre_url, args=args))
    assert respuesta.status_code == 200


@pytest.mark.django_db
def test_usuario_normal_no_puede_editar_ni_reasignar_ni_eliminar(client_normal, catalogo):
    propio = _crear_activo(catalogo, "INV-PERM-1", catalogo["usuario_a"])
    for nombre_url in (
        "activos:activo-update",
        "activos:activo-delete",
        "activos:activo-reasignar",
        "activos:activo-reubicar",
        "activos:activo-historial",
    ):
        respuesta = client_normal.get(reverse(nombre_url, args=[propio.pk]))
        assert respuesta.status_code == 403, nombre_url


@pytest.mark.django_db
def test_usuario_normal_no_puede_ver_la_ficha_de_gestion_ni_de_su_propio_equipo(
    client_normal, catalogo, usuario_normal
):
    propio = _crear_activo(catalogo, "INV-PERM-2", usuario_normal)
    respuesta = client_normal.get(reverse("activos:activo-detail", args=[propio.pk]))
    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_mis_activos_lista_solo_lo_propio(client_normal, catalogo, usuario_normal):
    propio = _crear_activo(catalogo, "INV-PERM-3", usuario_normal)
    _crear_activo(catalogo, "INV-PERM-4", catalogo["usuario_a"])
    _crear_activo(catalogo, "INV-PERM-5")  # sin asignar

    respuesta = client_normal.get(reverse("activos:mis-activos-list"))
    assert respuesta.status_code == 200
    assert list(respuesta.context["activos"]) == [propio]


@pytest.mark.django_db
def test_mis_activos_detalle_del_propio_funciona(client_normal, catalogo, usuario_normal):
    propio = _crear_activo(catalogo, "INV-PERM-6", usuario_normal)
    respuesta = client_normal.get(reverse("activos:mis-activos-detail", args=[propio.pk]))
    assert respuesta.status_code == 200
    assert respuesta.context["activo"] == propio


@pytest.mark.django_db
def test_mis_activos_detalle_de_otro_da_404_no_403(client_normal, catalogo):
    """404 y no 403: no se confirma que el activo existe si no es tuyo."""
    ajeno = _crear_activo(catalogo, "INV-PERM-7", catalogo["usuario_a"])
    respuesta = client_normal.get(reverse("activos:mis-activos-detail", args=[ajeno.pk]))
    assert respuesta.status_code == 404


@pytest.mark.django_db
def test_admin_tambien_puede_usar_mis_activos_para_lo_suyo(client_auth, catalogo, user):
    propio = _crear_activo(catalogo, "INV-PERM-8", user)
    respuesta = client_auth.get(reverse("activos:mis-activos-list"))
    assert respuesta.status_code == 200
    assert list(respuesta.context["activos"]) == [propio]


@pytest.mark.django_db
def test_home_redirige_a_mis_activos_si_no_es_admin(client_normal):
    respuesta = client_normal.get(reverse("core:home"))
    assert respuesta.status_code == 302
    assert respuesta.url == reverse("activos:mis-activos-list")


@pytest.mark.django_db
def test_home_sirve_el_dashboard_si_es_admin(client_auth):
    respuesta = client_auth.get(reverse("core:home"))
    assert respuesta.status_code == 200


@pytest.mark.django_db
def test_planilla_vigente_solo_admin_o_custodio_actual(
    client_normal, catalogo, usuario_normal
):
    propio = _crear_activo(catalogo, "INV-PERM-9", usuario_normal)
    ajeno = _crear_activo(catalogo, "INV-PERM-10", catalogo["usuario_a"])

    # Del propio: puede intentarlo (puede fallar más adelante por no haber
    # generado planilla aún, pero no por permisos).
    respuesta = client_normal.get(reverse("reportes:planilla-vigente", args=[propio.pk]))
    assert respuesta.status_code != 403

    # Del ajeno: bloqueado, sin importar que tenga el módulo.
    respuesta = client_normal.get(reverse("reportes:planilla-vigente", args=[ajeno.pk]))
    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_etiqueta_alta_sigue_abierta_a_cualquiera_con_modulo(client_normal):
    """`etiqueta_alta` (alta desde QR escaneado) no exige rol admin, a propósito."""
    from activos.models import Categoria, EtiquetaQR, SubCategoria, Ubicacion

    cat = Categoria.objects.create(nombre="Cat QR")
    sub = SubCategoria.objects.create(nombre="Sub QR", categoria=cat)
    Ubicacion.objects.create(nombre="Ubicación QR")
    etiqueta = EtiquetaQR.objects.create(
        subcategoria=sub,
        token="tok-permiso-1",
        codigo_reservado="PAL-QR-001",
    )
    respuesta = client_normal.get(reverse("etiqueta-alta", args=[etiqueta.token]))
    assert respuesta.status_code == 200
