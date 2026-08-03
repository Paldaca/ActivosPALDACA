# Arquitectura — ActivosPALDACA (SSAPI)

Documentación derivada del código en `ActivosPALDACA`. Última revisión basada en el estado del repositorio al analizarlo para PALDACA Suite.

---

## Propósito del repositorio

**ActivosPALDACA** (proyecto Django **SSAPI** — *Sistema de Gestión de Activos*) es el módulo satélite de **PALDACA Suite** responsable de:

- Inventario de activos físicos y tecnológicos (CRUD, filtros, KPIs).
- Catálogos de categorías, subcategorías y ubicaciones.
- Asignación y reasignación de activos a personas (`core.UsuarioPaldaca`).
- Historial de movimientos (reubicación, reasignación, etc.).
- Registro de mantenimientos y su impacto en el estado del activo.
- Generación de reportes PDF (inventario filtrado y nota de entrega).
- Gestión limitada de personas asignables desde la interfaz del módulo.

No es el portal de login ni la API central de autenticación. Depende de **Portal-Paldaca** para SSO y comparte la base de datos MySQL con el resto de la Suite.

**Despliegue producción:** `activos.cpaldaca.com` (ver `ALLOWED_HOSTS` en `SSAPI/settings.py` y workflow `.github/workflows/main.yml`).

---

## Arquitectura general

```
                    ┌─────────────────────────────────────┐
                    │         Portal-Paldaca                │
                    │  Login React (:5173) + API (:8000)    │
                    │  Emite cookie paldaca_sessionid       │
                    └──────────────┬──────────────────────┘
                                   │ SSO (cookie + django_session)
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                    ActivosPALDACA (SSAPI)                         │
│  Django 5.2.7 · Server-rendered (CBV + templates Bootstrap 5)    │
│  Puerto oficial Suite: 8001 (Portal .env.development)          │
├──────────────────────────────────────────────────────────────────┤
│  Middleware: PaldacaSessionMiddleware · ErrorHandling · Security │
│  AUTH_USER_MODEL = core.UsuarioPaldaca                           │
├──────────┬──────────┬──────────────┬──────────┬──────────────────┤
│  core    │  activos │mantenimientos│ reportes │ usuarios (UI)    │
│  (SSO,   │ (dominio │ (servicio    │ (PDF     │ (gestión sobre   │
│   home)  │  negocio)│  técnico)    │ ReportLab)│  core_usuario)  │
└──────────┴──────────┴──────────────┴──────────┴──────────────────┘
                                   │
                                   ▼
                         MySQL compartido (paldaca_db)
                    core_* · activos_* · django_session · auth_*
```

### Stack tecnológico (verificado en código)

| Capa | Tecnología |
|------|------------|
| Backend | Django 5.2.7 |
| Base de datos | MySQL (`mysqlclient`) vía `SSAPI/db.py` |
| PDF | ReportLab 4.0.4 |
| Frontend | Templates Django + Bootstrap 5.3 + JS propio (`activos-ui.js`) |
| Tests | pytest + pytest-django (`SSAPI/settings_test.py`, SQLite en memoria) |
| Config | `python-dotenv`, archivos `key.env` / `dev.env` |

**Nota:** `requirements.txt` incluye `psycopg2-binary`, pero la configuración activa usa **MySQL**, no PostgreSQL. El `README.md` raíz describe SQLite/PostgreSQL y está **desactualizado** respecto al código.

---

## Estructura del proyecto

```
ActivosPALDACA/
├── SSAPI/                 # Proyecto Django (settings, urls, db, wsgi)
├── core/                  # Identidad PALDACA, SSO, home, errores, nav embed
├── activos/               # Dominio principal de inventario
├── mantenimientos/        # Registro de mantenimientos
├── reportes/              # Generación PDF
├── usuarios/              # UI de personas; models.py vacío (solo migraciones legacy)
├── manage.py
├── key.env.example        # Plantilla SSO/BD (debe coincidir con Portal-Paldaca)
├── requirements.txt
└── docs/                  # Documentación técnica Suite
```

### Punto de entrada HTTP

`SSAPI/urls.py` monta:

| Prefijo | App | Rol |
|---------|-----|-----|
| `/` | `core` | Home/dashboard |
| `/activos/` | `activos` | Inventario y catálogos |
| `/mantenimientos/` | `mantenimientos` | Mantenimientos |
| `/reportes/` | `reportes` | Endpoints PDF |
| `/usuarios/` | `usuarios` | Búsqueda y perfil de personas |
| `/admin/` | Django admin | Gestión `core` y modelos registrados |

---

## Aplicaciones y responsabilidades

### `core`

**Responsabilidad:** Capa compartida de identidad PALDACA e infraestructura transversal.

| Componente | Ubicación | Función |
|------------|-----------|---------|
| Modelos compartidos | `core/models.py` | `Disciplina`, `Perfil`, `Modulo`, `UsuarioModulo`, `UsuarioPaldaca` |
| SSO / sesión | `core/middleware.py` → `PaldacaSessionMiddleware` | Invalida sesión si cambian permisos (`get_auth_revision`) |
| Cierre sesión | `core/session_logout.py` | Limpia cookies SSO en dominio compartido |
| Home | `core/views.py` → `HomeView` | Dashboard con KPIs de activos y mantenimientos |
| Errores | `core/views.py`, `core/middleware.py` | Handlers 400/403/404/500 + middleware de captura |
| Nav Suite | `core/context_processors.py`, `includes/paldaca_nav.html` | Inyecta URLs del bundle `paldaca-nav` del Portal |
| Admin | `core/admin.py` | CRUD de catálogos y usuarios PALDACA |
| Seed módulos | `core/management/commands/seed_core_modulos.py` | Catálogo base en `core_modulo` |

Tablas: `core_disciplina`, `core_perfil`, `core_modulo`, `core_usuario_modulo`, `core_usuario`.

### `activos`

**Responsabilidad:** Dominio de negocio del inventario.

| Modelo | Tabla | Descripción |
|--------|-------|-------------|
| `Categoria` | `activos_categoria` | Categoría principal |
| `SubCategoria` | `activos_subcategoria` | Subcategoría con `prefijo` único (código inventario) |
| `Ubicacion` | `activos_ubicacion` | Ubicación física |
| `Activo` | `activos_activo` | Activo con FK a subcategoría, ubicación y `UsuarioPaldaca` |
| `HistorialMovimiento` | `activos_historial_movimiento` | Auditoría de cambios |

Constantes: `activos/constants.py` define `MODULO_CODIGO = "activos"` y helper `TABLA(n)` → prefijo `activos_`.

Control de acceso: `activos/decorators.py` — `ModuloActivoRequiredMixin` y `@requiere_modulo_paldaca` verifican `user.tiene_acceso_modulo("activos")`.

Presentación: `activos/templatetags/activo_filters.py` centraliza estado derivado UI y nombres de personas.

### `mantenimientos`

**Responsabilidad:** Registro de intervenciones técnicas sobre activos.

| Modelo | Tabla |
|--------|-------|
| `Mantenimiento` | `activos_mantenimiento` |

Al guardar, sincroniza el estado del activo (`EM` ↔ `AC`) según mantenimientos en proceso (`mantenimientos/models.py` → `save()`).

### `reportes`

**Responsabilidad:** Exportación PDF vía ReportLab.

| Modelo | Tabla | Uso en código |
|--------|-------|---------------|
| `ReporteGenerado` | `activos_reporte_generado` | **Modelo definido; las vistas actuales no persisten registros** |

Vistas en `reportes/views.py`: reporte general (GET con filtros) y nota de entrega (POST con activos seleccionados).

### `usuarios`

**Responsabilidad:** Interfaz de gestión de personas sobre `core.UsuarioPaldaca`.

- `usuarios/models.py` está vacío (comentario: identidad en `core`).
- La app se conserva por historial de migraciones (`UsuarioAsignado` legacy → migrado a `core_usuario` en `activos/migrations/0003_usuario_asignado_core.py`).
- Vistas: búsqueda, perfil, alta/edición, activación/desactivación lógica (`usuarios/views.py`).

---

## Flujo principal de ejecución

### 1. Request entrante

```
HTTP Request
  → SecurityMiddleware
  → SessionMiddleware (lee cookie SESSION_COOKIE_NAME = paldaca_sessionid)
  → AuthenticationMiddleware (resuelve core.UsuarioPaldaca)
  → PaldacaSessionMiddleware
       · Compara paldaca_auth_revision en sesión vs get_auth_revision() en BD
       · Si inconsistente (modo estricto): cierra sesión → redirect login Portal
  → Vista protegida (ModuloActivoRequiredMixin / @requiere_modulo_paldaca)
       · Sin auth → redirect PALDACA_SSO_LOGIN_URL
       · Sin acceso módulo "activos" → HTTP 403
  → Template (base.html incluye paldaca_nav si autenticado)
```

### 2. Flujo de negocio típico (activo)

1. Usuario accede a `/activos/` (`ActivoListView`).
2. Filtros GET (categoría, estado, asignación, búsqueda).
3. Creación/edición vía `ActivoForm`; código inventario auto-generado si vacío (`PAL-{PREFIJO}-{NNN}`).
4. Reasignación/reubicación vía drawer o vistas dedicadas; se escribe `HistorialMovimiento`.
5. Mantenimiento en `/mantenimientos/nuevo/` puede forzar estado `EM` del activo.
6. PDF desde `/reportes/activos/` o nota de entrega POST.

### 3. Configuración de entorno

| Archivo | Efecto |
|---------|--------|
| `key.env` | `DJANGO_SECRET_KEY`, cookies SSO, MySQL (debe ser **idéntico** al Portal) |
| `dev.env` (opcional) | Activa `DEBUG=true`, usa `DATABASEDES`, URLs localhost para nav |

Lógica en `SSAPI/settings.py`: si existe `dev.env` → BD desarrollo + cookies sin dominio; si no → producción.

---

## Decisiones arquitectónicas detectadas

1. **Monolito Django server-rendered** — Sin SPA propia; React solo en Portal para login y nav embebido.
2. **Identidad centralizada** — Un solo `AUTH_USER_MODEL` (`core.UsuarioPaldaca`) compartido con toda la Suite; prohibición explícita de borrar filas desde Activos (baja lógica).
3. **Prefijo de tablas por módulo** — Tablas de negocio bajo `activos_*` para coexistir en BD unificada.
4. **Estado operativo derivado** — El modelo guarda `AC/IN/EM`; "Disponible" vs "Asignado" se calcula en capa de presentación (`activo_filters.py`), no en BD.
5. **Acceso binario por módulo** — Decoradores solo verifican `tiene_acceso_modulo("activos")`; **no** distinguen rol administrador vs usuario dentro del módulo en las vistas de negocio (aunque `es_administrador_en_modulo` existe en el modelo).
6. **Consistencia estricta de sesión** — `PALDACA_STRICT_SESSION_CONSISTENCY=true` por defecto: cambios de rol/módulos en admin invalidan sesiones activas.
7. **Nav como dependencia externa** — Sidebar cargado desde `cpaldaca.com/static/paldaca-nav.{css,js}` (override local vía `PALDACA_NAV_ASSET_BASE`).
8. **Migración legacy de usuarios** — `UsuarioAsignado` local fue absorbido por `core_usuario` mediante migración de datos.

---

## Dependencias internas entre apps

```
core ─────────────────────────────────────────► (base: auth, SSO, catálogos)
  ▲
  │ FK AUTH_USER_MODEL
  │
activos ◄── mantenimientos (FK Activo)
  ▲
  │ queryset / filtros
  │
reportes ──► activos (genera PDF sobre Activo)
usuarios ──► core.UsuarioPaldaca + activos (activos_asignados)
core.views.HomeView ──► activos, mantenimientos (KPIs dashboard)
```

**Orden de carga en `INSTALLED_APPS`:** `activos` antes que `core` en settings (no afecta FKs; `core` provee user model).

---

## Despliegue

- **CI/CD:** `.github/workflows/main.yml` — push a `main` → SSH a Namecheap, `migrate`, `collectstatic`, rsync a `activos.cpaldaca.com`.
- **cPanel:** `.cpanel.yml` define rsync alternativo a `ActivosApp`.
- **WSGI:** No hay `passenger_wsgi.py` en el repositorio; el workflow de deploy lo referencia en el servidor (`touch passenger_wsgi.py`).

---

## Inconsistencias documentadas

| Elemento | Observación |
|----------|-------------|
| `README.md` | Describe PostgreSQL/SQLite; el código usa MySQL |
| `requirements.txt` | Incluye `psycopg2-binary` sin uso aparente |
| `ReporteGenerado` | Modelo migrado; vistas no registran historial de reportes |
| `es_administrador_en_modulo` | Implementado en `core.models`; no usado en vistas de Activos |
| `core/static/core/js/base.js` | Referencia legacy a `/ia/chat/api/` (endpoint no definido en urls) |
| `seed_core_modulos` vs migración `0006_seed_modulos` | El comando seedea 5 módulos; la migración incluye además ventas, inventario, rrhh, proyectos |

---

## Referencias de código

- Configuración: `SSAPI/settings.py`, `SSAPI/db.py`
- Rutas raíz: `SSAPI/urls.py`
- Identidad: `core/models.py`
- Acceso módulo: `activos/decorators.py`, `activos/constants.py`
- Dominio activos: `activos/models.py`, `activos/views.py`
