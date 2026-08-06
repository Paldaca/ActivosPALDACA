"""Generación de PDF institucional con ReportLab."""

import io
import os

from django.conf import settings
from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, inch
from reportlab.platypus import HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def formatear_fecha(fecha) -> str:
    if not fecha:
        return ""
    meses = (
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    )
    return f"{fecha.day} de {meses[fecha.month - 1]} de {fecha.year}"


def _nombre_usuario(usuario) -> str:
    if not usuario:
        return "Sin asignar"
    nombre = f"{usuario.first_name or ''} {usuario.last_name or ''}".strip()
    return nombre or (usuario.email or "Sin asignar")


def generar_pdf(template_name, context, filename):
    """
    Genera un PDF institucional con ReportLab.

    `template_name` se conserva por compatibilidad con la API previa
    (los HTML en reportes/templates/ son referencia de diseño).
    """
    del template_name

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=3 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "InstitutionalTitle",
        parent=styles["Heading1"],
        fontSize=20,
        spaceAfter=20,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#32407b"),
        fontName="Helvetica-Bold",
    )
    subtitle_style = ParagraphStyle(
        "InstitutionalSubtitle",
        parent=styles["Heading2"],
        fontSize=14,
        spaceAfter=15,
        textColor=colors.HexColor("#32407b"),
        fontName="Helvetica-Bold",
    )
    normal_style = ParagraphStyle(
        "InstitutionalNormal",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=6,
        fontName="Helvetica",
    )
    info_style = ParagraphStyle(
        "ReportInfo",
        parent=styles["Normal"],
        fontSize=9,
        spaceAfter=4,
        fontName="Helvetica",
    )

    story = []
    story.extend(crear_encabezado_institucional())
    story.append(Spacer(1, 20))

    es_nota_entrega = "fecha_entrega" in context or bool(context.get("responsable_entrega"))
    if es_nota_entrega:
        story.append(Paragraph("NOTA DE ENTREGA DE ACTIVOS", title_style))
    else:
        story.append(Paragraph("REPORTE DE ACTIVOS", title_style))

    story.append(Spacer(1, 15))
    story.append(crear_informacion_reporte(context, info_style))
    story.append(Spacer(1, 20))

    if context.get("activos"):
        story.append(crear_tabla_activos(context["activos"]))
        story.append(Spacer(1, 20))

    if es_nota_entrega:
        story.extend(crear_seccion_firmas(context, subtitle_style))

    story.append(crear_pie_pagina(context, normal_style))
    doc.build(story)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def crear_encabezado_institucional():
    logo_path = os.path.join(
        settings.BASE_DIR, "core", "static", "core", "img", "logo_paldaca.png"
    )
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=2 * inch, height=0.8 * inch)
    else:
        logo = Paragraph(
            '<font color="#32407b"><b>PALDACA</b></font>',
            ParagraphStyle("LogoFallback", fontSize=14, alignment=TA_CENTER),
        )

    empresa_text = (
        '<font color="#32407b" size="12"><b>CONSORCIO PALDACA</b></font><br/>'
        '<font color="#32407b" size="12"><b>Sistema de Gestión de Activos</b></font><br/>'
        '<font color="#32407b" size="12"><b>Reporte Institucional</b></font>'
    )
    empresa_paragraph = Paragraph(
        empresa_text, ParagraphStyle("EmpresaInfo", alignment=TA_RIGHT)
    )

    header_table = Table([[logo, empresa_paragraph]], colWidths=[3 * inch, 3 * inch])
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return [
        header_table,
        HRFlowable(width="100%", thickness=2, color=colors.HexColor("#32407b")),
    ]


def crear_informacion_reporte(context, info_style):
    del info_style
    fecha = context.get("fecha_entrega") or context.get("fecha_generacion", "")
    info_data = [
        ["Fecha de generación:", fecha],
        ["Total de activos:", str(len(context.get("activos", [])))],
    ]
    if context.get("responsable_entrega"):
        info_data.append(["Responsable de entrega:", context["responsable_entrega"]])
    if context.get("observaciones"):
        info_data.append(["Observaciones:", context["observaciones"]])
    if context.get("filtros_aplicados"):
        info_data.append(["Filtros aplicados:", context["filtros_aplicados"]])

    info_table = Table(info_data, colWidths=[2.5 * inch, 3.5 * inch])
    info_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8f9fa")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("ALIGN", (1, 0), (1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (1, 0), (1, -1), colors.white),
                ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#dee2e6")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return info_table


def crear_tabla_activos(activos):
    headers = [
        "Código",
        "Categoría",
        "Marca",
        "Modelo",
        "Serial",
        "Ubicación",
        "Estado",
        "Usuario",
    ]
    table_data = [headers]
    for activo in activos:
        table_data.append(
            [
                activo.codigo_inventario,
                f"{activo.subcategoria.nombre}",
                activo.marca,
                activo.modelo,
                activo.numero_serial or "N/A",
                activo.ubicacion.nombre,
                activo.get_estado_display(),
                _nombre_usuario(activo.usuario_asignado),
            ]
        )

    activos_table = Table(
        table_data,
        colWidths=[
            0.9 * inch,
            0.9 * inch,
            0.5 * inch,
            1.1 * inch,
            0.8 * inch,
            1.0 * inch,
            1.0 * inch,
            0.8 * inch,
        ],
    )
    activos_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#32407b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f8f9fa")],
                ),
                ("TOPPADDING", (0, 1), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
            ]
        )
    )
    return activos_table


def crear_seccion_firmas(context, subtitle_style):
    story = [
        Paragraph("FIRMAS DE ENTREGA Y RECEPCIÓN", subtitle_style),
        Spacer(1, 20),
    ]
    signature_data = [
        ["ENTREGA", "RECEPCIÓN"],
        ["", ""],
        ["Responsable:", "Recibe:"],
        [context.get("responsable_entrega") or "", "_____________________"],
        ["", ""],
        ["Firma y sello:", "Firma y sello:"],
        ["", ""],
        ["", ""],
        ["", ""],
        ["Fecha: _______________", "Fecha: _______________"],
    ]
    signature_table = Table(signature_data, colWidths=[3 * inch, 3 * inch])
    signature_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#32407b")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("MINROWHEIGHT", (0, 0), (-1, -1), 25),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8f9fa")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#32407b")),
            ]
        )
    )
    story.append(signature_table)
    return story


def crear_pie_pagina(context, normal_style):
    del normal_style
    fecha = context.get("fecha_entrega") or context.get("fecha_generacion", "")
    footer_text = f"""
    <para align="center">
    <font size="8" color="#666666">
    Este documento fue generado automáticamente por el Sistema de Gestión de Activos de Consorcio PALDACA<br/>
    Fecha: {fecha} | Total de registros: {len(context.get('activos', []))}
    </font>
    </para>
    """
    return Paragraph(footer_text, ParagraphStyle("Footer", fontSize=8))
