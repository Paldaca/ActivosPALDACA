from django import forms
from .models import Mantenimiento


class MantenimientoForm(forms.ModelForm):
    """Formulario para crear y editar mantenimientos"""
    
    class Meta:
        model = Mantenimiento
        fields = ['activo', 'tecnico', 'telefono', 'descripcion', 'costo', 'estado']
        widgets = {
            # `readonly` no existe para <select>: era un atributo inerte que daba
            # falsa sensación de bloqueo. Se sustituye por el buscador del kit,
            # que además hace manejable una lista de cientos de activos.
            'activo': forms.Select(attrs={
                'class': 'form-select ax-combo-native',
            }),
            'tecnico': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre completo del técnico'
            }),
            'telefono': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: +57 300 123 4567'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe el mantenimiento realizado o a realizar...'
            }),
            'costo': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'estado': forms.Select(attrs={
                'class': 'form-select'
            }),
        }
        labels = {
            'activo': 'Activo',
            'tecnico': 'Técnico Responsable',
            'telefono': 'Teléfono de Contacto',
            'descripcion': 'Descripción del Mantenimiento',
            'costo': 'Costo ($)',
            'estado': 'Estado del Mantenimiento',
        }


class MantenimientoFilterForm(forms.Form):
    """Formulario para filtrar mantenimientos"""
    
    estado = forms.ChoiceField(
        choices=[('', 'Todos')] + list(Mantenimiento.EstadoMantenimiento.choices),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    activo = forms.ModelChoiceField(
        queryset=None,  # Se configurará en la vista
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label='Todos los activos'
    )
    buscar = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por técnico, descripción...'
        })
    )
    mes = forms.ChoiceField(
        choices=[('', 'Todos los meses')] + [
            ('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'), ('4', 'Abril'),
            ('5', 'Mayo'), ('6', 'Junio'), ('7', 'Julio'), ('8', 'Agosto'),
            ('9', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    año = forms.ChoiceField(
        choices=[],  # Se llenará dinámicamente
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        from activos.models import Activo
        from datetime import datetime
        super().__init__(*args, **kwargs)
        self.fields['activo'].queryset = (
            Activo.objects.select_related('subcategoria').order_by('codigo_inventario')
        )
        
        # Generar años disponibles (del año actual hacia atrás 5 años)
        current_year = datetime.now().year
        years = [('', 'Todos los años')] + [(str(y), str(y)) for y in range(current_year, current_year - 6, -1)]
        self.fields['año'].choices = years
