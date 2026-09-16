# Tareas programadas (Coolify Scheduled Tasks)

ActivosPALDACA no tiene ningún cron activo todavía. El primero es el despachador de avisos por
reloj (`docs/plan-notificaciones.md`, Fase 2). Se configura como **Scheduled Task de Coolify**
sobre el contenedor `web` de `docker-compose.yml` — no hay endpoint HTTP, el comando corre dentro
del contenedor ya desplegado (mismo mecanismo que `enviar_notificaciones_hdt` en HojadeTiempo).

## `enviar_notificaciones_activos`

Evalúa las reglas de Activos que dependen del reloj (ver `activos/services/avisos.py`). Hoy hay
tres (`mantenimiento_estancado` sigue sin implementar):

| Regla | Qué detecta | Horario | A quién avisa |
|-------|-------------|---------|----------------|
| `usuario_inactivo_con_equipos` | Usuario `is_active=False` que sigue con equipo asignado — típicamente desactivado desde el panel de superadmin del Portal, no desde Activos (BR-USR-03 ya lo bloquea aquí si tiene equipos) | Diario, 08:00 hora local | Administradores de Activos (`modulo.admins`) |
| `etiqueta_sin_vincular` | `EtiquetaQR` en `PENDIENTE` hace más de `ACTIVOS_UMBRAL_ETIQUETA_SIN_VINCULAR_DIAS` días (default 30) | Diario, 09:00 hora local | Quien la creó (si se registró) + administradores |
| `asignacion_sin_planilla` | `HistorialMovimiento` de reasignación sin `archivo_planilla` hace más de `ACTIVOS_UMBRAL_ASIGNACION_SIN_PLANILLA_DIAS` días (default 7) | Diario, 10:00 hora local | Administradores de Activos |

Se avisa **una sola vez por episodio**: un marcador (`AvisoUsuarioInactivo` para la primera regla,
`AvisoPorUmbral` para las otras dos) evita repetir el aviso mientras la situación no cambie, y se
libera solo, en una corrida posterior, cuando se resuelve (usuario reactivado o sin equipo,
etiqueta vinculada/anulada, planilla archivada) — así que si recae más adelante vuelve a avisar.
No hace falta correr esto más de una vez al día; correr más seguido no duplica nada (cada regla se
autolimita a su hora), pero tampoco acelera la detección más allá de esa ventana.

Los umbrales de días (`etiqueta_sin_vincular`, `asignacion_sin_planilla`) se leen en caliente del
Portal en cada corrida: `GET /api/notificaciones/tipos/<codigo>/config/`, firmado igual que la
emisión (RN-31). Editarlos en `/configuracion/notificaciones` tiene efecto real en la corrida
siguiente del despachador — **no requiere reiniciar el contenedor ni tocar variables de
entorno**. Las variables de entorno de abajo solo importan como respaldo: si el Portal no
responde, no está activo, o el valor no es un entero positivo, la regla usa ese número local en
vez de fallar.

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
python manage.py enviar_notificaciones_activos --regla etiqueta_sin_vincular --ahora --dry-run
python manage.py enviar_notificaciones_activos --regla asignacion_sin_planilla --ahora --dry-run
```

`--ahora` ignora el horario (útil para probar fuera de las 08:00-10:00); `--regla` limita a una sola.

### Variables relevantes

Ya usadas por los avisos de hecho (`activo_creado`/`activo_asignado`), y también por la lectura de
`umbral_dias` (mismo cliente firmado, `PALDACA_PORTAL_API_URL`): `PALDACA_PORTAL_API_URL`,
`PALDACA_NOTIFICACIONES_ACTIVAS`, `PALDACA_PORTAL_URL`, `PALDACA_SHELL_PATH` (ver
`SSAPI/settings.py`). Nuevas para las reglas por umbral — **solo se usan como respaldo** si el
Portal no responde, con los mismos defaults que el catálogo:

```bash
ACTIVOS_UMBRAL_ETIQUETA_SIN_VINCULAR_DIAS=30
ACTIVOS_UMBRAL_ASIGNACION_SIN_PLANILLA_DIAS=7
```

### Decisión pendiente antes de que esto le avise a alguien de verdad

Ningún usuario tiene hoy `rol=administrador` en el módulo `activos` en la base compartida
(confirmado en desarrollo al escribir esto). La audiencia `modulo.admins` no resuelve a nadie
hasta que se asigne ese rol desde el panel de superadmin del Portal — no es un bug de este
comando, es el mismo bloqueante ya documentado en `docs/plan-notificaciones.md` §1, y afecta
también a `activos.activo_creado` sin custodio y a cualquier otro aviso dirigido a "admins".

---

## Despliegue a producción (Coolify)

Nada de esto necesita un recurso nuevo en Coolify: reutiliza la infraestructura ya descrita en
`Portal-Paldaca/docs/COOLIFY.md` (misma MySQL, mismo `DJANGO_SECRET_KEY` compartido, mismo
`PALDACA_PORTAL_API_URL` que ya usan `activo_creado`/`activo_asignado`). Es un despliegue de
código en dos repos más, si nunca se hizo, dar de alta el Scheduled Task por primera vez.

### 1. Migraciones a aplicar

Ninguna de las dos es solo de esta feature — cubre todo lo construido en esta serie de cambios,
por si el despliegue anterior a producción quedó atrás:

| Repo | Migraciones | Qué agregan |
|------|-------------|-------------|
| Portal-Paldaca | `notificaciones.0009` a `0012` | Tipos `usuario_inactivo_con_equipos`/Fase 1 de Activos, campo `umbral_dias`, tipos `mantenimiento_estancado`/`etiqueta_sin_vincular`/`asignacion_sin_planilla` con sus defaults |
| ActivosPALDACA | `activos.0010`, `activos.0011` | `AvisoUsuarioInactivo`, `AvisoPorUmbral` (marcadores de dedup) |

El entrypoint de cada contenedor ya corre `migrate` al arrancar (mismo mecanismo que el resto de
la Suite) — no hace falta un paso manual salvo que el despliegue automático esté deshabilitado.
Verificar con `python manage.py showmigrations notificaciones` / `showmigrations activos` en la
terminal del recurso si hay duda de que haya corrido.

### 2. Código: qué se despliega y en qué orden

El endpoint de lectura (`tipo_config_view`, solo Portal) y su cliente (`obtener_config_tipo`, solo
Activos) son **independientes por diseño**: si Activos llama antes de que el Portal tenga el
endpoint desplegado, la petición falla (404) y `_umbral_dias()` cae al valor local — nunca rompe
la regla, nunca hace fallar el cron. Aun así, el orden recomendado evita una corrida "a ciegas"
con los defaults:

1. **Portal-Paldaca primero** (`git push` a la rama de Coolify → redeploy). Trae `tipo_config_view`
   más las migraciones de la tabla de arriba.
2. **ActivosPALDACA después.** Trae `obtener_config_tipo`, `_umbral_dias`, y las dos reglas nuevas
   completas (`etiqueta_sin_vincular`, `asignacion_sin_planilla`).

Si por algún motivo se despliega Activos primero, no pasa nada roto: el despachador sigue
funcionando con los defaults de entorno hasta que el Portal quede arriba.

### 3. URL del Portal — ya no hace falta fijarla a mano

`PALDACA_PORTAL_API_URL` no aparece en la tabla de variables por satélite de
`Portal-Paldaca/docs/COOLIFY.md`, así que Activos caía al default de `SSAPI/settings.py`. Ese
default **apuntaba a `https://api.cpaldaca.com/api`**, un alias que esa misma guía marca como
opcional ("ya no hace falta... salvo que quieras conservarlo") — si no estaba configurado en el
proxy, tanto la emisión de eventos como esta lectura de `umbral_dias` fallaban en silencio
(`NOTIFICACION_NO_ENVIADA` / `CONFIG_TIPO_NO_DISPONIBLE` en el log, con los defaults locales
cubriendo el golpe). **Corregido en código**: el default de producción ahora es
`https://cpaldaca.com/api` (`SSAPI/settings.py` y `core/context_processors.py`, este último para
el sidebar embebido del navegador, no solo el cliente server-to-server) — coincide con "el Portal
sirve el SPA y proxea `/api/` al mismo origen" de `docs/COOLIFY.md`. No hace falta ninguna
variable de entorno nueva en Coolify para esto; `PALDACA_PORTAL_API_URL`/`PALDACA_API_BASE` siguen
disponibles si algún día hay que apuntar a otro lado.

### 4. Crear (o confirmar) el Scheduled Task

Si `enviar_notificaciones_activos` **todavía no existe** como Scheduled Task en Coolify (era el
caso al escribir el resto de este documento): recurso ActivosPALDACA → **Scheduled Tasks** → nueva
tarea, contenedor `web`, comando `python manage.py enviar_notificaciones_activos`, frecuencia
`0 * * * *` (ver tabla en "Configuración en Coolify" arriba). Si ya existe, no hace falta tocarlo
— el binario nuevo lo recoge el próximo deploy.

### 5. Verificar que quedó bien, sin esperar a la corrida horaria

Desde la terminal del recurso de Activos en Coolify:

```bash
python manage.py enviar_notificaciones_activos --regla etiqueta_sin_vincular --ahora --dry-run
```

Revisar los logs del contenedor inmediatamente después (`docker logs` o el visor de logs de
Coolify) buscando:

- `CONFIG_TIPO_NO_DISPONIBLE | codigo=activos.etiqueta_sin_vincular` → el Portal no respondió o
  rechazó la petición (ver paso 3: `PALDACA_PORTAL_API_URL`, o que el Portal ya tenga
  desplegado el endpoint).
- Ausencia de ese log → el GET firmado funcionó; la regla evaluó con el `umbral_dias` real del
  Portal, no con el default de entorno.

Para confirmar el número exacto que se usó, cambiar temporalmente `umbral_dias` de un tipo desde
`/configuracion/notificaciones` a un valor obviamente distinto del default (ej. de 30 a 3 días) y
repetir el `--dry-run`: si el conteo de candidatos cambia, la lectura en caliente funciona.
Revertir el valor después — es lo mismo que se verificó en desarrollo antes de este despliegue
(ver `docs/plan-notificaciones.md`).

### 6. Antes de que esto le avise a alguien de verdad en producción

Repite el bloqueante de la sección anterior: sin al menos un usuario con `rol=administrador` en
el módulo `activos` (Portal → panel de superadmin), la audiencia `modulo.admins` sigue
resolviendo vacía en producción igual que en desarrollo. Confirmarlo antes de anunciar la feature,
no después.
