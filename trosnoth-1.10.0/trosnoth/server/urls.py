from django.conf.urls import include, url
from django.contrib import admin

urlpatterns = [
    url(r'^', include('trosnoth.djangoapp.urls', namespace='trosnoth')),
    url(r'^admin/', include(admin.site.urls)),
]
