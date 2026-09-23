from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import Activo, Categoria, EmpleadoPortal, SubCategoria, Ubicacion


def empleados_asignables():
    """Empleados de Nomina activos: los unicos que pueden recibir un equipo."""
    return EmpleadoPortal.objects.filter(activo=True).order_by("apellidos", "nombres")


def etiqueta_empleado(empleado):
    cargo = (empleado.cargo or "").strip()
    return f"{empleado.nombre_completo} — {cargo}" if cargo else empleado.nombre_completo


class ResponsableFormMixin:
    """Campo `responsable` (empleado de Nomina) comun a los formularios de activo.

    El responsable actual se admite aunque este dado de baja en Nomina: si no,
    editar cualquier otro campo del activo fallaria con "elige una opcion
    valida". Lo que no se permite es ELEGIR a alguien de baja.
    """

    def _configurar_responsable(self, empty_label=None):
        field = self.fields["responsable"]
        actual = self.instance.responsable_id if self.instance else None
        field.queryset = (
            EmpleadoPortal.objects.filter(Q(activo=True) | Q(pk=actual))
            if actual
            else empleados_asignables()
        )
        field.required = False
        field.label = "Responsable"
        field.label_from_instance = etiqueta_empleado
        if empty_label:
            field.empty_label = empty_label

    def clean_responsable(self):
        empleado = self.cleaned_data.get("responsable")
        if empleado is not None and not empleado.activo and "responsable" in self.changed_data:
            raise ValidationError("Ese empleado está dado de baja en Nómina.")
        return empleado

    def save(self, commit=True):
        if "responsable" in self.changed_data:
            # Una asignacion explicita cierra la fase 1 de la migracion.
            self.instance.usuario_legacy = None
        return super().save(commit)


class CategoriaForm(forms.ModelForm):
    """Formulario para Categoría"""
    class Meta:
        model = Categoria
        fields = ['nombre']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre de la categoría'
            })
        }


class SubCategoriaForm(forms.ModelForm):
    """Formulario para SubCategoría"""
    class Meta:
        model = SubCategoria
        fields = ['nombre', 'prefijo', 'categoria']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre de la subcategoría'
            }),
            'prefijo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: D',
                'maxlength': 5
            }),
            'categoria': forms.Select(attrs={
                'class': 'form-select ax-combo-native'
            })
        }

    def clean_prefijo(self):
        prefijo = (self.cleaned_data.get('prefijo') or '').strip().upper()
        return prefijo


class UbicacionForm(forms.ModelForm):
    """Formulario para Ubicación"""
    class Meta:
        model = Ubicacion
        fields = ['nombre']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre de la ubicación'
            })
        }


class ActivoForm(ResponsableFormMixin, forms.ModelForm):
    """Formulario para Activo"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._configurar_responsable()

    class Meta:
        model = Activo
        fields = [
            'subcategoria', 'marca', 'modelo', 'numero_serial',
            'responsable', 'ubicacion',
            'observaciones', 'estado'
        ]
        widgets = {
            'subcategoria': forms.Select(attrs={
                'class': 'form-select ax-combo-native',
                'id': 'id_subcategoria'
            }),
            'marca': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Marca del activo'
            }),
            'modelo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Modelo del activo'
            }),
            'numero_serial': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Número de serie (opcional)'
            }),
            # `ax-combo-native` activa el buscador de empleados de activos-ui.js.
            'responsable': forms.Select(attrs={
                'class': 'form-select ax-combo-native'
            }),
            'ubicacion': forms.Select(attrs={
                'class': 'form-select ax-combo-native'
            }),
            'observaciones': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Observaciones adicionales (opcional)'
            }),
            'estado': forms.Select(attrs={
                'class': 'form-select ax-combo-native'
            })
        }


class ActivoFilterForm(forms.Form):
    """Formulario para filtrar activos"""
    categoria = forms.ModelChoiceField(
        queryset=Categoria.objects.all(),
        required=False,
        empty_label="Todas las categorías",
        widget=forms.Select(attrs={'class': 'form-select ax-combo-native'})
    )
    subcategoria = forms.ModelChoiceField(
        queryset=SubCategoria.objects.select_related("categoria"),
        required=False,
        empty_label="Todas las subcategorías",
        widget=forms.Select(attrs={'class': 'form-select ax-combo-native'})
    )
    ubicacion = forms.ModelChoiceField(
        queryset=Ubicacion.objects.all(),
        required=False,
        empty_label="Todas las ubicaciones",
        widget=forms.Select(attrs={'class': 'form-select ax-combo-native'})
    )
    estado = forms.ChoiceField(
        choices=[('', 'Todos los estados')] + list(Activo.EstadoActivo.choices),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select ax-combo-native'})
    )
    buscar = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por código, marca o modelo...'
        })
    )


class ReasignarActivoForm(ResponsableFormMixin, forms.ModelForm):
    """Formulario para reasignar activo a otro empleado"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._configurar_responsable()

    class Meta:
        model = Activo
        fields = ['responsable']
        widgets = {
            'responsable': forms.Select(attrs={
                'class': 'form-select ax-combo-native'
            })
        }


class ReubicarActivoForm(forms.ModelForm):
    """Formulario para reubicar activo"""
    class Meta:
        model = Activo
        fields = ['ubicacion']
        widgets = {
            'ubicacion': forms.Select(attrs={
                'class': 'form-select ax-combo-native'
            })
        }



class EtiquetaFilterForm(forms.Form):
    """Filtros de catálogo para el listado de etiquetas QR."""

    categoria = forms.ModelChoiceField(
        queryset=Categoria.objects.all(),
        required=False,
        empty_label="Todas las categorías",
        widget=forms.Select(attrs={"class": "form-select ax-combo-native"}),
    )
    subcategoria = forms.ModelChoiceField(
        queryset=SubCategoria.objects.select_related("categoria"),
        required=False,
        empty_label="Todas las subcategorías",
        widget=forms.Select(attrs={"class": "form-select ax-combo-native"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categoria_id = (self.data.get("categoria") or "").strip()
        if categoria_id.isdigit():
            self.fields["subcategoria"].queryset = SubCategoria.objects.filter(
                categoria_id=categoria_id,
            ).select_related("categoria")


class GenerarEtiquetasForm(forms.Form):
    """Lote de etiquetas QR a imprimir.

    Deliberadamente corto: subcategoría y cantidad son lo ÚNICO que se sabe
    cuando llega una caja de equipos sin abrir. Pedir más aquí obligaría a
    inventar datos o a retrasar la impresión, que es justo lo que este camino
    evita frente al alta manual.
    """

    #: Una hoja Letter trae 50 etiquetas (5×10). Se permiten dos hojas por lote:
    #: por encima de eso conviene revisar si de verdad se van a pegar todas,
    #: porque cada etiqueta impresa aparta un código del inventario.
    MAX_POR_LOTE = 100

    subcategoria = forms.ModelChoiceField(
        queryset=SubCategoria.objects.select_related("categoria"),
        empty_label="Selecciona una subcategoría",
        label="Subcategoría",
        help_text="Determina el prefijo del código: PAL-{PREFIJO}-NNN.",
        widget=forms.Select(attrs={"class": "form-select ax-combo-native"}),
    )
    cantidad = forms.IntegerField(
        min_value=1,
        max_value=MAX_POR_LOTE,
        initial=1,
        label="Cantidad de etiquetas",
        help_text=f"Entre 1 y {MAX_POR_LOTE}. Una hoja Letter son 50.",
        widget=forms.NumberInput(attrs={
            "class": "form-control",
            "inputmode": "numeric",
            "min": 1,
            "max": MAX_POR_LOTE,
        }),
    )


class AltaDesdeEtiquetaForm(ResponsableFormMixin, forms.ModelForm):
    """Alta de un activo escaneando su etiqueta, pensada para el móvil.

    Frente a `ActivoForm` faltan dos campos a propósito:

    - `subcategoria` viene fijada por la etiqueta impresa. Cambiarla dejaría el
      código `PAL-{PREFIJO}-NNN` del adhesivo mintiendo sobre lo que hay dentro.
    - `estado` no se pregunta: un equipo que se acaba de registrar en campo está
      operativo. Darlo de baja o mandarlo a mantenimiento es una decisión
      posterior, y se toma desde el escritorio.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._configurar_responsable(empty_label="Sin asignar por ahora")

    class Meta:
        model = Activo
        fields = [
            "marca", "modelo", "numero_serial",
            "ubicacion", "responsable", "observaciones",
        ]
        widgets = {
            "marca": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Lenovo",
                "autocomplete": "off",
                "autocapitalize": "words",
            }),
            "modelo": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: ThinkPad T14",
                "autocomplete": "off",
            }),
            "numero_serial": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "El de la pegatina del equipo (opcional)",
                "autocomplete": "off",
                "autocapitalize": "characters",
            }),
            "ubicacion": forms.Select(attrs={"class": "form-select ax-combo-native"}),
            "responsable": forms.Select(attrs={
                "class": "form-select ax-combo-native",
            }),
            "observaciones": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Golpes, faltantes, accesorios… (opcional)",
            }),
        }
