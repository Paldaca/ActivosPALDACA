# Integración — ActivosPALDACA en PALDACA Suite

Documento de referencia sobre cómo **ActivosPALDACA** interactúa con los demás repositorios, la base de datos compartida y servicios externos. Toda afirmación está respaldada por código salvo donde se indique incertidumbre.

---

## Panorama de integración

ActivosPALDACA es un **programa satélite Django** que:

1. **No implementa login propio** — delega autenticación al Portal.
2. **Lee/escribe en MySQL compartido** — tablas `core_*` (identidad) y `activos_*` (negocio).
3. **Consume assets y API del Portal** — navegación lateral embebida (`paldaca-nav`).
4. **No expone API REST pública** — solo vistas HTML y endpoints PDF/JSON internos.

```
┌─────────────────┐     cookie SSO      ┌─────────────────────┐
│ Portal-Paldaca  │◄───────────────────►│  ActivosPALDACA     │
│ (5173 + :8000)  │   paldaca_sessionid │  activos.cpaldaca.com│
└────────┬────────┘                     └──────────┬──────────┘
         │                                         │
         │         ┌───────────────────────────────┤
         │         │                               │
         ▼         ▼                               ▼
    ┌────────────────────────────────────────────────────┐
    │              MySQL (paldaca_db / producción)        │
    │  core_* · activos_* · django_session · auth_*      │
    └────────────────────────────────────────────────────┘
         ▲                    ▲                    ▲
         │                    │                    │
    ┌────┴────┐         ┌─────┴─────┐       ┌─────┴─────┐
    │ Calidad │         │ Codigos   │       │ Hoja Tiempo│
    │ (sat.)  │         │ (sat.)    │       │ (sat.)     │
    └─────────┘         └───────────┘       └────────────┘
```

---

## Repositorios de PALDACA Suite

| Repositorio | Relación con Activos | Evidencia en código |
|-------------|----------------------|---------------------|
| **Portal-Paldaca** | Login, logout SSO, nav JS/CSS, API base para menú | `PALDACA_SSO_*`, `core/context_processors.py`, `includes/paldaca_nav.html` |
| **Calidad** | Comparte `core_*`, mismo patrón satélite | `core/migrations/0006_seed_modulos.py` (`codigo=calidad`) |
| **Codigos** | Idem | Seed módulo `codigos` |
| **Hoja de Tiempo** | Idem | Seed módulo `hdt` |
| **ActivosPALDACA** | Este repo; módulo `activos` | `activos/constants.py` → `MODULO_CODIGO = "activos"` |

Activos **no importa código** de otros repositorios en tiempo de ejecución. La integración es por **convenciones compartidas** (app `core`, `key.env`, BD, cookies).

---

## Autenticación y sesión (SSO)

### Mecanismo

| Aspecto | Valor / comportamiento | Fuente |
|---------|------------------------|--------|
| Modelo de usuario | `core.UsuarioPaldaca` (`AUTH_USER_MODEL`) | `SSAPI/settings.py` |
| Cookie de sesión | `SESSION_COOKIE_NAME` = `paldaca_sessionid` (env) | `SSAPI/settings.py` |
| Dominio cookie prod | `.cpaldaca.com` si `SESSION_COOKIE_DOMAIN` definido | `SSAPI/settings.py` |
| Secret key | `DJANGO_SECRET_KEY` — **debe ser idéntica al Portal** | `SSAPI/settings.py` (comentario + `raise` si falta) |
| Login redirect | `PALDACA_SSO_LOGIN_URL` (default dev: `http://localhost:5173/login/`) | `SSAPI/settings.py` |
| Logout redirect | `PALDACA_SSO_LOGOUT_URL` (default: Portal API `/api/auth/sso/logout/`) | `SSAPI/settings.py`, `core/views.py` |
| Tabla sesiones | `django_session` (Django estándar) | Implícito por `django.contrib.sessions` |

### Flujo SSO

1. Usuario inicia sesión en Portal → se crea sesión en `django_session` y cookie `paldaca_sessionid`.
2. Navegador envía la misma cookie a `activos.cpaldaca.com` (dominio `.cpaldaca.com` en prod).
3. `AuthenticationMiddleware` carga `UsuarioPaldaca`.
4. `PaldacaSessionMiddleware` valida que permisos en BD coincidan con snapshot en sesión (`paldaca_auth_revision`).
5. Si hay divergencia y modo estricto activo → logout + limpieza cookies (`core/session_logout.py`) + redirect al login Portal.

### Control de acceso al módulo

- Código de módulo: **`activos`** (`activos/constants.py`).
- Verificación: `UsuarioPaldaca.tiene_acceso_modulo("activos")` (`core/models.py`).
- Asignación: tabla **`core_usuario_modulo`** (gestionada preferentemente desde admin del Portal).
- Superuser: acceso sin filas en `core_usuario_modulo`.

### Variables de entorno críticas para SSO

Archivo plantilla: `key.env.example` (debe copiarse como `key.env`, mismo archivo que Portal-Paldaca).

```env
DJANGO_SECRET_KEY=...          # IGUAL en Portal y Activos
SESSION_COOKIE_NAME=paldaca_sessionid
SESSION_COOKIE_DOMAIN=         # vacío local; .cpaldaca.com prod
PALDACA_SSO_LOGIN_URL=...
PALDACA_SSO_LOGOUT_URL=...
MYSQL_*=...                    # misma BD
```

Desarrollo local: archivo `dev.env` activa cookies sin dominio y URLs localhost (`SSAPI/settings.py`, `core/context_processors.py`).

---

## Base de datos compartida

### Motor y configuración

| Entorno | Config | Fuente |
|---------|--------|--------|
| Local (existe `dev.env`) | `DATABASEDES` → MySQL vía `MYSQL_*` | `SSAPI/db.py`, `SSAPI/settings.py` |
| Producción (sin `dev.env`) | `DATABASEPROD` → MySQL Namecheap | `SSAPI/db.py` |
| Tests | SQLite `:memory:` | `SSAPI/settings_test.py` |

**Importante:** Portal y satélites deben apuntar a la **misma instancia MySQL** para SSO y datos compartidos.

### Tablas compartidas (`core_*`) — escritas/leídas por Activos

| Tabla | Modelo | Uso en Activos |
|-------|--------|----------------|
| `core_usuario` | `UsuarioPaldaca` | Auth, asignación de activos, gestión personas |
| `core_disciplina` | `Disciplina` | FK opcional en usuario (lectura/admin) |
| `core_perfil` | `Perfil` | FK opcional; editable desde formulario usuarios |
| `core_modulo` | `Modulo` | Catálogo de programas Suite |
| `core_usuario_modulo` | `UsuarioModulo` | Permiso de entrada al módulo `activos` |

Tablas Django estándar también compartidas: `django_session`, `django_migrations`, `auth_*` (grupos/permisos Django sobre `UsuarioPaldaca`).

### Tablas propias del módulo (`activos_*`)

| Tabla | Modelo | App |
|-------|--------|-----|
| `activos_categoria` | `Categoria` | activos |
| `activos_subcategoria` | `SubCategoria` | activos |
| `activos_ubicacion` | `Ubicacion` | activos |
| `activos_activo` | `Activo` | activos |
| `activos_historial_movimiento` | `HistorialMovimiento` | activos |
| `activos_mantenimiento` | `Mantenimiento` | mantenimientos |
| `activos_reporte_generado` | `ReporteGenerado` | reportes |

Prefijo definido en `activos/constants.py` → `TABLA(nombre)` = `activos_{nombre}`.

Migración a prefijo: `activos/migrations/0004_activos_prefijo_tablas.py`.

### Tablas legacy / eliminadas

| Tabla histórica | Estado |
|-----------------|--------|
| `usuarios_usuarioasignado` | Migrada a `core_usuario` (`activos/migrations/0003_usuario_asignado_core.py`); modelo eliminado (`usuarios/migrations/0002_delete_usuarioasignado.py`) |

### Modelos que dependen de otros sistemas

| Modelo Activos | Dependencia externa | Tipo |
|----------------|---------------------|------|
| `Activo.usuario_asignado` | `core.UsuarioPaldaca` | FK — identidad gestionada centralmente |
| `HistorialMovimiento.usuario` | `core.UsuarioPaldaca` | FK nullable |
| `ReporteGenerado.usuario` | `core.UsuarioPaldaca` | FK nullable |
| Acceso a vistas | `core_modulo` + `core_usuario_modulo` | Lógica, no FK directa en modelos activos |

**No hay FKs** desde Activos hacia tablas de Calidad, Codigos o HDT.

---

## APIs: consume vs expone

### Consume (externo)

| Recurso | URL / origen | Propósito | Fuente |
|---------|--------------|-----------|--------|
| Login SSO | `PALDACA_SSO_LOGIN_URL` | Redirect usuarios no autenticados | `SSAPI/settings.py` |
| Logout SSO | `PALDACA_SSO_LOGOUT_URL` | Cierre sesión centralizado | `core/views.py` |
| Nav CSS | `{asset_base}/static/paldaca-nav.css` | Sidebar Suite | `core/context_processors.py` |
| Nav JS | `{asset_base}/static/paldaca-nav.js` | Sidebar Suite | `core/context_processors.py` |
| Nav API | `PALDACA_API_BASE` (default `https://api.cpaldaca.com/api`) | Menú / módulos habilitados | `paldaca_nav.html` → `window.__PALDACA_NAV__` |
| Logos Portal | `{portal_url}/images/logo*.png` | Branding nav | `core/context_processors.py` |

Default producción del bundle nav: **`https://cpaldaca.com`**. Override local: `PALDACA_NAV_ASSET_BASE=http://localhost:8000`.

**Integración prevista / parcial:** `core/static/core/js/base.js` referencia `fetch("/ia/chat/api/")` — **no hay ruta definida** en `SSAPI/urls.py` de este repo. Posible resto de integración IA del Portal no conectado aquí.

### Expone (este repositorio)

| Endpoint | Método | Formato | Auth | Descripción |
|----------|--------|---------|------|-------------|
| `/` | GET | HTML | Módulo activos | Home/dashboard |
| `/activos/**` | GET/POST | HTML | Módulo activos | CRUD inventario |
| `/activos/catalogo/<tipo>/rapido/` | POST | JSON | Módulo activos | Alta express catálogo |
| `/mantenimientos/**` | GET/POST | HTML | Módulo activos | Mantenimientos |
| `/reportes/activos/` | GET | PDF | Módulo activos | Reporte inventario |
| `/reportes/nota-entrega/` | POST | PDF | Módulo activos | Nota de entrega |
| `/usuarios/**` | GET/POST | HTML | Módulo activos | Gestión personas |
| `/admin/**` | * | HTML | Staff Django | Admin |
| `/logout/` | GET | Redirect | — | Alias a logout Portal |

**No hay** Django REST Framework ni rutas `/api/` propias del módulo Activos.

El middleware devuelve JSON 401 solo para paths `/api/` o requests con `Accept: application/json` al invalidar sesión (`core/middleware.py`) — preparado para clientes API futuros, no implementados en este repo.

---

## Navegación embebida (Portal Shell)

### Integración activa

`core/templates/includes/paldaca_nav.html` monta:

```javascript
window.__PALDACA_NAV__ = {
  apiBaseUrl: "...",
  portalUrl: "...",
  currentApp: "activos",
  logoFullUrl: "...",
  logoCompactUrl: "..."
};
```

`paldaca_nav_current_app` = **`"activos"`** (`core/context_processors.py`).

El sidebar permite saltar entre módulos Suite según módulos habilitados del usuario (datos desde API Portal).

### Integración prevista

Documentación UX (`docs/ux-ui-sistema-activos.md`) describe alineación visual con Portal Shell. Activos ya consume el bundle nav; **no** está embebido dentro de un iframe del Portal — es despliegue independiente con nav inyectado.

---

## Sincronización de la app `core`

La guía interna `docs/guia-integracion-programas-satelite.md` (copiada/adaptada del ecosistema) establece:

> Cada satélite debe incluir la app Django `core` con **las mismas migraciones** que Portal-Paldaca.

### Implicaciones para compatibilidad

| Elemento | Riesgo si diverge |
|----------|-------------------|
| `core/migrations/*` | `InconsistentMigrationHistory`, esquema distinto |
| `core/models.py` | `get_auth_revision()` desincronizado, permisos rotos |
| `DJANGO_SECRET_KEY` | Sesiones no compartidas |
| `SESSION_COOKIE_*` | Cookie no enviada entre subdominios |
| Seed de módulos | Códigos distintos → 403 en satélites |

Comando local: `python manage.py seed_core_modulos` (`core/management/commands/seed_core_modulos.py`).

**Inconsistencia detectada:** la migración `0006_seed_modulos.py` inserta 9 módulos (incluye `ventas`, `inventario`, `rrhh`, `proyectos`); el comando `seed_core_modulos` solo 5. Ambos garantizan `activos`, pero el catálogo puede diferir si solo se ejecuta el comando.

---

## Dependencias externas (runtime)

| Dependencia | Uso |
|-------------|-----|
| MySQL | BD principal |
| Bootstrap 5.3 CDN | UI |
| Google Fonts (Roboto) | Tipografía |
| `cpaldaca.com` / `api.cpaldaca.com` | Nav y API menú (prod) |
| ReportLab | PDF |
| Namecheap hosting | Deploy prod (workflow CI) |

---

## Operaciones cross-repo que afectan a Activos

| Operación en Portal / admin central | Efecto en Activos |
|-------------------------------------|-------------------|
| Quitar acceso módulo `activos` en `core_usuario_modulo` | 403 o logout (middleware) |
| Cambiar `rol`, `disciplina`, `perfil` | Posible invalidación sesión |
| Desactivar `is_active` en `core_usuario` | Logout / sin acceso |
| Crear usuario solo en Portal | Visible en Activos si tiene acceso módulo |
| Crear usuario desde Activos (`UsuarioForm`) | Crea fila en **`core_usuario` global** sin asignar `UsuarioModulo` automáticamente — **puede no tener acceso a Activos ni otros módulos** hasta configuración en admin |
| Migraciones `core` en Portal sin sincronizar en Activos | Riesgo de esquema inconsistente |

---

## Elementos que pueden romper compatibilidad

### Críticos (SSO / Suite)

1. **`DJANGO_SECRET_KEY` diferente** entre Portal y Activos.
2. **`SESSION_COOKIE_DOMAIN` incorrecto** en local (dominio prod) o viceversa.
3. **Migraciones `core` desincronizadas** entre repositorios.
4. **Dos definiciones de usuario** — mitigado; legacy `UsuarioAsignado` eliminado.
5. **Código de módulo renombrado** sin actualizar `activos/constants.py` y filas `core_modulo`.

### Medios (datos / negocio)

6. **Borrado físico de `core_usuario`** desde otro sistema — rompe FKs `activos_activo.usuario_asignado_id` (SET NULL).
7. **Cambio de prefijo de tablas** sin migración coordinada.
8. **Alteración de `get_auth_revision()`** en Portal sin desplegar mismo `core` en Activos — logout masivo inesperado.

### Menores / deuda técnica

9. **`README.md` desactualizado** — riesgo operativo para nuevos desarrolladores (MySQL vs PostgreSQL).
10. **`ReporteGenerado` sin uso** — esquema extra sin valor hasta implementar persistencia.
11. **Chat legacy en `base.js`** — llamadas a endpoint inexistente (ruido en consola).
12. **Alta de usuarios en Activos sin `UsuarioModulo`** — usuarios "huérfanos" de acceso SSO al módulo.

---

## Mapa de módulos Suite (referencia)

Según `docs/guia-integracion-programas-satelite.md` y seeds:

| Programa | `MODULO_CODIGO` | Prefijo tablas negocio |
|----------|-----------------|------------------------|
| Portal | `portal` | `portal_` |
| Hoja de Tiempo | `hdt` | `hdt_` |
| Calidad | `calidad` | (según repo) |
| Codigos | `codigos` | `codigos_` |
| **Activos** | **`activos`** | **`activos_`** |

Puerto dev sugerido Activos: **8004** (guía interna; no enforced en código).

---

## Checklist de integración para desarrolladores

1. Copiar/sincronizar `key.env` desde Portal-Paldaca.
2. Verificar `MYSQL_*` apunta a la misma BD.
3. Ejecutar `migrate` (aplica `core` + `activos_*`).
4. Asignar módulo `activos` al usuario en admin (`core_usuario_modulo`).
5. Login en Portal → abrir Activos sin re-autenticación.
6. Confirmar nav carga desde Portal (`paldaca-nav.js` sin errores de red).

---

## Documentos relacionados en este repo

| Archivo | Contenido |
|---------|-----------|
| `docs/guia-integracion-programas-satelite.md` | Guía genérica satélites (SSO, copia de `core`) |
| `docs/ux-ui-sistema-activos.md` | Integración visual nav / UX |
| `key.env.example` | Variables SSO/BD |
| `docs/ARCHITECTURE.md` | Arquitectura interna |
| `docs/BUSINESS_RULES.md` | Reglas de negocio |
