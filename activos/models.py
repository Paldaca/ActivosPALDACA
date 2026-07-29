import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .constants import TABLA


class Categoria(models.Model):
    """Categoría principal de activos"""

    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = TABLA("categoria")
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class SubCategoria(models.Model):
    """Subcategoría de activos"""

    nombre = models.CharField(max_length=100)
    prefijo = models.CharField(max_length=5, unique=True)
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.PROTECT,
        related_name="subcategorias",
    )

    class Meta:
        db_table = TABLA("subcategoria")
        verbose_name = "Subcategoría"
        verbose_name_plural = "Subcategorías"
        ordering = ["categoria", "nombre"]
        unique_together = [["nombre", "categoria"]]

    def __str__(self):
        return f"{self.categoria.nombre} - {self.nombre}"

    def clean(self):
        super().clean()
        if self.prefijo:
            self.prefijo = self.prefijo.strip().upper()
            if not re.match(r'^[A-Z0-9]{1,5}$', self.prefijo):
                raise ValidationError({'prefijo': 'El prefijo solo puede contener letras y números (máx. 5).'})


class Ubicacion(models.Model):
    """Ubicación física de los activos"""

    nombre = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = TABLA("ubicacion")
        verbose_name = "Ubicación"
        verbose_name_plural = "Ubicaciones"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Activo(models.Model):
    """Activo del sistema"""

    class EstadoActivo(models.TextChoices):
        ACTIVO = "AC", "Activo"
        INACTIVO = "IN", "Inactivo"
        EN_MANTENIMIENTO = "EM", "En Mantenimiento"

    subcategoria = models.ForeignKey(
        SubCategoria,
        on_delete=models.PROTECT,
        related_name="activos",
    )
    marca = models.CharField(max_length=100)
    modelo = models.CharField(max_length=100)
    numero_serial = models.CharField(max_length=100, blank=True, null=True)
    codigo_inventario = models.CharField(max_length=50, unique=True)

    usuario_asignado = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activos_asignados",
    )

    ubicacion = models.ForeignKey(
        Ubicacion,
        on_delete=models.PROTECT,
        related_name="activos",
    )
    observaciones = models.TextField(blank=True, null=True)
    estado = models.CharField(
        max_length=2,
        choices=EstadoActivo.choices,
        default=EstadoActivo.ACTIVO,
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = TABLA("activo")
        verbose_name = "Activo"
        verbose_name_plural = "Activos"
        ordering = ["-fecha_creacion"]
        indexes = [
            models.Index(fields=["codigo_inventario"]),
            models.Index(fields=["estado"]),
            models.Index(fields=["subcategoria"]),
        ]

    def __str__(self):
        return f"{self.codigo_inventario} - {self.marca} {self.modelo}"

    @property
    def categoria(self):
        return self.subcategoria.categoria

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        if self.codigo_inventario:
            self.codigo_inventario = self.codigo_inventario.upper().strip()
        usuario = self.usuario_asignado
        if usuario is not None and getattr(usuario, "is_superuser", False):
            raise ValidationError(
                {
                    "usuario_asignado": (
                        "Los superusuarios no pueden tener activos asignados."
                    )
                }
            )
    def _generar_codigo_inventario(self):
        prefijo = self.subcategoria.prefijo.strip().upper()
        base = f"PAL-{prefijo}-"
        codigos = Activo.objects.filter(
            codigo_inventario__startswith=base
        ).values_list('codigo_inventario', flat=True)
        ultimo = 0
        for codigo in codigos:
            try:
                numero = int(codigo.split('-')[-1])
            except (ValueError, IndexError):
                continue
            if numero > ultimo:
                ultimo = numero
        return f"{base}{ultimo + 1:03d}"

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError

        if not self.codigo_inventario:
            self.codigo_inventario = self._generar_codigo_inventario()
        self.codigo_inventario = self.codigo_inventario.upper().strip()
        if self.usuario_asignado_id:
            usuario = self.usuario_asignado
            if usuario is not None and usuario.is_superuser:
                raise ValidationError(
                    {
                        "usuario_asignado": (
                            "Los superusuarios no pueden tener activos asignados."
                        )
                    }
                )
        super().save(*args, **kwargs)


class HistorialMovimiento(models.Model):
    """Historial de movimientos y cambios de activos"""

    class TipoMovimiento(models.TextChoices):
        CREACION = "CR", "Creación"
        ACTUALIZACION = "AC", "Actualización"
        REASIGNACION = "RE", "Reasignación"
        REUBICACION = "RU", "Reubicación"
        CAMBIO_ESTADO = "CE", "Cambio de Estado"
        ELIMINACION = "EL", "Eliminación"

    activo = models.ForeignKey(
        Activo,
        on_delete=models.CASCADE,
        related_name="historial_movimientos",
    )
    tipo_movimiento = models.CharField(
        max_length=2,
        choices=TipoMovimiento.choices,
    )
    descripcion = models.TextField()

    campo_modificado = models.CharField(max_length=100, blank=True, null=True)
    valor_anterior = models.TextField(blank=True, null=True)
    valor_nuevo = models.TextField(blank=True, null=True)

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimientos_activos",
    )

    fecha_movimiento = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = TABLA("historial_movimiento")
        verbose_name = "Historial de Movimiento"
        verbose_name_plural = "Historial de Movimientos"
        ordering = ["-fecha_movimiento"]
        indexes = [
            models.Index(fields=["activo", "-fecha_movimiento"]),
            models.Index(fields=["tipo_movimiento"]),
        ]

    def __str__(self):
        return (
            f"{self.activo.codigo_inventario} - "
            f"{self.get_tipo_movimiento_display()} - "
            f"{self.fecha_movimiento.strftime('%d/%m/%Y %H:%M')}"
        )
