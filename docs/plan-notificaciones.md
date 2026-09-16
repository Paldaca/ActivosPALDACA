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

Implementación: `activos/services/avisos.py`, `activos/services/notificaciones_portal.py` (cliente
firmado, idéntico al de HDT y Códigos). Tests: `activos/tests/test_notificaciones.py`.

### ⚠️ Bloqueante a resolver antes de sumar audiencia "admins"

`activos.activo_creado` incluye a los **administradores del módulo Activos según el Portal**
(`rol=administrador` + acceso a `activos`). Pero Activos **no aplica ese rol en sus vistas**
(gap ya documentado en `docs/BUSINESS_RULES.md` → "Reglas NO implementadas": *"Permisos elevados
para `rol=administrador` dentro del módulo: método existe en modelo; vistas no lo usan"*).
Cualquiera con acceso al módulo puede dar de alta y asignar activos hoy.

Si en el Portal nadie tiene ese rol en Activos, **todos** los avisos que este plan dirige a
"admins" (usuario desactivado con equipos, mantenimiento estancado, etc.) no le llegan a nadie.
**Acción previa a la Fase 2:** confirmar en `/configuracion/notificaciones` del Portal quiénes
son `rol=administrador` en el módulo `activos`, o asignarlo a quien corresponda (típicamente
quien hoy gestiona el inventario). No requiere cambios de código, solo datos.

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

### Fase 1 — Avisos de hecho (mantenimiento, pérdida de custodia, baja)

**Objetivo:** cubrir los cuatro avisos de la sección 3.1, mismo patrón que los hooks de HDT
(`avisos.py` + llamada desde la vista/servicio donde ocurre el cambio, `transaction.on_commit`).

Trabajo:

- `activos/services/avisos.py`: agregar `avisar_mantenimiento_iniciado()`,
  `avisar_mantenimiento_finalizado()`, `avisar_activo_desasignado()`, `avisar_activo_baja()`.
- Enganchar en `mantenimientos/views.py` (`MantenimientoCreateView`, `finalizar_mantenimiento`)
  y `activos/views.py` (`ActivoUpdateView`, `ActivoDeleteView`,
  `_registrar_reasignacion_en_historial`).
- Seed de los 4 tipos en el Portal (migración nueva en `backend/notificaciones/`), audiencia
  `payload.usuario_ids` (Activos resuelve al destinatario, igual que ya hace con
  `activo_asignado`) salvo `activo_baja`, que además suma `modulo.admins`.
- Tests en `activos/tests/test_notificaciones.py`, mismo estilo que los de la Fase 0.

**Criterio de salida:** los cuatro eventos de la sección 3.1, verificados con tests y con una
prueba end-to-end contra el Portal de desarrollo (mismo procedimiento que se usó para
`activo_creado`/`activo_asignado`).

### Fase 2 — Despachador por reloj

**Objetivo:** los cinco avisos de la sección 3.2, con `enviar_notificaciones_activos` como
Scheduled Task de Coolify — cada hora, igual que `enviar_notificaciones_hdt`.

Requisitos previos (bloqueantes, ver sección 1 y 5):

- Admins de Activos definidos en el Portal.
- Umbrales de días decididos (ver sección 5).

Trabajo:

- `activos/services/avisos.py`: funciones `usuarios_inactivos_con_equipos()`,
  `mantenimientos_estancados()`, `etiquetas_sin_vincular()`, `asignaciones_sin_planilla()`, y sus
  correspondientes `avisar_*`.
- Comando `enviar_notificaciones_activos` (mismo esqueleto que `enviar_notificaciones_hdt`:
  `--dry-run`, `--regla`, `--ahora`), con `resumen_semanal_admins` como quinta regla (una vez
  por semana, ej. lunes 08:00).
- Seed de los 5 tipos en el Portal.
- Tests: sin destinatarios no emite, umbral estricto (N-1 días no avisa, N sí), idempotencia de
  ejecutar dos veces en la misma hora (si el aviso no tiene dedupe en el Portal todavía, ver
  riesgo en sección 6).

**Criterio de salida:** un usuario desactivado desde el Portal con equipos asignados genera aviso
a los admins de Activos en la corrida horaria siguiente, sin intervención de Activos.

### Fase 3 — Mantenimiento preventivo y garantía (solo si se decide el modelo)

No se planifica en detalle aquí — depende de una decisión de producto (sección 5) que cambia el
esquema de `Activo` y/o `SubCategoria`. Una vez resuelta, sigue el mismo patrón de esta Fase 2
(regla por reloj + despachador).

---

## 5. Decisiones necesarias antes de seguir

| # | Decisión | Bloquea |
|---|----------|---------|
| 1 | ¿Quiénes son `rol=administrador` del módulo `activos` en el Portal? | Toda audiencia "admins" de este plan, incluido lo ya emitido en Fase 0 |
| 2 | Umbral de días para "mantenimiento estancado" | `activos.mantenimiento_estancado` |
| 3 | Umbral de días para "etiqueta sin vincular" | `activos.etiqueta_sin_vincular` |
| 4 | Umbral de días para "asignación sin planilla" | `activos.asignacion_sin_planilla` |
| 5 | ¿Avisamos siempre al custodio anterior al perder un equipo, o solo si lo pierde sin reemplazo? | `activos.activo_desasignado` |
| 6 | Mantenimiento preventivo: ¿periodicidad por `SubCategoria` o fecha explícita por `Activo`? | Fase 3 completa |
| 7 | ¿Activos guarda fecha de compra/garantía, o ese dato vive en otro sistema (contabilidad)? | Fase 3 (garantía) |

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

1. Decisión #1 (admins en el Portal) — no es código, se puede resolver hoy.
2. Fase 1 completa (4 avisos de hecho) — sin decisiones pendientes, mismo patrón ya probado en HDT.
3. Decisiones #2, #3, #4, #5.
4. Fase 2: empezar por `usuario_inactivo_con_equipos` (mayor valor, ver sección 3.2), luego el
   resto del despachador.
5. Decisiones #6 y #7, y solo entonces evaluar la Fase 3.
