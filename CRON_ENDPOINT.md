# Tareas programadas (Coolify Scheduled Tasks)

ActivosPALDACA no tiene ningún cron activo todavía. El primero es el despachador de avisos por
reloj (`docs/plan-notificaciones.md`, Fase 2). Se configura como **Scheduled Task de Coolify**
sobre el contenedor `web` de `docker-compose.yml` — no hay endpoint HTTP, el comando corre dentro
del contenedor ya desplegado (mismo mecanismo que `enviar_notificaciones_hdt` en HojadeTiempo).

## `enviar_notificaciones_activos`

Evalúa las reglas de Activos que dependen del reloj (ver `activos/services/avisos.py`). Hoy solo
hay una:

| Regla | Qué detecta | Horario | A quién avisa |
|-------|-------------|---------|----------------|
| `usuario_inactivo_con_equipos` | Usuario `is_active=False` que sigue con equipo asignado — típicamente desactivado desde el panel de superadmin del Portal, no desde Activos (BR-USR-03 ya lo bloquea aquí si tiene equipos) | Diario, 08:00 hora local | Administradores de Activos (`modulo.admins`) |

Se avisa **una sola vez por episodio**: un marcador (`AvisoUsuarioInactivo`) evita repetir el
aviso mientras la situación no cambie, y se libera solo, en una corrida posterior, cuando el
usuario se reactiva o pierde todo el equipo asignado — así que si recae más adelante vuelve a
avisar. No hace falta correr esto más de una vez al día; correr más seguido no duplica nada
(la regla se autolimita a su hora), pero tampoco acelera la detección más allá de esa ventana.

### Configuración en Coolify

Recurso de ActivosPALDACA → **Scheduled Tasks** → nueva tarea, contenedor **`web`**:

```bash
python manage.py enviar_notificaciones_activos
```

La frecuencia de Coolify usa la zona horaria del servidor (por defecto UTC); Caracas es UTC−4
todo el año. Cada hora basta — la regla decide si le toca:

| Frecuencia si el servidor está en UTC | Si el servidor está en America/Caracas |
|-----------------------------------------|-------------------------------------------|
| `0 * * * *` | `0 * * * *` |

### Antes de programarlo

Probar sin enviar nada al Portal:

```bash
python manage.py enviar_notificaciones_activos --dry-run
python manage.py enviar_notificaciones_activos --regla usuario_inactivo_con_equipos --ahora --dry-run
```

`--ahora` ignora el horario (útil para probar fuera de las 08:00); `--regla` limita a una sola.

### Variables relevantes

Ya usadas por los avisos de hecho (`activo_creado`/`activo_asignado`), no hay nada nuevo que
configurar: `PALDACA_PORTAL_API_URL`, `PALDACA_NOTIFICACIONES_ACTIVAS`, `PALDACA_PORTAL_URL`,
`PALDACA_SHELL_PATH` (ver `SSAPI/settings.py`).

### Decisión pendiente antes de que esto le avise a alguien de verdad

Ningún usuario tiene hoy `rol=administrador` en el módulo `activos` en la base compartida
(confirmado en desarrollo al escribir esto). La audiencia `modulo.admins` no resuelve a nadie
hasta que se asigne ese rol desde el panel de superadmin del Portal — no es un bug de este
comando, es el mismo bloqueante ya documentado en `docs/plan-notificaciones.md` §1, y afecta
también a `activos.activo_creado` sin custodio y a cualquier otro aviso dirigido a "admins".
