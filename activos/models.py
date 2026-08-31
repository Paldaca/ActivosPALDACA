import re
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

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
        """Siguiente código libre de la subcategoría.

        Delega en el servicio porque el número ya no depende solo de esta tabla:
        las etiquetas QR impresas apartan códigos antes de que exista el activo.
        """
        from .services.codigos import siguiente_codigo

        return siguiente_codigo(self.subcategoria)

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError

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

        # `reservar_codigos()` (dentro de `_generar_codigo_inventario`) suelta su
        # bloqueo de la subcategoría en cuanto CALCULA el código: es la propia
        # función la que abre y cierra su `transaction.atomic()`. Si el INSERT
        # ocurriera fuera de ese envoltorio —como pasaba aquí antes—, el
        # bloqueo ya estaría liberado cuando `super().save()` corre, y dos
        # altas manuales simultáneas para la misma subcategoría podían volver
        # a calcular el mismo siguiente número: justo la carrera que ese
        # servicio existe para cerrar. Envolver aquí hace que el `atomic()`
        # interno anide como savepoint y el bloqueo de fila persista hasta que
        # ESTE bloque confirma, con el INSERT ya dentro.
        with transaction.atomic():
            if not self.codigo_inventario:
                self.codigo_inventario = self._generar_codigo_inventario()
            self.codigo_inventario = self.codigo_inventario.upper().strip()
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
        PLANILLA = "PA", "Planilla"

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
    archivo_planilla = models.FileField(
        upload_to="planillas/historial/",
        blank=True,
        null=True,
    )

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


class EtiquetaQR(models.Model):
    """Etiqueta QR física pegada sobre un activo.

    Es una entidad propia y no un campo de `Activo` porque nace ANTES que él:
    al comprar un lote se imprimen las etiquetas con su código ya apartado, y
    los activos se registran después, escaneándolas. `Activo` exige marca,
    modelo y ubicación, así que no admite filas a medias que hicieran de
    marcador de posición.

    Modelarla aparte tiene tres consecuencias buenas: la URL impresa nunca
    cambia (el token vive aquí de principio a fin), reimprimir no tiene efectos
    secundarios, y si el activo se borra la etiqueta sobrevive y puede
    responder "este código ya no está en uso" en lugar de un 404 ciego.
    """

    #: Bytes de entropía del token. 9 -> 12 caracteres base64url (72 bits).
    #: Se mantiene corto a propósito: cada carácter de la URL sube la densidad
    #: del QR, y a 22 mm de lado el módulo ya baja de 0,75 mm.
    TOKEN_BYTES = 9

    #: Intentos ante la (improbable) colisión de token.
    MAX_INTENTOS_TOKEN = 5

    class EstadoEtiqueta(models.TextChoices):
        PENDIENTE = "PE", "Pendiente"
        VINCULADA = "VI", "Vinculada"
        ANULADA = "AN", "Anulada"

    token = models.CharField(
        max_length=16,
        unique=True,
        editable=False,
        help_text="Identificador opaco que viaja en el QR. Inmutable.",
    )
    codigo_reservado = models.CharField(
        max_length=50,
        unique=True,
        help_text="Código de inventario apartado al imprimir; se traspasa al activo.",
    )
    subcategoria = models.ForeignKey(
        SubCategoria,
        on_delete=models.PROTECT,
        related_name="etiquetas",
    )
    activo = models.ForeignKey(
        Activo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="etiquetas",
    )
    estado = models.CharField(
        max_length=2,
        choices=EstadoEtiqueta.choices,
        default=EstadoEtiqueta.PENDIENTE,
    )
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="etiquetas_generadas",
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_vinculacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = TABLA("etiqueta_qr")
        verbose_name = "Etiqueta QR"
        verbose_name_plural = "Etiquetas QR"
        ordering = ["-fecha_creacion", "codigo_reservado"]
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["estado"]),
            models.Index(fields=["subcategoria"]),
        ]
        constraints = [
            # Un activo puede acumular etiquetas anuladas (adhesivo perdido,
            # pegado en el equipo equivocado), pero solo una vigente.
            models.UniqueConstraint(
                fields=["activo"],
                condition=models.Q(estado="VI"),
                name="activos_etiqueta_qr_una_vigente_por_activo",
            ),
        ]

    def __str__(self):
        return f"{self.codigo_reservado} ({self.get_estado_display()})"

    # -- ciclo de vida -----------------------------------------------------

    @classmethod
    def generar_token(cls):
        """Token libre. La colisión es teórica; el reintento la vuelve nula."""
        for _ in range(cls.MAX_INTENTOS_TOKEN):
            candidato = secrets.token_urlsafe(cls.TOKEN_BYTES)
            if not cls.objects.filter(token=candidato).exists():
                return candidato
        raise RuntimeError(
            "No se pudo generar un token de etiqueta libre. "
            "Revisa el tamaño del espacio de tokens."
        )

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = self.generar_token()
        if self.codigo_reservado:
            self.codigo_reservado = self.codigo_reservado.upper().strip()
        super().save(*args, **kwargs)

    @property
    def esta_pendiente(self):
        return self.estado == self.EstadoEtiqueta.PENDIENTE

    @property
    def esta_vinculada(self):
        return self.estado == self.EstadoEtiqueta.VINCULADA and self.activo_id is not None

    def vincular(self, activo):
        """Ata la etiqueta a un activo. Idempotente.

        Reintentar la misma vinculación (doble envío del formulario del móvil,
        reintento de red) no debe crear nada ni mover la fecha original.
        """
        if self.activo_id == activo.pk and self.esta_vinculada:
            return self

        if self.estado == self.EstadoEtiqueta.ANULADA:
            raise ValidationError("Esta etiqueta está anulada y no puede vincularse.")
        if self.activo_id and self.activo_id != activo.pk:
            raise ValidationError(
                f"La etiqueta {self.codigo_reservado} ya pertenece a otro activo."
            )

        self.activo = activo
        self.estado = self.EstadoEtiqueta.VINCULADA
        self.fecha_vinculacion = timezone.now()
        self.save(update_fields=["activo", "estado", "fecha_vinculacion"])
        return self

    def desvincular(self):
        """Suelta el activo dejando la etiqueta reutilizable.

        Para el caso real de pegar el adhesivo en el equipo equivocado: se
        despega, se suelta aquí y vuelve a quedar pendiente con su código.
        """
        self.activo = None
        self.estado = self.EstadoEtiqueta.PENDIENTE
        self.fecha_vinculacion = None
        self.save(update_fields=["activo", "estado", "fecha_vinculacion"])
        return self

    def anular(self):
        """Retira la etiqueta de circulación: su URL deja de resolver.

        El código NO se libera: reutilizarlo dejaría dos adhesivos distintos
        con el mismo número impreso, uno de ellos por ahí pegado a un equipo.
        """
        self.estado = self.EstadoEtiqueta.ANULADA
        self.save(update_fields=["estado"])
        return self
