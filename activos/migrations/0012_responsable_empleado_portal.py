"""Responsable del activo = empleado de Nomina (tabla portal_empleado del Portal).

Fase 1 (esta migracion): la FK anterior a core_usuario se conserva como
`usuario_legacy` y se crea `responsable`. Si el Portal ya creo y sincronizo
`portal_empleado`, las asignaciones se copian aqui mismo; si no, o para lo que
quede pendiente, `python manage.py vincular_responsables`.

Fase 2 (futura): eliminar `usuario_legacy` cuando no quede ningun pendiente.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def copiar_asignaciones(apps, schema_editor):
    from activos.services.responsables import (
        tabla_empleados_disponible,
        vincular_responsables,
    )

    if not tabla_empleados_disponible(schema_editor.connection):
        return
    vincular_responsables(
        apps.get_model("activos", "Activo"),
        apps.get_model("activos", "EmpleadoPortal"),
    )


def vaciar_marcadores(apps, schema_editor):
    apps.get_model("activos", "AvisoUsuarioInactivo").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("activos", "0011_aviso_por_umbral"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EmpleadoPortal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nomina_id", models.PositiveIntegerField(unique=True)),
                ("cedula", models.CharField(max_length=20)),
                ("nombres", models.CharField(max_length=100)),
                ("apellidos", models.CharField(max_length=100)),
                ("cargo", models.CharField(blank=True, default="", max_length=100)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("telefono", models.CharField(blank=True, default="", max_length=30)),
                ("activo", models.BooleanField(default=True)),
                ("sincronizado_en", models.DateTimeField(blank=True, null=True)),
                (
                    "usuario",
                    models.OneToOneField(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="empleado_portal",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Empleado",
                "verbose_name_plural": "Empleados",
                "db_table": "portal_empleado",
                "ordering": ("apellidos", "nombres"),
                "managed": False,
            },
        ),
        migrations.RenameField(
            model_name="activo",
            old_name="usuario_asignado",
            new_name="usuario_legacy",
        ),
        migrations.AlterField(
            model_name="activo",
            name="usuario_legacy",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="activos_legacy",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="activo",
            name="responsable",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="activos_asignados",
                to="activos.empleadoportal",
            ),
        ),
        # Los marcadores de aviso eran por cuenta; ahora son por empleado. Se
        # descartan: a lo sumo el despachador repite un aviso una vez.
        migrations.RunPython(vaciar_marcadores, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="avisousuarioinactivo",
            name="usuario",
        ),
        # Nullable primero y obligatorio despues (la tabla ya esta vacia): un
        # `default=0` lo rechaza MySQL para una FK a un AutoField.
        migrations.AddField(
            model_name="avisousuarioinactivo",
            name="empleado",
            field=models.OneToOneField(
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="aviso_inactivo_activos",
                to="activos.empleadoportal",
            ),
        ),
        migrations.AlterField(
            model_name="avisousuarioinactivo",
            name="empleado",
            field=models.OneToOneField(
                db_constraint=False,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="aviso_inactivo_activos",
                to="activos.empleadoportal",
            ),
        ),
        migrations.AlterModelOptions(
            name="avisousuarioinactivo",
            options={
                "verbose_name": "Aviso de empleado de baja",
                "verbose_name_plural": "Avisos de empleado de baja",
            },
        ),
        migrations.RunPython(copiar_asignaciones, migrations.RunPython.noop),
    ]
