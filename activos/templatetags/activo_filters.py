"""Filtros y tags de presentación del módulo de Activos.

Aquí vive la capa de traducción entre el modelo de datos y el lenguaje que ve
el usuario. Dos reglas de negocio se aplican de forma centralizada:

1. Las personas SIEMPRE se muestran como "Nombre Apellido", nunca por username.
2. El estado operativo que ve el usuario (Disponible / Asignado / En
   Mantenimiento / Dado de Baja) se DERIVA de `estado` + `usuario_asignado`;
   no requiere migración ni cambios en el modelo.
"""

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


# =============================================================================
# Costos
# =============================================================================

@register.filter(name='sum_costo')
def sum_costo(queryset):
    """Suma el costo total de mantenimientos"""
    try:
        return sum(m.costo for m in queryset)
    except (TypeError, AttributeError):
        return 0


# =============================================================================
# Personas
# =============================================================================

@register.filter(name='nombre_completo')
def nombre_completo(user, vacio='Sin asignar'):
    """Nombre y Apellido de la persona. Nunca expone el username si hay nombre.

    Si el usuario no tiene nombre ni apellido cargados, se cae al username como
    último recurso: es preferible mostrar un identificador legible a dejar la
    celda vacía. Ese caso es un problema de calidad de datos, no de interfaz.
    """
    if not user:
        return vacio
    nombre = (getattr(user, 'get_full_name', lambda: '')() or '').strip()
    return nombre or getattr(user, 'username', vacio)


@register.filter(name='iniciales')
def iniciales(valor):
    """Iniciales para el avatar: 'Ricardo Goitia' -> 'RG'."""
    if hasattr(valor, 'get_full_name'):
        valor = nombre_completo(valor, vacio='')
    partes = [p for p in str(valor or '').strip().split() if p]
    if not partes:
        return '??'
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


@register.filter(name='tono_avatar')
def tono_avatar(valor):
    """Índice 0-7 estable por persona, para pintar siempre el mismo pastel.

    Replica el algoritmo de activos-ui.js para que el avatar generado en el
    cliente (drawer) coincida con el renderizado en el servidor (tabla).
    """
    if hasattr(valor, 'get_full_name'):
        valor = nombre_completo(valor, vacio='')
    texto = str(valor or '')
    h = 0
    for ch in texto:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h % 8


# =============================================================================
# Estado operativo (derivado)
# =============================================================================

#: Contrato único de estados visibles. Cualquier plantilla que necesite pintar
#: un estado pasa por aquí, de modo que color y etiqueta nunca divergen.
ESTADOS_UI = {
    'disponible': {
        'label': 'Disponible',
        'icono': 'bi-box-seam',
        'ayuda': 'En inventario, sin responsable asignado. Listo para entregar.',
    },
    'asignado': {
        'label': 'Asignado',
        'icono': 'bi-person-check',
        'ayuda': 'Bajo la responsabilidad de una persona.',
    },
    'mantenimiento': {
        'label': 'En Mantenimiento',
        'icono': 'bi-tools',
        'ayuda': 'Fuera de servicio temporalmente. No debería reasignarse.',
    },
    'baja': {
        'label': 'Dado de Baja',
        'icono': 'bi-archive',
        'ayuda': 'Retirado del inventario operativo.',
    },
}


@register.filter(name='estado_key')
def estado_key(activo):
    """Traduce (estado, usuario_asignado) al estado operativo de la interfaz."""
    estado = getattr(activo, 'estado', None)
    if estado == 'EM':
        return 'mantenimiento'
    if estado == 'IN':
        return 'baja'
    return 'asignado' if getattr(activo, 'usuario_asignado_id', None) else 'disponible'


@register.filter(name='estado_label')
def estado_label(activo):
    return ESTADOS_UI[estado_key(activo)]['label']


@register.inclusion_tag('activos/includes/estado_badge.html')
def badge_estado(activo, tamano='', sobre_hero=False):
    """Badge de estado reutilizable. Uso: {% badge_estado activo %}"""
    key = estado_key(activo)
    datos = ESTADOS_UI[key]
    return {
        'key': key,
        'label': datos['label'],
        'icono': datos['icono'],
        'ayuda': datos['ayuda'],
        'tamano': tamano,
        'sobre_hero': sobre_hero,
    }


# =============================================================================
# Tipo de activo -> icono
# =============================================================================

#: El orden importa: la primera palabra clave que aparezca gana.
_ICONOS_TIPO = (
    (('laptop', 'portatil', 'portátil', 'notebook'), 'bi-laptop'),
    (('desktop', 'cpu', 'torre', 'computador', 'computadora', 'pc'), 'bi-pc-display'),
    (('monitor', 'pantalla', 'display'), 'bi-display'),
    (('impresora', 'printer', 'multifuncional'), 'bi-printer'),
    (('escaner', 'escáner', 'scanner'), 'bi-upc-scan'),
    (('servidor', 'server', 'nas', 'rack'), 'bi-hdd-rack'),
    (('router', 'switch', 'firewall', 'access point', 'modem'), 'bi-router'),
    (('telefono', 'teléfono', 'celular', 'movil', 'móvil', 'smartphone'), 'bi-phone'),
    (('tablet', 'ipad'), 'bi-tablet'),
    (('teclado', 'keyboard'), 'bi-keyboard'),
    (('mouse', 'raton', 'ratón'), 'bi-mouse'),
    (('camara', 'cámara', 'webcam'), 'bi-camera-video'),
    (('proyector', 'videobeam'), 'bi-projector'),
    (('disco', 'almacenamiento', 'usb', 'memoria'), 'bi-device-hdd'),
    (('ups', 'bateria', 'batería', 'regulador'), 'bi-battery-charging'),
    (('ambulancia',), 'bi-truck-front'),
    (('vehiculo', 'vehículo', 'camion', 'camión', 'carro', 'moto'), 'bi-truck'),
    (('silla', 'mesa', 'archivador', 'mobiliario', 'escritorio'), 'bi-shop'),
    (('herramienta', 'taladro'), 'bi-wrench-adjustable'),
)


@register.filter(name='icono_activo')
def icono_activo(activo):
    """Icono Bootstrap según el tipo (subcategoría/categoría) del activo."""
    if hasattr(activo, 'subcategoria'):
        sub = activo.subcategoria
        texto = '{} {}'.format(
            getattr(sub, 'nombre', ''),
            getattr(getattr(sub, 'categoria', None), 'nombre', ''),
        )
    else:
        texto = str(activo or '')

    texto = texto.lower()
    for claves, icono in _ICONOS_TIPO:
        if any(clave in texto for clave in claves):
            return icono
    return 'bi-box-seam'


# =============================================================================
# Utilidades de URL y métricas
# =============================================================================

@register.simple_tag(takes_context=True)
def query_params(context, **kwargs):
    """Reconstruye el querystring actual aplicando cambios.

    Uso: <a href="{% query_params estado='EM' %}">  → conserva búsqueda,
    categoría, etc. y descarta `page` (cambiar un filtro vuelve a la página 1).
    Pasar None o '' elimina el parámetro.
    """
    request = context.get('request')
    if request is None:
        return mark_safe('?')

    params = request.GET.copy()
    for clave, valor in kwargs.items():
        if valor in (None, '', 'None'):
            params.pop(clave, None)
        else:
            params[clave] = valor

    if any(clave != 'page' for clave in kwargs):
        params.pop('page', None)

    codificado = params.urlencode()
    return mark_safe('?{}'.format(codificado) if codificado else '?')


@register.simple_tag(takes_context=True)
def quitar_filtro(context, param):
    """Querystring actual sin el parámetro indicado. Para las píldoras 'quitar'."""
    request = context.get('request')
    if request is None:
        return mark_safe('?')

    params = request.GET.copy()
    params.pop(param, None)
    params.pop('page', None)
    codificado = params.urlencode()
    return mark_safe('?{}'.format(codificado) if codificado else '?')


@register.simple_tag(takes_context=True)
def filtro_activo(context, clave, valor):
    """'is-active' si el parámetro GET `clave` vale `valor`. Para los chips."""
    request = context.get('request')
    if not request:
        return ''
    return 'is-active' if request.GET.get(clave, '') == str(valor) else ''


@register.simple_tag(takes_context=True)
def chip_activo(context, estado='', asignacion=''):
    """'is-active' para los chips de estado, que combinan dos parámetros."""
    request = context.get('request')
    if not request:
        return ''
    coincide = (
        request.GET.get('estado', '') == estado
        and request.GET.get('asignacion', '') == asignacion
    )
    return 'is-active' if coincide else ''


def _porcentaje(valor, total):
    try:
        total = float(total)
        if total <= 0:
            return 0.0
        return min(100.0, max(0.0, round(float(valor) / total * 100, 1)))
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


@register.filter(name='porcentaje')
def porcentaje(valor, total):
    """Porcentaje acotado a [0, 100] para MOSTRAR al usuario.

    Se devuelve como número, así que Django lo localiza: en español se lee
    "6,8". Correcto en pantalla, inválido dentro de una regla CSS.
    """
    return _porcentaje(valor, total)


@register.filter(name='porcentaje_css')
def porcentaje_css(valor, total):
    """Mismo porcentaje, pero como cadena con punto decimal.

    Imprescindible para `style="width:{{ x|porcentaje_css:y }}%"`: con la
    localización activa un float se imprime "6,8" y el navegador descarta la
    declaración entera, dejando la barra a cero. Al devolver una cadena, Django
    no la localiza.
    """
    return '{:.1f}'.format(_porcentaje(valor, total))
