from django.urls import path
from . import views

urlpatterns = [
    path('', views.ParserView.as_view(), name='parser_view'),
    path('parser/start/', views.StartParserView.as_view(), name='start_parser'),
    path('parser/multi-start/', views.StartMultiPageParserView.as_view(), name='multi_start_parser'),
    path('parser/stop/', views.StopParserView.as_view(), name='stop_parser'),
    path('parser/status/', views.ParserStatusView.as_view(), name='parser_status'),
    path('parser/clear/', views.ClearDataView.as_view(), name='clear_data'),
    path('cars/ajax/', views.CarsAjaxView.as_view(), name='cars_ajax'),  # Новый URL
]