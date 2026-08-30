"""Remove on-disk planilla storage fields."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("activos", "0007_planilla_asignacion"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="activo",
            name="planilla_generada_en",
        ),
        migrations.RemoveField(
            model_name="activo",
            name="planilla_pdf",
        ),
        migrations.RemoveField(
            model_name="historialmovimiento",
            name="archivo_planilla",
        ),
    ]
