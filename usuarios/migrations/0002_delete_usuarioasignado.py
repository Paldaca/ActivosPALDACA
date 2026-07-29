from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("usuarios", "0002_usuarioasignado_pdf_asignacion"),
        ("activos", "0003_usuario_asignado_core"),
    ]

    operations = [
        migrations.DeleteModel(
            name="UsuarioAsignado",
        ),
    ]
