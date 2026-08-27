"""
URL configuration for SSAPI project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve as media_serve

from activos.views_etiquetas import etiqueta_alta
from activos.views_publicos import etiqueta_publica


def healthz(_request):
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path('healthz/', healthz, name='healthz'),
    path('admin/', admin.site.urls),

    # Ficha publica de una etiqueta QR. Cuelga de la raiz y no de /activos/
    # porque esta URL se imprime dentro del codigo: cada caracter ahorrado baja
    # la densidad del simbolo y lo hace mas legible en un adhesivo de 25 mm.
    # Sin app_name ni namespace, por lo mismo.
    path('q/<str:token>/', etiqueta_publica, name='etiqueta-publica'),
    # El alta cuelga de /q/ (y no de /activos/) para heredar esa exclusion:
    # se llega escaneando desde el movil y no debe acabar dentro del iframe.
    path('q/<str:token>/alta/', etiqueta_alta, name='etiqueta-alta'),

    path('', include('core.urls')),
    path('activos/', include('activos.urls')),
    path('mantenimientos/', include('mantenimientos.urls')),
    path('reportes/', include('reportes.urls')),
    path('usuarios/', include('usuarios.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    urlpatterns += [
        re_path(
            r'^media/(?P<path>.*)$',
            media_serve,
            {'document_root': settings.MEDIA_ROOT},
        ),
    ]
