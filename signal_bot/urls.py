"""
URL configuration for signal_bot project.

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
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from crm import views


urlpatterns = [
    path('admin/', admin.site.urls),
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
    # Pocket Option (оригинальный URL — обратная совместимость)
    path("postback/", views.postback_view, name="postback"),
    # платформо-специфичные эндпоинты
    path("postback/pocket/", views.postback_pocket_view, name="postback_pocket"),
    path("postback/binarium/", views.postback_binarium_view, name="postback_binarium"),
]
