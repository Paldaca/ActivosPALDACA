# Sistema UX/UI — Módulo de Gestión de Activos

Documentación del rediseño del módulo `activos` (+ `usuarios`, `mantenimientos`,
`home`). Cubre el sistema de diseño, las reglas de negocio traducidas a
interfaz, los patrones de interacción y el estado de la integración con el
sidebar del Portal.

Referencia rápida de archivos:

| Pieza | Archivo |
|---|---|
| Tokens + componentes CSS | [`activos/static/css/activos-ui.css`](../activos/static/css/activos-ui.css) |
| Comportamiento (combos, drawers, modales, stepper…) | [`activos/static/js/activos-ui.js`](../activos/static/js/activos-ui.js) |
| Filtros/tags de plantilla (estado derivado, nombre, avatar) | [`activos/templatetags/activo_filters.py`](../activos/templatetags/activo_filters.py) |
| Partials reutilizables | [`activos/templates/activos/includes/`](../activos/templates/activos/includes/) |

---

## 1. Principios

1. **El identificador es el código de inventario.** Nunca el `pk` de Django, nunca el nombre del equipo a secas. Se muestra siempre como `.ax-code` (mono, destacado, enlazable).
2. **Las personas se muestran como "Nombre Apellido", nunca por username.** Regla centralizada en un único filtro (`nombre_completo`), no repetida a mano en cada plantilla.
3. **El estado que ve el usuario se deriva, no se duplica.** El modelo `Activo.estado` solo guarda `AC/IN/EM`; "Disponible" vs. "Asignado" se calcula a partir de `estado + usuario_asignado`. Un único punto de verdad (`estado_key` en `activo_filters.py`) decide el color y la etiqueta en toda la app.
4. **Confirmar no debe costar una navegación.** Reasignar, reubicar y eliminar ocurren en drawers/modales sobre la página actual. Las páginas completas (`reasignar.html`, `reubicar.html`) se conservan como respaldo accesible y sin JavaScript, nunca como el camino principal.
5. **Todo botón real es un enlace/formulario real.** El JS mejora la experiencia (drawer, combo, altas rápidas) pero nunca es la única vía: si falla o está desactivado, la URL de Django detrás sigue funcionando.
6. **Sin caps silenciosos.** Si algo se recorta (5 de N mantenimientos, top-5 de categorías) se dice explícitamente en la interfaz.

---

## 2. Sistema de diseño (`activos-ui.css`)

Prefijo de namespace: **`.ax-*`**. Depende de Bootstrap 5.3 + Bootstrap Icons +
las variables de marca ya definidas en `core.css` (`--e-global-color-*`).

### 2.1 Tokens

```css
--ax-navy / --ax-indigo / --ax-violet / --ax-red   /* espejo de core.css */
--ax-surface / --ax-surface-2 / --ax-surface-3     /* superficies */
--ax-ink / --ax-ink-2 / --ax-ink-3                 /* tinta, 3 niveles */
--ax-lila / --ax-menta / --ax-durazno / --ax-rosa
--ax-cielo / --ax-lavanda / --ax-neutro            /* 7 familias pastel: fondo+borde+tinta */
--ax-sh-1 … --ax-sh-4                              /* elevación */
--ax-r-sm / --ax-r / --ax-r-lg / --ax-r-xl         /* radios */
--ax-ease / --ax-ease-out / --ax-spring            /* curvas de animación */
```

Cada familia pastel (`--ax-lila`, `--ax-menta`…) trae tres variables: fondo,
borde y tinta. Nunca se usa el fondo pastel con texto negro — la tinta de la
misma familia garantiza contraste AA.

### 2.2 Botones — `.btn-pastel`

Superficie tenue + tinta saturada, en vez de botones sólidos de alto peso
visual. Modificadores de color: `--lila --menta --durazno --rosa --cielo
--lavanda --neutro --glass` (translúcido, para usar sobre el hero). Tamaños:
`--sm --lg`. Variante `--icon` (circular, para acciones de fila) y `--cta`
(acento de marca a la izquierda, para la acción principal de la página).

```html
<a class="btn-pastel btn-pastel--cta"><i class="bi bi-plus-lg"></i> Nuevo activo</a>
<button class="btn-pastel btn-pastel--rosa btn-pastel--icon"><i class="bi bi-trash"></i></button>
```

### 2.3 Indicadores (KPI) — `.ax-kpi`

Acabado "premium": velo de color radial + degradado claro, filete superior de
acento (se engrosa al pasar el mouse), destello diagonal en hover, cifra
protagonista con `tabular-nums`, y una barra de participación (`.ax-kpi-meter`)
que muestra qué porcentaje del total representa esa cifra.

```html
<a href="…" class="ax-kpi ax-kpi--disponible">
  <span class="ax-kpi-head">
    <span class="ax-kpi-label">Disponibles</span>
    <span class="ax-kpi-icon"><i class="bi bi-box-seam"></i></span>
  </span>
  <span class="ax-kpi-value"><span class="ax-count" data-value="{{ n }}">0</span></span>
  <span class="ax-kpi-meter"><span style="width:{{ n|porcentaje_css:total }}%"></span></span>
  <span class="ax-kpi-foot"><span>Listos para entregar</span><span class="ax-kpi-share">{{ n|porcentaje:total }}%</span></span>
</a>
```

⚠️ **Regla de los dos filtros de porcentaje** (ver §5.2): el ancho inline usa
`porcentaje_css`, el texto visible usa `porcentaje`. Confundirlos deja la
barra en 0% con la localización de Django activada (`6,8%` no es un `width`
CSS válido).

### 2.4 Badges de estado — `.ax-estado`

Ver §3. Nunca se construyen a mano; siempre vía `{% badge_estado activo %}`.

### 2.5 Tabla de datos — `.ax-table`

Cabecera sticky, fila con `data-label` para el colapso a tarjetas en móvil,
celda de persona con avatar de iniciales (`.ax-person` / `.ax-avatar`), celda
de equipo con icono por tipo (`.ax-equipo` + `icono_activo`), acciones que se
revelan al pasar el mouse (`.ax-row-actions` — **nunca con `transform`**, ver
§6.1).

### 2.6 Búsqueda y chips — `.ax-searchbar`, `.ax-chip`

Atajo de teclado `/` para enfocar la búsqueda (ver §4.4). Los chips de estado
son enlaces reales (`?estado=EM`), no botones de JS: recargan la página con el
filtro aplicado, así que funcionan con JS desactivado y son compartibles por
URL.

### 2.7 Drawers, modales, stepper

Ver §4 (patrones de interacción).

### 2.8 Animación

Utilidades `.ax-anim-rise/fade/pop/slide` + `data-ax-stagger="N"` (JS asigna
`--i` a cada hijo, tope de 10 para que listas largas no tarden casi un segundo
en terminar de aparecer). Todo respeta `prefers-reduced-motion: reduce`.

---

## 3. Badges de estado — contrato único

| Estado visible | Condición derivada | Familia de color | Icono |
|---|---|---|---|
| **Disponible** | `estado='AC'` y sin `usuario_asignado` | menta | `bi-box-seam` |
| **Asignado** | `estado='AC'` y con `usuario_asignado` | cielo | `bi-person-check` |
| **En Mantenimiento** | `estado='EM'` | durazno | `bi-tools` |
| **Dado de Baja** | `estado='IN'` | neutro (tachado) | `bi-archive` |

Implementado en `ESTADOS_UI` + `estado_key()` dentro de
`activos/templatetags/activo_filters.py`. Cualquier pantalla nueva que
necesite pintar un estado debe usar `{% badge_estado activo %}` — nunca un
`{% if activo.estado == 'AC' %}` inline, porque eso es exactamente lo que
hacía divergir color y etiqueta entre pantallas antes del rediseño.

---

## 4. Patrones de interacción

### 4.1 Reasignación / reubicación rápida — Drawer (Offcanvas)

**Decisión de diseño:** se descartó el modal centrado a favor de un drawer
lateral (`.ax-drawer`, Bootstrap Offcanvas) porque:

- dedica más ancho a la comparación "De → Para" sin sentirse apretado;
- se abre desde la fila o desde la ficha sin perder el contexto de la lista
  detrás;
- es el mismo componente para la acción individual y para el modo "en lote".

Contrato de datos (fila de la tabla → drawer): el disparador (`<a
data-ax-reasignar>`) lleva todos los `data-*` necesarios (código, equipo,
serial, icono, usuario/ubicación actual). `activos-ui.js` los lee al abrir el
drawer y pinta la ficha compacta del activo + el bloque "De → Para". El botón
de guardar permanece deshabilitado hasta que el valor elegido sea distinto al
actual — evita registrar movimientos de historial en falso.

Partials: `_drawer_reasignar.html`, `_drawer_reubicar.html`, `_drawer_lote.html`
(mismo drawer, parametrizado con `modo='reasignar'|'reubicar'` para lote).

**Respaldo sin JS:** `activo-reasignar` / `activo-reubicar` siguen siendo
vistas Django completas (`reasignar.html`, `reubicar.html`), con el mismo
diseño "De → Para" pero en página completa. El drawer solo antepone un atajo.

### 4.2 Eliminación — Modal único con confirmación por escritura

Un solo `_modal_eliminar.html` sirve a las 4 entidades borrables (activo,
categoría, subcategoría, ubicación). El disparador pasa `data-titulo`,
`data-ficha`, `data-impacto`, `data-aviso` y, si aplica, `data-confirmar`
(exige escribir el código de inventario para habilitar el botón — solo para
el borrado de un activo, la acción más costosa de deshacer).

Si el borrado está bloqueado por dependencias (categoría con subcategorías,
ubicación con activos…), el disparador manda `data-bloqueado` con el motivo:
el modal se vuelve informativo y oculta el botón de confirmar.

**Por qué no hay páginas de confirmación:** confirmar una eliminación no
debería costar una navegación completa + botón "atrás". Las 4 vistas de
borrado son ahora endpoints POST puros (`SinPaginaDeBorradoMixin`): un `GET`
directo redirige a donde tiene sentido seguir trabajando, en vez de servir una
página huérfana.

### 4.3 Alta express de catálogo — Modal + fetch JSON

Problema que resuelve: antes, si al dar de alta un activo la subcategoría o
ubicación no existía, había que abrir una pestaña nueva, crear el catálogo,
volver y recargar el formulario. Ahora el botón **+** junto al select abre
`_modal_crear_rapido.html`, que llama a `POST /activos/catalogo/<tipo>/rapido/`
(vista `crear_rapido`, respuesta JSON) y añade la opción nueva al `<select>`
sin recargar la página. Para subcategoría, la categoría puede elegirse **o**
escribirse en el mismo paso (crea ambas si hace falta).

### 4.4 Buscador con atajo de teclado

`data-ax-buscar` + tecla `/` para enfocar sin usar el mouse (patrón de
GitHub/Linear). Autoenvío con debounce cuando el término tiene 2+ caracteres.
Los `<select>` de filtro con `data-ax-autofiltro` envían el formulario al
cambiar — un cambio de filtro es un resultado, no dos pasos.

### 4.5 Combobox de personas/ubicaciones sobre `<select>` nativo

`.ax-combo` mejora un `<select class="ax-combo-native">` con búsqueda
incremental, resaltado de coincidencia y avatares. El `<select>` real
permanece en el DOM (oculto visualmente, no con `display:none`, para que la
validación nativa del navegador siga funcionando) y es lo que efectivamente
se envía — el combo es una capa de UX, no reemplaza el control.

### 4.6 Formulario de alta en 2 pasos — Stepper

`activo/form.html` divide "Equipo" (subcategoría, marca, modelo, serial) de
"Asignación" (ubicación, responsable, estado, observaciones). Sin JavaScript,
`<noscript>` fuerza que ambos paneles se muestren completos (nunca un paso
oculto sin salida). Con JS, `Enter` en un input intermedio avanza de paso en
vez de enviar el formulario a medio llenar.

### 4.7 Acciones en lote

Checkbox por fila (oculto hasta pulsar "Seleccionar") + barra flotante
(`.ax-bulkbar`) con contador. Reasignar/reubicar en lote reutiliza el mismo
`_drawer_lote.html` y pega contra `POST /activos/acciones-masivas/`, que aplica
el cambio activo por activo dentro de una transacción, **omitiendo** (sin
generar movimiento de historial) los que ya tuvieran ese responsable o esa
ubicación.

---

## 5. Reglas de negocio traducidas a código de plantilla

### 5.1 Nombre de persona

```python
# activo_filters.py
nombre_completo(user)  # "Nombre Apellido"; cae a username solo si faltan ambos
iniciales(valor)        # "RG" para el avatar
tono_avatar(valor)      # índice 0-7 determinista (mismo algoritmo en JS y Python)
```

`tono_avatar` está duplicado a propósito en `activo_filters.py` (servidor) y
`activos-ui.js` (cliente): el avatar pintado por el combobox en el drawer debe
coincidir con el pintado por Django en la tabla, sin round-trip.

### 5.2 Porcentajes — dos filtros, un solo motivo

```python
{{ n|porcentaje:total }}       # "6,8" — para TEXTO visible (localizado, con coma)
{{ n|porcentaje_css:total }}   # "6.8" — para width:…% dentro de style="" (nunca localizado)
```

Usar `porcentaje` dentro de un `style="width:…%"` es un bug silencioso: con
`LANGUAGE_CODE=es`, Django imprime `6,8%`, que el navegador descarta como
`width` inválido y la barra queda invisible sin ningún error en consola.

### 5.3 Icono por tipo de activo

`icono_activo` mapea palabras clave del nombre de la subcategoría/categoría
(laptop, monitor, impresora, servidor, router, ambulancia…) a un icono
Bootstrap. Es heurístico y editable: añadir un tipo nuevo es agregar una
tupla a `_ICONOS_TIPO` en `activo_filters.py`.

---

## 6. Bugs corregidos durante el rediseño (para no repetirlos)

### 6.1 `transform` permanente rompe `position: fixed` de los hijos

`.ax-row-actions` (acciones que aparecen al pasar el mouse sobre una fila)
usaba `transform: translateX(6px)` en reposo. Un `transform` distinto de
`none` convierte al elemento en **bloque contenedor** de sus descendientes
`position: fixed` — el menú desplegable de esa fila terminaba anclado a un
punto absoluto de la página (a veces fuera del viewport) en vez de junto a su
botón. Se resolvió animando `padding-left` en su lugar; el diseño necesita
opacidad + desplazamiento, no `transform`, cuando puede contener un dropdown.

**Regla general:** ningún ancestro de un `.dropdown-menu`/offcanvas/modal
puede tener `transform`, `filter`, `perspective`, `will-change` ni `contain`
permanentes.

### 6.2 `<span>` con `width` inline no hace nada sin `display: block`

`.ax-bar-fill` (barra de distribución por categoría/ubicación) es un `<span>`.
Un elemento `inline` ignora `width`/`height`: la barra medía 0px pase lo que
pase el `style="width:X%"`. Fix: `display: block` explícito en la regla base.

### 6.3 Dropdowns recortados por el `overflow-x` de la tabla

`.ax-table-wrap` necesita `overflow-x: auto` para el scroll horizontal en
tablas anchas, pero eso recorta cualquier `.dropdown-menu` (Popper por
defecto posiciona en `absolute`, dentro del contenedor con overflow). Fix:
`bootstrap.Dropdown` se instancia con `popperConfig: { strategy: 'fixed' }`
(`initDropdowns()` en `activos-ui.js`), así el menú escapa del recorte.

### 6.4 `DeleteView.delete()` ya no se invoca en Django ≥4.0

Las 4 vistas de borrado (`Categoria`, `SubCategoria`, `Ubicacion`, `Activo`)
tenían su guarda de "no borrar si tiene hijos" dentro de `delete()`. Desde
Django 4.0, `BaseDeleteView.post()` llama a `form_valid()`, no a `delete()` —
la guarda era código muerto y borrar una categoría con subcategorías lanzaba
`ProtectedError` (500) en vez de un mensaje de error. Las guardas se movieron
a `form_valid()`.

### 6.5 Acciones de escritura por `GET`, sin CSRF, con redirect abierto

`finalizar_mantenimiento` cambiaba estado vía `GET` (cacheable, prefetcheable,
sin CSRF) y redirigía con `request.META['HTTP_REFERER']` sin validar —
cualquier página externa podía encadenar la acción y decidir a dónde vuelve el
usuario. Ahora es `@require_POST` y usa `_url_de_retorno()`
(`url_has_allowed_host_and_scheme`) igual que reasignar/reubicar.

### 6.6 El historial guardaba el username

`_registrar_reasignacion_en_historial` guardaba `str(usuario)` (username) en
`valor_anterior`/`valor_nuevo`. Ahora usa `_nombre()` (Nombre Apellido) —
consistente con la regla de negocio en todo el resto de la interfaz.

---

## 7. Integración con el sidebar del Portal (SSO embebido)

### 7.1 Arquitectura

El menú lateral **no vive en este repositorio**: es un bundle React
independiente (`Portal-Paldaca/frontend/dist-nav/paldaca-nav.{js,css}`) que
Activos incluye vía `core/templates/includes/paldaca_nav.html` (sin
modificar — fuera del alcance de este rediseño):

```html
<link rel="stylesheet" href="{{ paldaca_nav_css }}">
<div id="paldaca-nav-root"></div>
<script>window.__PALDACA_NAV__ = { apiBaseUrl: …, currentApp: "activos", … };</script>
<script defer src="{{ paldaca_nav_js }}"></script>
```

`core/context_processors.py::paldaca_urls` resuelve esas URLs; en `DEBUG`
apuntan a `http://127.0.0.1:8000` (Portal backend). El componente React
agrega la clase `body.paldaca-nav-mounted` al montarse, y `core.css` reacciona
a esa clase para ceder el 100% del ancho al contenido (sin ella, se reserva
un hueco de `--app-sidebar-w-expanded` para un sidebar local que ya no existe).

Puertos de desarrollo (`docs/guia-integracion-programas-satelite.md`):
Portal backend `8000`, Portal frontend (Vite) `5173`, **Activos `8004`**.

### 7.2 Estado encontrado: conexión rota

Se validó end-to-end y se encontraron **dos causas independientes**, ambas
fuera de este repositorio, ninguna introducida por el rediseño (confirmado:
`base.html`, `paldaca_nav.html`, `context_processors.py` y `middleware.py`
—los cuatro archivos de la integración— no tienen diffs en esta sesión):

**a) `Portal-Paldaca/dev.env` sin `DJANGO_SECRET_KEY` → el backend del Portal
no arrancaba.**
`backend/config/env.py::load_paldaca_env()` usa `if dev.env existe: cargar
dev.env / elif key.env existe: cargar key.env` — un `elif`, no una superposición
de capas. Como `dev.env` sí existe (para overrides locales de cookies/MySQL)
pero no define `DJANGO_SECRET_KEY`, `key.env` nunca se cargaba y Django
lanzaba `ImproperlyConfigured` al arrancar. Sin el backend del Portal en el
puerto 8000, `paldaca-nav.js`/`.css` nunca se sirven.
**Fix aplicado:** se añadió `DJANGO_SECRET_KEY` (copiado de `key.env`) a
`Portal-Paldaca/dev.env`. Es un archivo local, no versionado (`.gitignore`),
así que no hay nada que commitear por esto.

**b) El bundle `paldaca-nav.js` lanzaba `ReferenceError: process is not
defined` al ejecutarse en el navegador → el sidebar nunca llegaba a montarse,
en NINGÚN satélite (no es específico de Activos).**
`frontend/vite.nav.config.ts` construye el bundle en modo *library* (IIFE)
sin el `define` de `process.env.NODE_ENV` que el build de aplicación normal sí
aplica automáticamente. React lee esa variable en su arranque; al no existir
`process` en el navegador, el módulo entero moría antes de exponer
`window.PaldacaNav`. El error queda enmascarado como `"Script error."` sin
archivo ni línea cuando el script se carga cross-origin (128.0.0.1:8004 →
127.0.0.1:8000) sin atributo `crossorigin`, que es exactamente como se sirve
en producción — por eso costó aislar la causa.

**Fix aplicado** en `Portal-Paldaca/frontend/vite.nav.config.ts`:

```ts
define: {
  "process.env.NODE_ENV": JSON.stringify("production"),
},
```

y se reconstruyó el bundle (`npm run build:nav`): `dist-nav/paldaca-nav.js`
pasó de 635 KB (con ramas de desarrollo de React sin eliminar) a 247 KB
minificado. Verificado en navegador tras el fix: `window.PaldacaNav` definido,
`body` recibe `paldaca-nav-mounted`, el `<aside class="paldaca-nav-sidebar">`
se renderiza con logo y navegación.

### 7.3 Pendiente — acción del usuario

`vite.nav.config.ts` y los artefactos regenerados en `dist-nav/` quedaron
**modificados sin commitear** en el repositorio `Portal-Paldaca` (otro
proyecto; no se hizo commit por ustedes):

```bash
cd Portal-Paldaca
git status --short frontend/vite.nav.config.ts frontend/dist-nav/
git add frontend/vite.nav.config.ts frontend/dist-nav/
git commit -m "fix(nav): define process.env.NODE_ENV en el build del sidebar embebible"
```

Sin este commit, cualquiera que reconstruya `dist-nav/` desde cero
(`npm run build:nav`) sin el `define` reproduce el mismo error.

### 7.4 Cómo levantar el entorno completo en desarrollo

```bash
# 1) Portal backend (sirve el sidebar + API de sesión)
cd Portal-Paldaca
venv/Scripts/python.exe backend/manage.py runserver 8000

# 2) Portal frontend (solo necesario para /login)
cd Portal-Paldaca/frontend
npm run dev          # 5173

# 3) Activos
cd ActivosPALDACA
venv/Scripts/python.exe manage.py runserver 8004
```

Los tres deben estar arriba para ver el sidebar montado con sesión real. Si
solo se necesita revisar maquetado/estilos de Activos sin el sidebar del
Portal, basta el paso 3 — el layout se degrada correctamente (contenido a
ancho completo) cuando el bundle del nav no está disponible, aunque sin la
navegación global.
