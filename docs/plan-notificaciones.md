# Plan de acción — Notificaciones de Activos

Documento de planificación (no describe solo lo ya implementado). Extiende al módulo Activos
el sistema de notificaciones de PALDACA Suite, siguiendo el mismo patrón híbrido que ya corre en
producción en HDT: **avisos de hecho** (se emiten donde ocurre el cambio) para todo lo que tiene
un punto de código claro, y un **despachador por reloj** para lo que no lo tiene.

Referencia de arquitectura: `Portal-Paldaca/docs/plan-sistema-notificaciones.md` (el bus) y
`HojadeTiempo/notificaciones/avisos.py` + `enviar_notificaciones_hdt` (la implementación de
referencia del híbrido).

---

## 1. Estado actual (punto de partida)

Ya integrado y en producción desde la Fase 3 del plan del Portal:

| Evento | Dónde se emite | Audiencia |
|--------|-----------------|-----------|
| `activos.activo_creado` | `ActivoCreateView.form_valid()`, `etiqueta_alta()` | Admins de Activos (Portal) + custodio si ya viene asignado |
| `activos.activo_asignado` | `ActivoUpdateView.form_valid()`, `reasignar_activo()`, `acciones_masivas()` | El nuevo custodio (la masiva agrupa en un solo aviso) |

Y desde este mismo plan, Fase 1 completa:

| Evento | Dónde se emite | Audiencia |
|--------|-----------------|-----------|
| `activos.mantenimiento_iniciado` | `MantenimientoCreateView.form_valid()` | Custodio (si tiene) |
| `activos.mantenimiento_finalizado` | `finalizar_mantenimiento()` | Custodio |
| `activos.activo_desasignado` | `_registrar_reasignacion_en_historial()` (`ActivoUpdateView`, `reasignar_activo`, `acciones_masivas`) | Custodio **anterior** (la masiva agrupa por cada anterior distinto) |
| `activos.activo_baja` | `ActivoUpdateView.form_valid()` (cambio a `IN`), `ActivoDeleteView.form_valid()` (antes de borrar) | Custodio (si tenía) + admins |

Y adelantado de la Fase 2 (ver abajo):

| Evento | Dónde se emite | Audiencia |
|--------|-----------------|-----------|
| `activos.usuario_inactivo_con_equipos` | `enviar_notificaciones_activos` (despachador diario, 08:00) | Admins de Activos |
| `activos.etiqueta_sin_vincular` | `enviar_notificaciones_activos` (despachador diario, 09:00) | Quien creó la etiqueta (si se registró) + admins |
| `activos.asignacion_sin_planilla` | `enviar_notificaciones_activos` (despachador diario, 10:00) | Admins de Activos |

Implementación: `activos/services/avisos.py`, `activos/services/notificaciones_portal.py` (cliente
firmado, idéntico al de HDT y Códigos). Tests: `activos/tests/test_notificaciones.py`. Cron:
`CRON_ENDPOINT.md`.

### ⚠️ Bloqueante a resolver antes de sumar audiencia "admins"

**Mitad resuelto.** `activos.activo_creado` incluye a los **administradores del módulo Activos
según el Portal** (`rol=administrador` + acceso a `activos`). El gap de *enforcement* que este
párrafo señalaba (Activos no aplicaba ese rol en sus vistas) ya se cerró: ver BR-ACC-04b en
`docs/BUSINESS_RULES.md` — gestión ahora exige `AdminActivoRequiredMixin` /
`@requiere_admin_activo`, y solo queda abierto a cualquiera con el módulo "Mis Activos".

Lo que **sigue sin resolver** es la parte de datos: en la base compartida de desarrollo, a la
fecha de este párrafo, **ningún usuario tiene `rol=administrador` en el módulo `activos`**
(confirmado directamente contra la BD al implementar `usuario_inactivo_con_equipos`). Mientras
eso no cambie, **todos** los avisos que este plan dirige a "admins" — incluido el que ya está en
producción — no le llegan a nadie; es silencioso, no da error. **Acción pendiente, no es
código:** asignar `rol=administrador` en el módulo `activos` a quien corresponda (típicamente
quien hoy gestiona el inventario), desde el panel de superadmin del Portal.

---

## 2. Principios (heredados del plan del Portal y de la implementación en HDT)

1. **Hecho vs reloj, no todo por cron.** Si hay un punto de código donde el cambio ocurre
   (alta, reasignación, fin de mantenimiento), el aviso se emite ahí: es inmediato y no necesita
   recordar a quién ya se avisó. Solo lo que nadie dispara (un estado que se detecta con el
   tiempo, no con un evento) pasa por el despachador.
2. **Todos los avisos filtran por acceso al módulo `activos` y `is_active=True`, nunca
   superusuarios** — mismo patrón que HDT y que `avisar_activo_creado()` ya usa vía la audiencia
   del Portal.
3. **Nunca lanza.** `transaction.on_commit` + captura de errores de red; si el Portal está
   caído, se registra `NOTIFICACION_NO_ENVIADA` y el flujo de negocio sigue.
4. **Menos ruido que FOMO.** Alta rotación de activos (reubicaciones, ediciones menores) no
   es notificación. Agregar en un resumen antes que mandar uno por evento.
5. **No inventar datos.** Si el aviso necesita una fecha o un umbral que el modelo no tiene
   (mantenimiento preventivo, garantía), no se implementa hasta decidir el cambio de esquema.

---

## 3. Catálogo propuesto

### 3.1 Avisos de hecho (Fase 1 — sin decisiones pendientes, listos para implementar)

| Código | Hecho | Dónde engancha | Destinatario |
|--------|-------|-----------------|--------------|
| `activos.mantenimiento_iniciado` | El activo entra a mantenimiento (`Mantenimiento.save()` pone `Activo.estado = EM`) | `Mantenimiento.save()` o la vista de alta (`MantenimientoCreateView.form_valid()`) | Custodio (si tiene) |
| `activos.mantenimiento_finalizado` | Último mantenimiento en proceso se cierra y el activo vuelve a `AC` | `finalizar_mantenimiento()` | Custodio |
| `activos.activo_desasignado` | Reasignación deja al custodio anterior sin el equipo (incluye "dejar sin asignar") | `_registrar_reasignacion_en_historial()` — mismo punto que ya dispara `activo_asignado`, agregar el aviso al anterior | Custodio **anterior** |
| `activos.activo_baja` | El activo pasa a `IN` (inactivo) o se elimina (`ActivoDeleteView`) | `ActivoUpdateView.form_valid()` (cambio a `IN`) y `ActivoDeleteView.form_valid()` | Custodio (si tenía) + admins |

Notas de diseño:

- `activo_desasignado` reusa el mismo hook que ya calcula `usuario_anterior` vs `usuario_nuevo`
  en `_registrar_reasignacion_en_historial()` (`activos/views.py`) — no hace falta un segundo
  query, solo emitir cuando `usuario_anterior` existía y `usuario_nuevo` es distinto (incluido
  `None`).
- `mantenimiento_iniciado` puede enredarse con `Mantenimiento.save()` corriendo tanto en alta
  como en edición; conviene engancharlo en la vista (`form_valid`), no en el modelo, para no
  emitir en cada guardado si el mantenimiento ya estaba en proceso (mismo criterio que HDT usó
  para no avisar en cada carga de página).
- `activo_baja` por eliminación necesita capturar los datos del custodio **antes** de que
  `ActivoDeleteView` borre la fila (el historial se borra en cascada, BR-ACT-12).

**Criterio de salida:** un mantenimiento que finaliza avisa al custodio en menos de un minuto
(vía campana); un activo eliminado con custodio asignado deja un aviso a esa persona aunque el
registro ya no exista en Activos.

### 3.2 Avisos por reloj (Fase 2 — necesita el despachador + decisiones de umbral)

| Código | Regla | Fuente de datos | Para quién |
|--------|-------|------------------|------------|
| `activos.usuario_inactivo_con_equipos` | Usuario con `is_active=False` que sigue teniendo activos con `usuario_asignado = él` | `core_usuario` (vía Portal) + `Activo.usuario_asignado` | Admins de Activos |
| `activos.mantenimiento_estancado` | Mantenimiento en estado `EN_PROCESO` hace más de N días | `Mantenimiento.fecha` + `estado` | Admins |
| `activos.etiqueta_sin_vincular` | `EtiquetaQR` en `PENDIENTE` hace más de N días desde `fecha_creacion` | `EtiquetaQR` | Quien la creó (`creada_por`) + admins |
| `activos.asignacion_sin_planilla` | `HistorialMovimiento` tipo `REASIGNACION` sin `archivo_planilla`, hace más de N días | `HistorialMovimiento` | Admins |
| `activos.resumen_semanal_admins` | Altas, reasignaciones y mantenimientos de los últimos 7 días, en un solo aviso | Conteos sobre las tablas anteriores | Admins |

**Por qué `usuario_inactivo_con_equipos` no puede ser un aviso de hecho:** la desactivación de
un usuario puede ocurrir **fuera de Activos** (panel de superadmin del Portal, u otro satélite
con acceso a `core_usuario`). `BR-USR-03` solo bloquea la desactivación *si ocurre desde la
pantalla de Activos*; si ocurre desde otro lado, Activos no tiene ningún hook que lo detecte.
Es, con diferencia, **el aviso de mayor valor de este plan**: hoy un equipo puede quedar en manos
de alguien que ya no tiene cuenta activa, sin que nadie se entere.

**Criterio de salida:** con un usuario desactivado desde el Portal (no desde Activos) y con
equipos asignados, el despachador lo detecta en la corrida siguiente y avisa a los admins de
Activos — sin que Activos haya tenido que interceptar esa desactivación.

### 3.3 Bloqueados por falta de datos (no entran en este plan)

| Idea | Por qué está bloqueada |
|------|--------------------------|
| Mantenimiento preventivo próximo / vencido | `Mantenimiento` solo registra `fecha` (fecha de **registro**, `auto_now_add`) y estado en proceso/finalizado. No existe periodicidad ni próxima fecha programada, ni a nivel de `Activo` ni de `SubCategoria`. |
| Garantía por vencer | `Activo` no tiene fecha de compra ni de garantía. |

Estas dos requieren decisión de producto + migración de esquema antes de poder planificarse en
serio (ver sección 5).

---

## 4. Plan por fases

### Fase 0 — Ya hecho
`activo_creado`, `activo_asignado`. Sin acción.

### Fase 1 — Avisos de hecho (mantenimiento, pérdida de custodia, baja) ✅ hecha (septiembre 2026)

**Objetivo:** cubrir los cuatro avisos de la sección 3.1, mismo patrón que los hooks de HDT
(`avisos.py` + llamada desde la vista/servicio donde ocurre el cambio, `transaction.on_commit`).

Trabajo hecho:

- `activos/services/avisos.py`: `avisar_mantenimiento_iniciado()`,
  `avisar_mantenimiento_finalizado()`, `avisar_activos_desasignados()` (plural: agrupa varios
  activos del mismo custodio anterior en un solo aviso, igual que `avisar_activos_asignados`),
  `avisar_activo_baja()`.
- Enganchado en `mantenimientos/views.py` (`MantenimientoCreateView.form_valid()`,
  `finalizar_mantenimiento()`) y `activos/views.py` (`ActivoUpdateView.form_valid()`,
  `ActivoDeleteView.form_valid()`, `reasignar_activo()`, `acciones_masivas()` —
  las tres últimas comparten el hook de `_registrar_reasignacion_en_historial()` para saber si
  hubo `usuario_anterior`).
- Seed de los 4 tipos en el Portal (`backend/notificaciones/migrations/0010_seed_tipos_activos_fase1.py`):
  `payload.usuario_ids` para los tres primeros; `activo_baja` suma `modulo.admins`, igual que
  `activo_creado`.
- 10 tests nuevos en `activos/tests/test_notificaciones.py` (183 → 193 en el repo).

Decisiones tomadas al implementar (no estaban en el plan original):

- `activo_desasignado` en `acciones_masivas` agrupa por custodio anterior, no por activo: si una
  masiva mueve equipos de 2 personas distintas a una tercera, salen 2 avisos (uno por persona que
  pierde equipo), no uno por activo — mismo criterio anti-ruido que ya usa `activo_asignado`.
- El deep link de `activo_desasignado` va siempre a `mis-activos-list`, nunca a la ficha del
  activo: el custodio anterior ya no lo puede ver (`mis-activos-detail` filtra por dueño) y le
  daría 404.
- El deep link de `activo_baja` por eliminación va al listado (`activo-list`), no a la ficha: la
  fila ya no existe. Por estado→`IN` sí puede ir a la ficha (`activo-detail`), porque el registro
  sigue vivo.
- `MantenimientoUpdateView` (editar un mantenimiento existente, incluido cambiar su `estado` a
  mano desde el formulario) **no** dispara ningún aviso — solo `MantenimientoCreateView` y
  `finalizar_mantenimiento()`, tal como estaba scopeado. Es la misma asimetría que ya existe en
  `activo_asignado` (edición genérica no notifica, solo los flujos dedicados).

**Criterio de salida — cumplido:** los cuatro eventos, verificados con tests y con una corrida
real contra el Portal de desarrollo (`Evento` + `BandejaItem` para cada uno, incluido
`activo_baja` llegando tanto al admin como al custodio en el mismo evento). Datos de prueba
eliminados después.

### Fase 2 — Despachador por reloj

**Objetivo:** los cinco avisos de la sección 3.2, con `enviar_notificaciones_activos` como
Scheduled Task de Coolify.

#### `usuario_inactivo_con_equipos` — hecho

Implementado adelantado del resto de la Fase 2 (era, con diferencia, el de mayor valor — ver
sección 3.2). Diferencias con lo que este documento planificaba originalmente:

- **Diario (08:00), no cada hora.** No es un chequeo calendario como los de HDT (que solo son
  verdad una hora a la semana); es un estado que persiste hasta que alguien reasigna. Correr el
  despachador cada hora sin más habría re-avisado en cada corrida mientras nadie actuara —
  demasiado ruido. Diario alcanza para el nivel de urgencia real del caso.
- **Dedupe propio (`AvisoUsuarioInactivo`).** El riesgo de la sección 6 ("sin dedupe en el
  Portal, un aviso que no se calendariza se repite") aplicaba de lleno aquí — a diferencia de
  `recordatorio_lunes`/`recordatorio_viernes` de HDT, que se resuelven solos porque la condición
  cambia de una semana a otra. Se resolvió con una marca local por usuario que se libera solo al
  reactivarse o perder todo el equipo, no con el `dedupe_key` pendiente del Portal (Fase 4 del
  plan del Portal, sigue sin implementarse).
- No requirió ningún cambio en Portal-Paldaca ni en Nómina: Activos ya tiene `is_active` del
  usuario vía su propio `AUTH_USER_MODEL` compartido (`Activo.usuario_asignado__is_active`), así
  que no hace falta que Portal lea la tabla `activos_activo` ni que Activos reciba un webhook.

Trabajo: `activos/services/avisos.py` (`usuarios_inactivos_con_equipos()`,
`avisar_usuarios_inactivos_con_equipos()`, `_limpiar_avisos_resueltos()`), modelo
`AvisoUsuarioInactivo` (migración `activos/migrations/0010`), comando
`enviar_notificaciones_activos`, seed en Portal (`backend/notificaciones/migrations/0009`), tests
en `activos/tests/test_notificaciones.py`. Ver `CRON_ENDPOINT.md`.

**Criterio de salida — cumplido, verificado dos veces:** tests (18, incluida idempotencia y
recaída tras reactivación) y una corrida real contra el Portal de desarrollo (usuario y admin de
prueba, servidores locales de ambos repos, revisando `BandejaItem` en la base) — ⚠️ con un admin
de Activos temporal creado a mano para la prueba, porque hoy nadie tiene ese rol en el Portal (ver
bloqueante en sección 1): el aviso funciona, pero en producción no le llega a nadie hasta que se
asigne el rol.

#### `etiqueta_sin_vincular` / `asignacion_sin_planilla` — hechas (septiembre 2026)

Implementadas en el mismo despachador que `usuario_inactivo_con_equipos`
(`enviar_notificaciones_activos`, diario a las 09:00 y 10:00 respectivamente).

- `activos/services/avisos.py`: `etiquetas_sin_vincular()` / `avisar_etiquetas_sin_vincular()`
  (agrupa por `creada_por`: un aviso por creador — así el creador solo ve sus propias etiquetas,
  no las de otros — que además siempre llega a admins vía la audiencia del tipo) y
  `asignaciones_sin_planilla()` / `avisar_asignaciones_sin_planilla()` (un solo aviso agregado por
  corrida, solo admins).
- Dedup: **sí necesitaron marcador**, a diferencia de las reglas de HDT — la condición persiste
  (una etiqueta sigue `PENDIENTE`, una reasignación sigue sin planilla) hasta que alguien actúa,
  no se resuelve con el calendario. Se generalizó `AvisoUsuarioInactivo` en un modelo nuevo,
  `AvisoPorUmbral` (`regla` + `objeto_id`), en vez de crear dos tablas casi idénticas.
- ✅ **`umbral_dias` ya se lee en caliente del Portal** (cerrado el mismo día). Nuevo endpoint
  `GET /api/notificaciones/tipos/<codigo>/config/` (Portal, `tipo_config_view`), autenticado igual
  que la emisión — firma de servicio para el cron, cookie de admin del módulo como respaldo — y
  con el mismo chequeo de pertenencia que `emitir_evento_view` (`tipo.modulo_origen != cliente` →
  403: un satélite no puede leer la config de otro). Cliente en Activos:
  `notificaciones_portal.obtener_config_tipo()` + `avisos._umbral_dias()`. Cada corrida del
  despachador hace un GET firmado antes de evaluar la regla; si el Portal no responde, no está
  activo, o el valor no es un entero positivo, cae a la variable de entorno local
  (`ACTIVOS_UMBRAL_ETIQUETA_SIN_VINCULAR_DIAS` / `ACTIVOS_UMBRAL_ASIGNACION_SIN_PLANILLA_DIAS`,
  mismos defaults 30 / 7 días) — nunca bloquea la regla. Verificado en vivo cambiando el umbral de
  `etiqueta_sin_vincular` a 3 días en el Portal (muy por debajo del default local de 30) y
  confirmando que Activos detectó etiquetas de 5 días que el default local no habría detectado;
  restaurado a 30 después de la prueba.
- 29 tests nuevos (`activos/tests/test_notificaciones.py`: 18 de detección + 11 de
  `obtener_config_tipo`/`_umbral_dias`) y 7 más del lado del Portal
  (`TipoConfigViewTests` en `backend/notificaciones/tests.py`), verificado en vivo contra el
  Portal de desarrollo dos veces — la corrida de detección encontró 9 reasignaciones legítimas ya
  vencidas en la base compartida (dato real, no de prueba), y la corrida de wiring del umbral
  encontró 186 etiquetas reales al bajar el umbral a 3 días (confirmando que el valor sí viene del
  Portal). En ambos casos: eventos, `BandejaItem` y marcadores `AvisoPorUmbral` generados por la
  prueba se limpiaron después, sin tocar los datos reales subyacentes (activos, historial,
  etiquetas) ni el `umbral_dias` restaurado a su valor original.

#### `mantenimiento_estancado` y `resumen_semanal_admins` — pendientes

`mantenimiento_estancado` deliberadamente no se implementó en esta iteración. Trabajo restante
para las dos: `activos/services/avisos.py` → `mantenimientos_estancados()` + `avisar_*`;
`resumen_semanal_admins` (una vez por semana, agrega altas/reasignaciones/mantenimientos de los
últimos 7 días); sumar ambas reglas a `HORARIOS` en `enviar_notificaciones_activos`.

### Fase 3 — Mantenimiento preventivo y garantía (solo si se decide el modelo)

No se planifica en detalle aquí — depende de una decisión de producto (sección 5) que cambia el
esquema de `Activo` y/o `SubCategoria`. Una vez resuelta, sigue el mismo patrón de esta Fase 2
(regla por reloj + despachador).

---

## 5. Decisiones necesarias antes de seguir

| # | Decisión | Estado |
|---|----------|--------|
| 1 | ¿Quiénes son `rol=administrador` del módulo `activos` en el Portal? | ⚠️ **Sigue pendiente** — bloquea toda audiencia "admins" de este plan, incluido lo ya emitido en Fase 0 y Fase 1 |
| 2 | Umbral de días para "mantenimiento estancado" | ✅ **Resuelto como dato, no como código** — `TipoNotificacion.umbral_dias`, default 15 días, editable en `/configuracion/notificaciones` sin deploy (Portal, migraciones `0011`/`0012`) |
| 3 | Umbral de días para "etiqueta sin vincular" | ✅ Igual mecanismo, default 30 días |
| 4 | Umbral de días para "asignación sin planilla" | ✅ Igual mecanismo, default 7 días |
| 5 | ¿Avisamos siempre al custodio anterior al perder un equipo, o solo si lo pierde sin reemplazo? | ✅ **Resuelto en Fase 1**: siempre avisa (`avisar_activos_desasignados`, sin distinguir si hay reemplazo) |
| 6 | Mantenimiento preventivo: ¿periodicidad por `SubCategoria` o fecha explícita por `Activo`? | Sigue pendiente — bloquea Fase 3 completa |
| 7 | ¿Activos guarda fecha de compra/garantía, o ese dato vive en otro sistema (contabilidad)? | Sigue pendiente — bloquea Fase 3 (garantía) |

Idea tomada de `Renata-IA/Notificaciones/models.py` (`ConfiguracionAlertas`): en vez de que un
umbral de días sea una decisión de producto que bloquea código indefinidamente, es un campo
editable con un default razonable — el generador de la alerta (cuando se implemente su lógica de
detección en Activos) lee el valor vigente en cada corrida, así que afinar el número no requiere
tocar código ni volver a desplegar. Las decisiones #2-#4 seguían "pendientes" solo porque el plan
las trataba como definitivas; como dato con default son triviales.

---

## 6. Riesgos

| Riesgo | Mitigación |
|--------|------------|
| Sin admins reales en el Portal, los avisos de "admins" no llegan a nadie (silencioso) | Decisión #1 antes de la Fase 2; test que falle si la audiencia resuelve vacío en un escenario de prueba con admin definido |
| El despachador corre dos veces en la misma hora (reinicio de Coolify, doble Scheduled Task) y duplica el resumen semanal | Mismo patrón que HDT: cada regla se ata a un día/hora exactos, así que una segunda corrida en la misma hora vuelve a emitir. Si esto no es aceptable para Activos, adoptar la clave de deduplicación pendiente en la Fase 4 del plan del Portal antes de la Fase 2 de este plan |
| `activo_baja` por `ActivoDeleteView` pierde los datos del custodio si no se capturan antes del `super().form_valid()` | Cubrir con un test explícito: eliminar un activo asignado y verificar que el aviso salió con el `usuario_ids` correcto |
| Resumen semanal se vuelve ruido si nadie lo lee | Revisar en 2-3 semanas de uso si conviene apagarlo (`activo=False` en el tipo, sin tocar código) |

---

## 7. Orden de trabajo recomendado

1. ⚠️ **Decisión #1 (admins en el Portal) — sigue pendiente**, no es código, se puede resolver
   hoy. Bloquea el valor real de todo lo que ya está implementado con audiencia "admins":
   `activo_creado` sin custodio, `activo_baja`, `usuario_inactivo_con_equipos`,
   `etiqueta_sin_vincular` y `asignacion_sin_planilla`.
2. ~~Fase 1 (4 avisos de hecho)~~ — **hecha**.
3. ~~Fase 2: `usuario_inactivo_con_equipos`~~ — **hecho**, adelantado del resto de la Fase 2 (ver
   sección 4). No esperó a la Fase 1 porque no comparte código con ella.
4. ~~Decisiones #2, #3, #4~~ (umbrales) — **resueltas** como configuración (sección 5). ~~Decisión
   #5~~ (desasignado siempre avisa) — **resuelta** al construir la Fase 1.
5. ~~Fase 2: `etiqueta_sin_vincular`, `asignacion_sin_planilla`~~ — **hechas**. Queda
   `mantenimiento_estancado` (deliberadamente fuera de esta iteración) y `resumen_semanal_admins`.
6. ~~Sincronización real Activos↔Portal de `umbral_dias`~~ — **hecha** (`GET .../tipos/<codigo>/config/`
   firmado). Editar el umbral en `/configuracion/notificaciones` ya tiene efecto real en la corrida
   siguiente del despachador, no solo en el catálogo.
7. Decisiones #6 y #7, y solo entonces evaluar la Fase 3.
