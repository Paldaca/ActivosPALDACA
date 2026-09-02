from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from .models import Activo, Categoria, SubCategoria, Ubicacion


def usuarios_asignables():
    """Personas que pueden ser responsables de un activo, en orden alfabético.

    Los superusuarios del ecosistema (SSO/admin global) no reciben activos:
    no aparecen en selectores ni en la gestión de personas del módulo.
    """
    return get_user_model().objects.filter(
        is_active=True,
        is_superuser=False,
    ).order_by("last_name", "first_name", "username")


#: Alias interno histórico.
_usuarios_asignables_queryset = usuarios_asignables


def _label_usuario(user):
    nombre = user.get_full_name().strip()
    return nombre or user.username


def _validar_usuario_asignable(usuario):
    """Rechaza superusuarios (y cuentas inactivas) como responsables."""
    if usuario is None:
        return
    if getattr(usuario, "is_superuser", False):
        raise ValidationError(
            "Los superusuarios no pueden tener activos asignados."
        )
    if not getattr(usuario, "is_active", True):
        raise ValidationError(
            "No se puede asignar un activo a un usuario inactivo."
        )

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
                'class': 'form-select'
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


class ActivoForm(forms.ModelForm):
    """Formulario para Activo"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["usuario_asignado"]
        field.queryset = _usuarios_asignables_queryset()
        field.required = False
        field.label_from_instance = _label_usuario

    def clean_usuario_asignado(self):
        usuario = self.cleaned_data.get("usuario_asignado")
        _validar_usuario_asignable(usuario)
        return usuario

    class Meta:
        model = Activo
        fields = [
            'subcategoria', 'marca', 'modelo', 'numero_serial',
            'usuario_asignado', 'ubicacion',
            'observaciones', 'estado'
        ]
        widgets = {
            'subcategoria': forms.Select(attrs={
                'class': 'form-select',
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
            # `ax-combo-native` activa el buscador de personas de activos-ui.js.
            'usuario_asignado': forms.Select(attrs={
                'class': 'form-select ax-combo-native'
            }),
            'ubicacion': forms.Select(attrs={
                'class': 'form-select'
            }),
            'observaciones': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Observaciones adicionales (opcional)'
            }),
            'estado': forms.Select(attrs={
                'class': 'form-select'
            })
        }


class ActivoFilterForm(forms.Form):
    """Formulario para filtrar activos"""
    categoria = forms.ModelChoiceField(
        queryset=Categoria.objects.all(),
        required=False,
        empty_label="Todas las categorías",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    subcategoria = forms.ModelChoiceField(
        queryset=SubCategoria.objects.select_related("categoria"),
        required=False,
        empty_label="Todas las subcategorías",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    ubicacion = forms.ModelChoiceField(
        queryset=Ubicacion.objects.all(),
        required=False,
        empty_label="Todas las ubicaciones",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    estado = forms.ChoiceField(
        choices=[('', 'Todos los estados')] + list(Activo.EstadoActivo.choices),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    buscar = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por código, marca o modelo...'
        })
    )


class ReasignarActivoForm(forms.ModelForm):
    """Formulario para reasignar activo a otro usuario"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["usuario_asignado"]
        field.queryset = _usuarios_asignables_queryset()
        field.required = False
        field.label_from_instance = _label_usuario

    def clean_usuario_asignado(self):
        usuario = self.cleaned_data.get("usuario_asignado")
        _validar_usuario_asignable(usuario)
        return usuario

    class Meta:
        model = Activo
        fields = ['usuario_asignado']
        widgets = {
            'usuario_asignado': forms.Select(attrs={
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
                'class': 'form-select'
            })
        }



class EtiquetaFilterForm(forms.Form):
    """Filtros de catálogo para el listado de etiquetas QR."""

    categoria = forms.ModelChoiceField(
        queryset=Categoria.objects.all(),
        required=False,
        empty_label="Todas las categorías",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    subcategoria = forms.ModelChoiceField(
        queryset=SubCategoria.objects.select_related("categoria"),
        required=False,
        empty_label="Todas las subcategorías",
        widget=forms.Select(attrs={"class": "form-select"}),
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
        widget=forms.Select(attrs={"class": "form-select"}),
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


class AltaDesdeEtiquetaForm(forms.ModelForm):
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
        field = self.fields["usuario_asignado"]
        field.queryset = _usuarios_asignables_queryset()
        field.required = False
        field.label_from_instance = _label_usuario
        field.empty_label = "Sin asignar por ahora"

    def clean_usuario_asignado(self):
        usuario = self.cleaned_data.get("usuario_asignado")
        _validar_usuario_asignable(usuario)
        return usuario

    class Meta:
        model = Activo
        fields = [
            "marca", "modelo", "numero_serial",
            "ubicacion", "usuario_asignado", "observaciones",
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
            "ubicacion": forms.Select(attrs={"class": "form-select"}),
            "usuario_asignado": forms.Select(attrs={"class": "form-select"}),
            "observaciones": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Golpes, faltantes, accesorios… (opcional)",
            }),
        }
