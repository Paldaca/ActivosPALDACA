"""Humo: renderiza cada pantalla del módulo con datos reales."""
import pytest
from django.urls import reverse

from activos.models import Activo, Categoria, SubCategoria, Ubicacion, HistorialMovimiento


@pytest.fixture
def datos(db, django_user_model):
    from core.models import Modulo, UsuarioModulo

    mod, _ = Modulo.objects.get_or_create(codigo="activos", defaults={"nombre": "Activos"})
    admin = django_user_model.objects.create_user(
        username="V-ADMIN", password="x", first_name="Ricardo", last_name="Goitia"
    )
    ana = django_user_model.objects.create_user(
        username="V-ANA", password="x", first_name="Ana", last_name="Prueba"
    )
    sin_nombre = django_user_model.objects.create_user(username="V-SINNOMBRE", password="x")
    for u in (admin, ana, sin_nombre):
        UsuarioModulo.objects.get_or_create(usuario=u, modulo=mod)

    cat = Categoria.objects.create(nombre="Equipos de cómputo")
    sub = SubCategoria.objects.create(nombre="Laptop", prefijo="LAP", categoria=cat)
    sub2 = SubCategoria.objects.create(nombre="Impresora", prefijo="IMP", categoria=cat)
    ub = Ubicacion.objects.create(nombre="Sede Principal")
    ub2 = Ubicacion.objects.create(nombre="Almacén")

    asignado = Activo.objects.create(
        subcategoria=sub, marca="Dell", modelo="Latitude 5420",
        numero_serial="SN123", ubicacion=ub, usuario_asignado=ana, estado="AC",
    )
    disponible = Activo.objects.create(
        subcategoria=sub, marca="HP", modelo="ProBook", ubicacion=ub, estado="AC",
    )
    manten = Activo.objects.create(
        subcategoria=sub2, marca="Epson", modelo="L3250", ubicacion=ub2, estado="EM",
    )
    baja = Activo.objects.create(
        subcategoria=sub, marca="Acer", modelo="Viejo", ubicacion=ub2,
        usuario_asignado=sin_nombre, estado="IN",
    )
    HistorialMovimiento.objects.create(
        activo=asignado, tipo_movimiento="RE", descripcion="Reasignación de usuario: Sin asignar -> Ana Prueba",
        campo_modificado="usuario_asignado", valor_anterior="Sin asignar",
        valor_nuevo="Ana Prueba", usuario=admin,
    )
    return {
        "admin": admin, "ana": ana, "cat": cat, "sub": sub, "ub": ub, "ub2": ub2,
        "asignado": asignado, "disponible": disponible, "manten": manten, "baja": baja,
    }


@pytest.fixture
def cli(client, datos):
    client.force_login(datos["admin"])
    return client


def test_todas_las_pantallas_renderizan(cli, datos):
    a = datos["asignado"]
    urls = [
        reverse("activos:activo-list"),
        reverse("activos:activo-list") + "?estado=AC&asignacion=libre",
        reverse("activos:activo-list") + "?estado=EM",
        reverse("activos:activo-list") + "?buscar=Ana",
        reverse("activos:activo-list") + f"?categoria={datos['cat'].pk}&ubicacion={datos['ub'].pk}&usuario_asignado={datos['ana'].pk}&buscar=Dell",
        reverse("activos:activo-detail", args=[a.pk]),
        reverse("activos:activo-detail", args=[datos["disponible"].pk]),
        reverse("activos:activo-create"),
        reverse("activos:activo-update", args=[a.pk]),
        reverse("activos:activo-historial", args=[a.pk]),
        reverse("activos:activo-historial", args=[datos["manten"].pk]),
        reverse("activos:activo-reasignar", args=[a.pk]),
        reverse("activos:activo-reubicar", args=[a.pk]),
        reverse("activos:categoria-list"),
        reverse("activos:categoria-create"),
        reverse("activos:categoria-update", args=[datos["cat"].pk]),
        reverse("activos:subcategoria-list"),
        reverse("activos:subcategoria-list") + f"?categoria={datos['cat'].pk}",
        reverse("activos:subcategoria-create"),
        reverse("activos:subcategoria-update", args=[datos["sub"].pk]),
        reverse("activos:ubicacion-list"),
        reverse("activos:ubicacion-create"),
        reverse("activos:ubicacion-update", args=[datos["ub"].pk]),
    ]
    for url in urls:
        r = cli.get(url)
        assert r.status_code == 200, f"{url} -> {r.status_code}"


def test_kpis_y_estados_derivados(cli, datos):
    r = cli.get(reverse("activos:activo-list"))
    ctx = r.context["resumen"]
    assert ctx["total"] == 4
    assert ctx["disponibles"] == 1
    assert ctx["asignados"] == 1
    assert ctx["mantenimiento"] == 1
    assert ctx["baja"] == 1

    body = r.content.decode()
    assert "Disponible" in body and "En Mantenimiento" in body and "Dado de Baja" in body
    # Regla: nunca el username en pantalla
    assert "Ana Prueba" in body
    assert "V-ANA" not in body


def test_filtro_asignacion(cli, datos):
    r = cli.get(reverse("activos:activo-list"), {"estado": "AC", "asignacion": "libre"})
    assert list(r.context["activos"]) == [datos["disponible"]]

    r = cli.get(reverse("activos:activo-list"), {"estado": "AC", "asignacion": "asignado"})
    assert list(r.context["activos"]) == [datos["asignado"]]


def test_buscar_por_persona(cli, datos):
    r = cli.get(reverse("activos:activo-list"), {"buscar": "Prueba"})
    assert list(r.context["activos"]) == [datos["asignado"]]


def test_reasignar_con_next_vuelve_al_listado(cli, datos):
    a = datos["disponible"]
    destino = reverse("activos:activo-list") + "?estado=AC"
    r = cli.post(
        reverse("activos:activo-reasignar", args=[a.pk]),
        {"usuario_asignado": datos["ana"].pk, "next": destino},
    )
    assert r.status_code == 302
    assert r.url == destino
    a.refresh_from_db()
    assert a.usuario_asignado_id == datos["ana"].pk
    assert a.historial_movimientos.filter(tipo_movimiento="RE").count() == 1


def test_next_externo_es_rechazado(cli, datos):
    a = datos["disponible"]
    r = cli.post(
        reverse("activos:activo-reasignar", args=[a.pk]),
        {"usuario_asignado": "", "next": "https://malicioso.example.com/"},
    )
    assert r.status_code == 302
    assert "malicioso" not in r.url


def test_acciones_masivas_reasignar(cli, datos):
    ids = [datos["disponible"].pk, datos["manten"].pk]
    r = cli.post(reverse("activos:activo-acciones-masivas"), {
        "accion": "reasignar", "activos": ids, "destino": datos["ana"].pk,
        "next": reverse("activos:activo-list"),
    })
    assert r.status_code == 302
    for pk in ids:
        act = Activo.objects.get(pk=pk)
        assert act.usuario_asignado_id == datos["ana"].pk
        assert act.historial_movimientos.filter(tipo_movimiento="RE").count() == 1


def test_acciones_masivas_omite_sin_cambio(cli, datos):
    a = datos["asignado"]  # ya es de Ana
    r = cli.post(reverse("activos:activo-acciones-masivas"), {
        "accion": "reasignar", "activos": [a.pk], "destino": datos["ana"].pk,
    })
    assert r.status_code == 302
    assert a.historial_movimientos.filter(tipo_movimiento="RE").count() == 1  # la del fixture


def test_acciones_masivas_reubicar(cli, datos):
    ids = [datos["asignado"].pk, datos["disponible"].pk]
    r = cli.post(reverse("activos:activo-acciones-masivas"), {
        "accion": "reubicar", "activos": ids, "destino": datos["ub2"].pk,
    })
    assert r.status_code == 302
    for pk in ids:
        assert Activo.objects.get(pk=pk).ubicacion_id == datos["ub2"].pk


def test_borrado_sin_pagina(cli, datos):
    a = datos["disponible"]
    r = cli.get(reverse("activos:activo-delete", args=[a.pk]))
    assert r.status_code == 302
    assert Activo.objects.filter(pk=a.pk).exists()

    r = cli.post(reverse("activos:activo-delete", args=[a.pk]))
    assert r.status_code == 302
    assert not Activo.objects.filter(pk=a.pk).exists()


def test_catalogo_protegido_no_revienta(cli, datos):
    r = cli.post(reverse("activos:categoria-delete", args=[datos["cat"].pk]), follow=True)
    assert r.status_code == 200
    assert Categoria.objects.filter(pk=datos["cat"].pk).exists()
    assert any("no se puede eliminar" in str(m).lower() for m in r.context["messages"])


def test_guardar_y_nuevo(cli, datos):
    r = cli.post(reverse("activos:activo-create"), {
        "subcategoria": datos["sub"].pk, "marca": "Lenovo", "modelo": "T14",
        "numero_serial": "", "usuario_asignado": "", "ubicacion": datos["ub"].pk,
        "observaciones": "", "estado": "AC", "guardar_y_nuevo": "1",
    })
    assert r.status_code == 302
    assert r.url == reverse("activos:activo-create")
    assert Activo.objects.filter(marca="Lenovo").exists()


# ---------------------------------------------------------------------------
# Alta express de catálogo (sin salir del formulario de activos)
# ---------------------------------------------------------------------------

def test_crear_rapido_ubicacion(cli):
    from django.urls import reverse as rv
    r = cli.post(rv("activos:crear-rapido", args=["ubicacion"]), {"nombre": "Depósito Norte"})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] and d["creado"]
    assert Ubicacion.objects.filter(pk=d["id"], nombre="Depósito Norte").exists()


def test_crear_rapido_ubicacion_reutiliza(cli, datos):
    from django.urls import reverse as rv
    r = cli.post(rv("activos:crear-rapido", args=["ubicacion"]), {"nombre": "Sede Principal"})
    d = r.json()
    assert d["ok"] and d["creado"] is False
    assert d["id"] == datos["ub"].pk


def test_crear_rapido_exige_nombre(cli):
    from django.urls import reverse as rv
    r = cli.post(rv("activos:crear-rapido", args=["categoria"]), {"nombre": "   "})
    assert r.status_code == 400
    assert "nombre" in r.json()["errores"]


def test_crear_rapido_subcategoria_con_categoria_existente(cli, datos):
    from django.urls import reverse as rv
    r = cli.post(rv("activos:crear-rapido", args=["subcategoria"]), {
        "nombre": "Monitor", "prefijo": "mon", "categoria": datos["cat"].pk,
    })
    assert r.status_code == 200, r.content
    d = r.json()
    sub = SubCategoria.objects.get(pk=d["id"])
    assert sub.prefijo == "MON"          # se normaliza en mayúsculas
    assert sub.categoria_id == datos["cat"].pk


def test_crear_rapido_subcategoria_creando_categoria_en_el_mismo_paso(cli):
    from django.urls import reverse as rv
    r = cli.post(rv("activos:crear-rapido", args=["subcategoria"]), {
        "nombre": "Ambulancia", "prefijo": "AMB", "categoria_nueva": "Vehículos",
    })
    assert r.status_code == 200, r.content
    d = r.json()
    sub = SubCategoria.objects.get(pk=d["id"])
    assert sub.categoria.nombre == "Vehículos"
    assert d["categoria"]["texto"] == "Vehículos"


def test_crear_rapido_subcategoria_sin_categoria_falla(cli):
    from django.urls import reverse as rv
    r = cli.post(rv("activos:crear-rapido", args=["subcategoria"]), {
        "nombre": "Suelto", "prefijo": "SUE",
    })
    assert r.status_code == 400
    assert "categoria" in r.json()["errores"]


def test_crear_rapido_prefijo_invalido(cli, datos):
    from django.urls import reverse as rv
    r = cli.post(rv("activos:crear-rapido", args=["subcategoria"]), {
        "nombre": "Raro", "prefijo": "A-B!", "categoria": datos["cat"].pk,
    })
    assert r.status_code == 400
    assert "prefijo" in r.json()["errores"]


def test_crear_rapido_requiere_post(cli):
    from django.urls import reverse as rv
    assert cli.get(rv("activos:crear-rapido", args=["ubicacion"])).status_code == 405


def test_crear_rapido_requiere_sesion(db, client):
    from django.urls import reverse as rv
    r = client.post(rv("activos:crear-rapido", args=["ubicacion"]), {"nombre": "X"})
    assert r.status_code in (302, 403)
    assert not Ubicacion.objects.filter(nombre="X").exists()


# ---------------------------------------------------------------------------
# Home, personas y mantenimientos
# ---------------------------------------------------------------------------

@pytest.fixture
def mantenimiento(datos):
    from mantenimientos.models import Mantenimiento
    return Mantenimiento.objects.create(
        activo=datos["asignado"], tecnico="Carlos Pérez", telefono="04141234567",
        descripcion="Cambio de disco", costo="120.50", estado="EP",
    )


def test_home_renderiza(cli, datos, mantenimiento):
    from django.urls import reverse as rv
    r = cli.get(rv("core:home"))
    assert r.status_code == 200
    assert r.context["resumen"]["total"] == 4
    body = r.content.decode()
    assert "Requiere atención" in body
    assert "V-ANA" not in body            # nunca el username


def test_pantallas_usuarios_y_mantenimientos(cli, datos, mantenimiento):
    from django.urls import reverse as rv
    urls = [
        rv("usuarios:usuario-search"),
        rv("usuarios:usuario-search") + "?estado=con_activos",
        rv("usuarios:usuario-search") + "?estado=inactivos",
        rv("usuarios:usuario-search") + "?buscar=Ana",
        rv("usuarios:usuario-profile", args=[datos["ana"].pk]),
        rv("usuarios:usuario-create"),
        rv("usuarios:usuario-update", args=[datos["ana"].pk]),
        rv("mantenimientos:mantenimiento-list"),
        rv("mantenimientos:mantenimiento-list") + "?estado=EP",
        rv("mantenimientos:mantenimiento-create"),
        rv("mantenimientos:mantenimiento-create") + f"?activo_id={datos['asignado'].pk}",
        rv("mantenimientos:mantenimiento-detail", args=[mantenimiento.pk]),
        rv("mantenimientos:mantenimiento-update", args=[mantenimiento.pk]),
    ]
    for url in urls:
        assert cli.get(url).status_code == 200, url


def test_buscar_persona_por_codigo_de_inventario(cli, datos):
    from django.urls import reverse as rv
    r = cli.get(rv("usuarios:usuario-search"), {"buscar": datos["asignado"].codigo_inventario})
    assert list(r.context["usuarios"]) == [datos["ana"]]


def test_desactivar_persona_no_borra_la_identidad_sso(cli, datos, django_user_model):
    from django.urls import reverse as rv
    ana = datos["ana"]
    # Con activos a cargo NO se puede desactivar
    r = cli.post(rv("usuarios:usuario-estado", args=[ana.pk]), {"activar": "0"}, follow=True)
    ana.refresh_from_db()
    assert ana.is_active is True
    assert django_user_model.objects.filter(pk=ana.pk).exists()

    # Liberando el equipo, la baja es lógica y reversible
    datos["asignado"].usuario_asignado = None
    datos["asignado"].save(update_fields=["usuario_asignado"])
    cli.post(rv("usuarios:usuario-estado", args=[ana.pk]), {"activar": "0"})
    ana.refresh_from_db()
    assert ana.is_active is False
    assert django_user_model.objects.filter(pk=ana.pk).exists()   # nunca se borra

    cli.post(rv("usuarios:usuario-estado", args=[ana.pk]), {"activar": "1"})
    ana.refresh_from_db()
    assert ana.is_active is True


def test_no_puedo_desactivarme_a_mi_mismo(cli, datos):
    from django.urls import reverse as rv
    admin = datos["admin"]
    cli.post(rv("usuarios:usuario-estado", args=[admin.pk]), {"activar": "0"})
    admin.refresh_from_db()
    assert admin.is_active is True


def test_finalizar_mantenimiento_requiere_post(cli, mantenimiento):
    from django.urls import reverse as rv
    assert cli.get(rv("mantenimientos:mantenimiento-finalizar", args=[mantenimiento.pk])).status_code == 405
    mantenimiento.refresh_from_db()
    assert mantenimiento.estado == "EP"


def test_finalizar_mantenimiento_devuelve_el_activo_a_servicio(cli, datos, mantenimiento):
    from django.urls import reverse as rv
    datos["asignado"].refresh_from_db()
    assert datos["asignado"].estado == "EM"          # el alta lo sacó de servicio

    r = cli.post(rv("mantenimientos:mantenimiento-finalizar", args=[mantenimiento.pk]),
                 {"next": rv("mantenimientos:mantenimiento-list")})
    assert r.status_code == 302
    assert r.url == rv("mantenimientos:mantenimiento-list")
    mantenimiento.refresh_from_db()
    datos["asignado"].refresh_from_db()
    assert mantenimiento.estado == "FI"
    assert datos["asignado"].estado == "AC"


def test_finalizar_no_acepta_redirect_externo(cli, mantenimiento):
    from django.urls import reverse as rv
    r = cli.post(rv("mantenimientos:mantenimiento-finalizar", args=[mantenimiento.pk]),
                 {"next": "https://malicioso.example.com/"})
    assert r.status_code == 302
    assert "malicioso" not in r.url
