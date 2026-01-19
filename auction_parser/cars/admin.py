from django.contrib import admin
from .models import Car, Image, ParserLog

@admin.register(Car)
class CarAdmin(admin.ModelAdmin):
    list_display = ['brand', 'model', 'year', 'price', 'mileage', 'lot_number']
    list_filter = ['brand', 'year', 'created_at']
    search_fields = ['brand', 'model', 'lot_number']
    readonly_fields = ['created_at']

@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ['car', 'url']
    list_filter = ['car__brand']
    search_fields = ['car__brand', 'car__model', 'url']

@admin.register(ParserLog)
class ParserLogAdmin(admin.ModelAdmin):
    list_display = ['url', 'status', 'cars_parsed', 'images_parsed', 'created_at']
    list_filter = ['status', 'created_at']
    readonly_fields = ['created_at', 'finished_at']
    search_fields = ['url']