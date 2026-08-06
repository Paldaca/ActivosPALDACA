"""
Compatibilidad: la lógica vive en reportes.services.
Este módulo reexporta lo mínimo por si quedan imports antiguos.
"""

from .services.excel import exportar_activos_excel as generar_excel_activos
from .services.excel import nombre_usuario as _nombre_usuario
from .services.filtros import filtros_desde_request as obtener_filtros_aplicados
from .services.pdf import formatear_fecha, generar_pdf

__all__ = [
    "formatear_fecha",
    "generar_excel_activos",
    "generar_pdf",
    "obtener_filtros_aplicados",
    "_nombre_usuario",
]
