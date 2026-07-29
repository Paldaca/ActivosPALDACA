from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from activos.decorators import ModuloActivoRequiredMixin, requiere_modulo_paldaca
from activos.forms import usuarios_asignables

from .forms import UsuarioForm

UserModel = get_user_model()


def _usuarios_gestion_queryset():
    """Base de gestión: incluye inactivos, excluye superusuarios.

    Antes se filtraba por `is_active=True`, así que un usuario desactivado
    desaparecía del buscador y no había forma de reactivarlo desde la interfaz.
    El filtro de estado ahora es explícito y reversible.

    Los superusuarios no son personas asignables de inventario: no se listan
    ni se editan desde este módulo.
    """
    return (
        UserModel.objects.filter(is_superuser=False)
        .select_related("perfil")
        .annotate(num_activos=Count("activos_asignados", distinct=True))
    )


class UsuarioSearchView(ModuloActivoRequiredMixin, ListView):
    """Buscador de personas asignables (core_usuario)."""

    model = UserModel
    template_name = "usuarios/usuario_search.html"
    context_object_name = "usuarios"
    paginate_by = 20

    def get_queryset(self):
        queryset = _usuarios_gestion_queryset()

        estado = self.request.GET.get("estado", "activos")
        if estado == "activos":
            queryset = queryset.filter(is_active=True)
        elif estado == "inactivos":
            queryset = queryset.filter(is_active=False)
        elif estado == "con_activos":
            queryset = queryset.filter(is_active=True, num_activos__gt=0)
        elif estado == "sin_activos":
            queryset = queryset.filter(is_active=True, num_activos=0)

        buscar = self.request.GET.get("buscar", "").strip()
        if buscar:
            # Buscar por código de inventario responde a "¿de quién es PAL-LAP-007?"
            queryset = queryset.filter(
                Q(first_name__icontains=buscar)
                | Q(last_name__icontains=buscar)
                | Q(email__icontains=buscar)
                | Q(telefono__icontains=buscar)
                | Q(perfil__nombre__icontains=buscar)
                | Q(activos_asignados__codigo_inventario__icontains=buscar)
            ).distinct()

        return queryset.order_by("last_name", "first_name", "username")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["buscar"] = self.request.GET.get("buscar", "")
        context["estado_actual"] = self.request.GET.get("estado", "activos")

        base = UserModel.objects.filter(is_superuser=False).annotate(
            num_activos=Count("activos_asignados", distinct=True)
        )
        context["resumen"] = {
            "total": base.filter(is_active=True).count(),
            "con_activos": base.filter(is_active=True, num_activos__gt=0).count(),
            "sin_activos": base.filter(is_active=True, num_activos=0).count(),
            "inactivos": base.filter(is_active=False).count(),
        }
        return context


class UsuarioProfileView(ModuloActivoRequiredMixin, DetailView):
    """Perfil con los activos bajo responsabilidad de la persona."""

    model = UserModel
    template_name = "usuarios/usuario_profile.html"
    context_object_name = "usuario"

    def get_queryset(self):
        return UserModel.objects.filter(is_superuser=False).select_related(
            "perfil", "disciplina"
        )
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        activos = self.object.activos_asignados.select_related(
            "subcategoria__categoria", "ubicacion"
        ).order_by("subcategoria__categoria__nombre", "codigo_inventario")
        context["activos_asignados"] = activos
        context["total_activos"] = activos.count()
        context["en_mantenimiento"] = activos.filter(estado="EM").count()
        # Alimenta el drawer de reasignación rápida desde la propia ficha.
        context["usuarios_asignables"] = usuarios_asignables()
        return context


class UsuarioCreateView(ModuloActivoRequiredMixin, CreateView):
    model = UserModel
    form_class = UsuarioForm
    template_name = "usuarios/usuario_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f"{self.object.get_full_name()} se registró correctamente.",
        )
        return response

    def get_success_url(self):
        # Tras crear a alguien lo habitual es asignarle equipos: se abre su ficha.
        return reverse("usuarios:usuario-profile", kwargs={"pk": self.object.pk})


class UsuarioUpdateView(ModuloActivoRequiredMixin, UpdateView):
    model = UserModel
    form_class = UsuarioForm
    template_name = "usuarios/usuario_form.html"

    def get_queryset(self):
        return UserModel.objects.filter(is_superuser=False).select_related("perfil")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Datos actualizados correctamente.")
        return response

    def get_success_url(self):
        return reverse("usuarios:usuario-profile", kwargs={"pk": self.object.pk})


@require_POST
@requiere_modulo_paldaca
def cambiar_estado_usuario(request, pk):
    """Activa o desactiva a una persona. NUNCA borra la fila de core_usuario.

    `core_usuario` es la identidad compartida por todo el ecosistema Paldaca
    (SSO). Antes esto era un DeleteView cuyo `delete()` dejó de invocarse en
    Django 4.0: el flujo real terminaba en `form_valid()` -> `object.delete()`,
    que borraba la identidad en todos los programas y además se saltaba la
    comprobación de activos asignados. Ahora es una baja lógica explícita
    y reversible.
    """
    usuario = get_object_or_404(
        UserModel.objects.filter(is_superuser=False).annotate(
            num_activos=Count("activos_asignados")
        ),
        pk=pk,
    )
    nombre = usuario.get_full_name().strip() or usuario.username
    activar = request.POST.get("activar") == "1"

    if not activar:
        if usuario.pk == request.user.pk:
            messages.error(request, "No puedes desactivar tu propia cuenta.")
            return redirect("usuarios:usuario-profile", pk=pk)

        if usuario.num_activos:
            messages.error(
                request,
                f'No se puede desactivar a "{nombre}": tiene '
                f"{usuario.num_activos} activo(s) bajo su responsabilidad. "
                "Reasígnalos primero.",
            )
            return redirect("usuarios:usuario-profile", pk=pk)

    usuario.is_active = activar
    usuario.save(update_fields=["is_active"])
    messages.success(
        request,
        f'"{nombre}" {"se reactivó" if activar else "quedó desactivado"} correctamente.',
    )
    return redirect("usuarios:usuario-profile", pk=pk)
