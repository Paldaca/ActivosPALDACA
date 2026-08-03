# Reglas de negocio — ActivosPALDACA

Solo reglas **identificadas en el código**. Cada entrada indica dónde se implementa. Si no hay enforcement en vistas, se documenta explícitamente.

---

## 1. Acceso al módulo Activos (SSO / permisos)

### BR-ACC-01 — Solo usuarios autenticados acceden al módulo

- **Regla:** Toda vista de negocio exige sesión Django válida.
- **Implementación:** `activos/decorators.py` — `@login_required` (vía `@requiere_modulo_paldaca`) y `LoginRequiredMixin` en `ModuloActivoRequiredMixin`.
- **Comportamiento:** Usuario no autenticado → redirección a `settings.PALDACA_SSO_LOGIN_URL`.

### BR-ACC-02 — Acceso al programa requiere fila en `core_usuario_modulo` (salvo superuser)

- **Regla:** `user.tiene_acceso_modulo("activos")` debe ser verdadero.
- **Implementación:** `activos/decorators.py` → `_usuario_tiene_acceso()`; lógica en `core/models.py` → `UsuarioPaldaca.tiene_acceso_modulo()`.
- **Detalle del modelo:**
  - Superuser: acceso si el módulo existe y `activo=True`.
  - Resto: requiere fila en `core_usuario_modulo` con `modulo.codigo="activos"`.
  - Usuario inactivo (`is_active=False`): sin acceso.
- **Comportamiento:** Autenticado sin acceso → HTTP 403 con mensaje `"No tienes acceso a este programa."`

### BR-ACC-03 — Cambios de permisos invalidan la sesión (modo estricto)

- **Regla:** Si rol, disciplina, perfil, estado activo o módulos asignados cambian, la sesión se cierra.
- **Implementación:** `core/middleware.py` → `PaldacaSessionMiddleware`; hash en `core/models.py` → `get_auth_revision()`.
- **Configuración:** `PALDACA_STRICT_SESSION_CONSISTENCY` (default `"true"` en `SSAPI/settings.py`).

### BR-ACC-04 — Roles globales PALDACA (catálogo, no enforcement en vistas Activos)

- **Regla:** `UsuarioPaldaca.rol` ∈ `{usuario, administrador}`. Superuser tiene acceso global.
- **Implementación:** `core/models.py` — `ROL_CHOICES`, `es_administrador`, `es_administrador_en_modulo()`.
- **Limitación verificada:** Las vistas de `activos`, `mantenimientos`, `reportes` y `usuarios` **no** consultan `es_administrador_en_modulo()`. Usuario y administrador con acceso al módulo tienen las mismas capacidades en la UI actual.

---

## 2. Activos e inventario

### BR-ACT-01 — Estados almacenados del activo

- **Regla:** `Activo.estado` ∈ `AC` (Activo), `IN` (Inactivo), `EM` (En Mantenimiento). Default: `AC`.
- **Implementación:** `activos/models.py` → `EstadoActivo`.

### BR-ACT-02 — Estado operativo derivado en interfaz

- **Regla:** Lo que ve el usuario se deriva de `(estado, usuario_asignado)`:
  - `EM` → "En Mantenimiento"
  - `IN` → "Dado de Baja"
  - `AC` + sin responsable → "Disponible"
  - `AC` + con responsable → "Asignado"
- **Implementación:** `activos/templatetags/activo_filters.py` → `estado_key()`; también KPIs en `activos/views.py` → `_resumen_inventario()` y `core/views.py` → `HomeView`.

### BR-ACT-03 — Código de inventario único y normalizado

- **Regla:** `codigo_inventario` es único; se almacena en mayúsculas sin espacios extremos.
- **Implementación:** `activos/models.py` → `clean()`, `save()`; constraint en modelo (`unique=True`).

### BR-ACT-04 — Generación automática de código de inventario

- **Regla:** Si no se proporciona código al guardar, se genera `PAL-{PREFIJO_SUBCATEGORIA}-{NNN}` consecutivo (3 dígitos) por prefijo.
- **Implementación:** `activos/models.py` → `_generar_codigo_inventario()`, invocado desde `save()`.

### BR-ACT-05 — Prefijo de subcategoría

- **Regla:** `SubCategoria.prefijo` único, 1–5 caracteres alfanuméricos `[A-Z0-9]`, normalizado a mayúsculas.
- **Implementación:** `activos/models.py` → `SubCategoria.clean()`; `activos/forms.py` → `SubCategoriaForm.clean_prefijo()`.

### BR-ACT-06 — Integridad referencial al eliminar catálogos

- **Regla:**
  - No se elimina categoría con subcategorías hijas.
  - No se elimina subcategoría con activos.
  - No se elimina ubicación con activos.
- **Implementación:** `activos/views.py` — `CategoriaDeleteView`, `SubCategoriaDeleteView`, `UbicacionDeleteView` → `form_valid()` con comprobación previa; además `on_delete=PROTECT` en FKs de `Activo`.

### BR-ACT-07 — Superusuarios no pueden recibir activos

- **Regla:** Un activo no puede asignarse a un usuario con `is_superuser=True`.
- **Implementación:** `activos/models.py` → `clean()`, `save()`; `activos/forms.py` → `_validar_usuario_asignable()`.

### BR-ACT-08 — Usuarios asignables en selectores

- **Regla:** Solo usuarios `is_active=True` y `is_superuser=False` aparecen como responsables.
- **Implementación:** `activos/forms.py` → `usuarios_asignables()`.

### BR-ACT-09 — Usuarios inactivos no pueden recibir activos

- **Regla:** Validación en formularios rechaza asignación a usuario inactivo.
- **Implementación:** `activos/forms.py` → `_validar_usuario_asignable()`.

### BR-ACT-10 — Historial en reasignación y reubicación

- **Regla:** Cambios de `usuario_asignado` o `ubicacion` generan registro en `HistorialMovimiento` con tipo `RE` o `RU`, valores anterior/nuevo y usuario que ejecutó la acción.
- **Implementación:** `activos/views.py` → `_registrar_reasignacion_en_historial()`, `_registrar_reubicacion_en_historial()`; invocados desde edición, reasignar, reubicar y acciones masivas.
- **Detalle:** El historial guarda nombres como `"Nombre Apellido"`, no username (`activos/views.py` → `_nombre()`).

### BR-ACT-11 — Historial no se crea automáticamente al crear activo

- **Regla verificada por tests:** Alta de activo no genera entradas de historial por defecto.
- **Implementación:** `activos/tests/test_activo_flow.py` → `test_crear_activo_exitoso`.

### BR-ACT-12 — Eliminación de activo elimina historial en cascada

- **Regla:** `HistorialMovimiento` tiene `on_delete=CASCADE` respecto a `Activo`.
- **Implementación:** `activos/models.py`; verificado en `test_eliminar_activo`.

### BR-ACT-13 — Acciones masivas idempotentes

- **Regla:** Reasignar/reubicar en lote omite activos que ya tienen el destino; solo cuenta cambios reales.
- **Implementación:** `activos/views.py` → `acciones_masivas()`.

### BR-ACT-14 — Filtro "Disponible" vs "Asignado"

- **Regla:** Filtro `asignacion=libre` → `usuario_asignado IS NULL`; `asignacion=asignado` → not null. Independiente del campo `estado` salvo otros filtros explícitos.
- **Implementación:** `activos/views.py` → `ActivoListView.get_queryset()`.

---

## 3. Mantenimientos

### BR-MNT-01 — Estados de mantenimiento

- **Regla:** `Mantenimiento.estado` ∈ `EP` (En proceso), `FI` (Finalizado). Default: `EP`.
- **Implementación:** `mantenimientos/models.py` → `EstadoMantenimiento`.

### BR-MNT-02 — Mantenimiento en proceso pone activo en mantenimiento

- **Regla:** Al guardar mantenimiento con estado `EP`, si el activo no está en `EM`, se actualiza a `EM`.
- **Implementación:** `mantenimientos/models.py` → `Mantenimiento.save()`.

### BR-MNT-03 — Finalizar último mantenimiento en proceso restaura activo

- **Regla:** Al pasar a `FI`, si no quedan otros mantenimientos `EP` del mismo activo y el activo está en `EM`, vuelve a `AC`.
- **Implementación:** `mantenimientos/models.py` → `Mantenimiento.save()`.

### BR-MNT-04 — Costo no negativo

- **Regla:** `costo >= 0`.
- **Implementación:** `mantenimientos/models.py` → `Mantenimiento.clean()`.

### BR-MNT-05 — Finalización solo por POST

- **Regla:** Cerrar mantenimiento requiere POST (protección CSRF).
- **Implementación:** `mantenimientos/views.py` → `@require_POST` en `finalizar_mantenimiento()`.

---

## 4. Reportes PDF

### BR-REP-01 — Reporte general respeta filtros del listado

- **Regla:** El PDF de inventario aplica los mismos filtros GET que la vista de activos (incluido `asignacion`).
- **Implementación:** `reportes/views.py` → `generar_reporte_activos()`.

### BR-REP-02 — Nota de entrega requiere al menos un activo

- **Regla:** POST sin `activos_seleccionados` → error y redirect al listado.
- **Implementación:** `reportes/views.py` → `generar_nota_entrega()`.

### BR-REP-03 — Modelo de historial de reportes (no aplicado en vistas)

- **Regla de modelo:** `ReporteGenerado` puede registrar tipo, usuario, filtros JSON y cantidad.
- **Implementación:** `reportes/models.py`.
- **Limitación:** `reportes/views.py` **no persiste** instancias de `ReporteGenerado` al generar PDFs.

---

## 5. Gestión de personas (`usuarios` app)

### BR-USR-01 — No eliminar identidad SSO

- **Regla:** `core_usuario` no se borra desde Activos; solo baja lógica (`is_active=False`).
- **Implementación:** `usuarios/views.py` → `cambiar_estado_usuario()` (comentario y lógica explícitos).

### BR-USR-02 — No desactivar cuenta propia

- **Regla:** Un usuario no puede desactivarse a sí mismo.
- **Implementación:** `usuarios/views.py` → `cambiar_estado_usuario()`.

### BR-USR-03 — No desactivar persona con activos asignados

- **Regla:** Desactivación bloqueada si `num_activos > 0`; mensaje pide reasignar primero.
- **Implementación:** `usuarios/views.py` → `cambiar_estado_usuario()`.

### BR-USR-04 — Superusuarios fuera de gestión del módulo

- **Regla:** Listados, perfiles y formularios excluyen `is_superuser=True`.
- **Implementación:** `usuarios/views.py` → `_usuarios_gestion_queryset()`, `UsuarioProfileView.get_queryset()`, etc.

### BR-USR-05 — Alta de persona en Activos crea usuario SSO sin contraseña usable

- **Regla:** Nuevo usuario recibe `set_unusable_password()` y username autogenerado si falta.
- **Implementación:** `usuarios/forms.py` → `UsuarioForm.save()`, `_nuevo_username()`.

### BR-USR-06 — Campos editables desde Activos

- **Regla:** Desde este módulo solo se gestionan: nombres, apellidos, email, teléfono, perfil, `is_active`.
- **Implementación:** `usuarios/forms.py` → `UsuarioForm.Meta.fields`.
- **Implicación:** Rol, disciplina y acceso a módulos (`UsuarioModulo`) **no** se asignan desde esta UI; deben gestionarse en admin Portal/central.

---

## 6. Presentación (reglas de interfaz con efecto funcional)

### BR-UI-01 — Personas siempre como "Nombre Apellido"

- **Regla:** Mensajes, historial y etiquetas usan `get_full_name()`; username solo como último recurso.
- **Implementación:** `activos/templatetags/activo_filters.py` → `nombre_completo()`; `activos/views.py` → `_nombre()`.

### BR-UI-02 — Redirect `next` validado

- **Regla:** Parámetro `next` solo acepta URLs del mismo host (anti open-redirect).
- **Implementación:** `activos/views.py`, `mantenimientos/views.py` → `_url_de_retorno()`.

### BR-UI-03 — Borrado vía modal, no página dedicada

- **Regla:** GET a URLs de delete redirige sin ejecutar borrado.
- **Implementación:** `activos/views.py` → `SinPaginaDeBorradoMixin`.

---

## 7. Catálogo compartido PALDACA (`core`)

### BR-CORE-01 — Módulos del ecosistema

- **Regla:** Catálogo en `core_modulo` con `codigo` slug único y flag `activo`.
- **Implementación:** `core/models.py` → `Modulo`; seed en `core/migrations/0006_seed_modulos.py` y `seed_core_modulos` command.

### BR-CORE-02 — Un acceso por par usuario-módulo

- **Regla:** Constraint único `(usuario, modulo)` en `core_usuario_modulo`.
- **Implementación:** `core/models.py` → `UsuarioModulo.Meta.constraints`.

### BR-CORE-03 — Disciplina y perfil opcionales

- **Regla:** FK nullable en `UsuarioPaldaca`.
- **Implementación:** `core/models.py`.

---

## Reglas NO implementadas (gaps detectados)

| Expectativa (documentación Suite) | Estado en Activos |
|-----------------------------------|-------------------|
| Permisos elevados para `rol=administrador` dentro del módulo | Método existe en modelo; **vistas no lo usan** |
| Registro de reportes generados | Modelo existe; **vistas no persisten** |
| Asignación de módulo al crear usuario desde Activos | **No implementado** en `UsuarioForm` |
