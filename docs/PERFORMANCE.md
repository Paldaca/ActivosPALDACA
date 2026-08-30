# Rendimiento de ActivosPALDACA

## Instrumentación

Con `DEBUG=True`, cada respuesta incluye `Server-Timing` y registra:

- tiempo total y tiempo SQL;
- cantidad de consultas;
- tamaño de la respuesta;
- ruta, método y estado HTTP.

El log usa el nombre `paldaca.performance`. No se registra SQL ni contenido
de usuario y el middleware queda inactivo fuera de desarrollo.

El Portal añade medidas locales en las herramientas de rendimiento del
navegador:

- `paldaca-auth-handshake`;
- `paldaca-module-<codigo>-total`;
- marcas de inicio, carga del iframe y recepción de `ready`.

## Resultado de la fase

Medición local con datos reales, en modo desarrollo:

- `/`: 9 consultas, 18 KB de HTML y 42-55 ms en caliente.
- `/activos/`: 14 consultas, 240 KB de HTML y 175 ms.
- `/usuarios/`: 6 consultas, 65 KB de HTML y 48 ms.
- Perfil de usuario: 5 consultas, 219 KB de HTML y 71 ms.
- Detalle de activo: 10 consultas, 28 KB de HTML y 47 ms.

La primera compilación local de plantillas tardó cerca de 4,4 segundos. La
segunda petición bajó a 42-55 ms. Esta diferencia debe medirse también en el
entorno desplegado, donde `DEBUG=False` usa carga de plantillas optimizada.

Cambios estructurales:

- SSO pasó de recargar usuario, módulos y acceso por separado a reutilizar el
  usuario autenticado y un único snapshot de módulos por petición.
- El resumen de usuarios pasó de cuatro conteos a un agregado.
- El perfil deriva sus conteos de la colección ya cargada.
- Los selectores de responsables ya no incrustan el catálogo completo:
  consultan un endpoint paginado al abrir o buscar.
- El resumen de etiquetas pasó de cuatro consultas a una.
- Se eliminó el N+1 de subcategorías y se limitó el historial visible de
  mantenimientos.
- `static_v` conserva en memoria las rutas y fechas ya resueltas.

Los presupuestos automáticos actuales son 9 consultas para usuarios, 8 para
perfil y 16 para listado de activos. Incluyen sesión y middleware de pruebas.

## Iframe

El Portal mantiene la carga normal hasta 15 segundos. Entre 15 y 30 segundos
muestra un aviso no destructivo y permite abrir el módulo en otra pestaña.
Solo declara error después de 30 segundos. `load`, `ready`, acceso denegado,
sesión expirada y reintento cancelan los temporizadores vigentes.

## Riesgos pendientes

- El PDF se genera de forma síncrona; se registra dentro del tiempo total de
  la petición. Si supera el presupuesto deberá moverse a una cola.
- El perfil puede producir HTML grande cuando una persona tiene muchos
  activos; la siguiente fase debería paginar esa tabla.
- Servir `/media/` mediante Django no es adecuado para producción.
- No existe caché compartida. Esta fase no introduce Redis ni Celery.
