"""Restore planilla file on history movements for audit."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("activos", "0008_remove_planilla_storage"),
    ]

    operations = [
        migrations.AddField(
            model_name="historialmovimiento",
            name="archivo_planilla",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="planillas/historial/",
            ),
        ),
    ]
