"""Render HTML templates to PDF with xhtml2pdf."""

from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa


def link_callback(uri, rel):
    """Resolve static and media URIs to local files for xhtml2pdf."""
    del rel
    if not uri:
        return uri
    parsed = uri.replace("\\", "/")
    static_url = settings.STATIC_URL or "/static/"
    media_url = settings.MEDIA_URL or "/media/"
    if parsed.startswith(media_url):
        relative = parsed[len(media_url):].lstrip("/")
        return str(Path(settings.MEDIA_ROOT) / relative)
    if parsed.startswith(static_url):
        relative = parsed[len(static_url):].lstrip("/")
        found = finders.find(relative)
        if found:
            return found
        fallback = Path(settings.BASE_DIR) / "core" / "static" / relative
        if fallback.exists():
            return str(fallback)
    return uri


def render_html_pdf_bytes(template_name, context) -> bytes:
    """Return PDF bytes from a Django HTML template."""
    html = render_to_string(template_name, context)
    result = BytesIO()
    pdf = pisa.CreatePDF(
        src=html,
        dest=result,
        encoding="utf-8",
        link_callback=link_callback,
    )
    if pdf.err:
        raise ValueError("No se pudo generar el PDF de la planilla.")
    return result.getvalue()


def render_html_pdf(template_name, context, filename) -> HttpResponse:
    """Return an attachment HttpResponse with the rendered PDF."""
    data = render_html_pdf_bytes(template_name, context)
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )
    return response
