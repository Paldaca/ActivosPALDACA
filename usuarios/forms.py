from django import forms
from django.contrib.auth import get_user_model

from core.models import Perfil

UserModel = get_user_model()


class UsuarioForm(forms.ModelForm):
    """Gestión en Activos sobre campos nativos de core.UsuarioPaldaca."""

    class Meta:
        model = UserModel
        fields = [
            "first_name",
            "last_name",
            "email",
            "telefono",
            "perfil",
            "is_active",
        ]
        labels = {
            "first_name": "Nombres",
            "last_name": "Apellidos",
            "email": "Correo electrónico",
            "telefono": "Teléfono",
            "perfil": "Perfil",
            "is_active": "Usuario activo",
        }
        widgets = {
            "first_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Nombres del usuario"}
            ),
            "last_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Apellidos del usuario"}
            ),
            "email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "correo@ejemplo.com"}
            ),
            "telefono": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Número de teléfono"}
            ),
            "perfil": forms.Select(
                attrs={"class": "form-select ax-combo-native"},
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["email"].required = False
        self.fields["telefono"].required = False
        self.fields["perfil"].required = False
        self.fields["perfil"].queryset = Perfil.objects.order_by("nombre")
        self.fields["perfil"].empty_label = "Sin perfil asignado"
