from rest_framework.routers import DefaultRouter

from .viewsets import DocumentoViewSet

router = DefaultRouter()
router.register("documentos", DocumentoViewSet, basename="documento")
urlpatterns = router.urls
