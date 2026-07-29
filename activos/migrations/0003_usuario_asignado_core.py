import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def migrate_usuario_asignado_to_core(apps, schema_editor):
    """
    Mapea usuarios_usuarioasignado -> core_usuario y actualiza FKs en activos_activo.
    tabla_vieja: usuarios_usuarioasignado -> core_usuario
    """
    UsuarioAsignado = apps.get_model("usuarios", "UsuarioAsignado")
    UsuarioPaldaca = apps.get_model("core", "UsuarioPaldaca")
    Activo = apps.get_model("activos", "Activo")

    id_map = {}
    for legacy in UsuarioAsignado.objects.all().iterator():
        user = None
        email = (legacy.email or "").strip()
        if email:
            user = UsuarioPaldaca.objects.filter(email=email).first()
        identificacion = legacy.identificacion.strip()
        if not user:
            user = UsuarioPaldaca.objects.filter(username=identificacion).first()
        if not user:
            user = UsuarioPaldaca(
                username=identificacion,
                email=email,
                first_name=legacy.nombres,
                last_name=legacy.apellidos,
                is_active=legacy.activo,
            )
            user.set_unusable_password()
            user.save()
        id_map[legacy.pk] = user.pk

    for activo in Activo.objects.exclude(usuario_asignado_id__isnull=True).iterator():
        new_id = id_map.get(activo.usuario_asignado_id)
        if new_id:
            Activo.objects.filter(pk=activo.pk).update(usuario_asignado_id=new_id)


class Migration(migrations.Migration):

    dependencies = [
        ("activos", "0003_subcategoria_prefijo"),
        ("usuarios", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(
            migrate_usuario_asignado_to_core,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="activo",
            name="usuario_asignado",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="activos_asignados",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
