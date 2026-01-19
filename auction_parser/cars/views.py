from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView
from django.contrib import messages
from django.utils import timezone
import threading
from .models import (ParserLog, Car, Image)
from .parser import AuctionParser
from .run_parse import MultiPageParser  # Импортируем новый класс

from django.db.models import Q
from django.core.paginator import Paginator
import json


class CarsAjaxView(View):
    """AJAX view для загрузки автомобилей с фильтрацией"""

    def get(self, request):
        try:
            # Получаем параметры фильтрации
            search = request.GET.get('search', '').strip()
            brand = request.GET.get('brand', '').strip()
            year_from = request.GET.get('year_from', '').strip()
            year_to = request.GET.get('year_to', '').strip()
            price_from = request.GET.get('price_from', '').strip()
            price_to = request.GET.get('price_to', '').strip()
            mileage_from = request.GET.get('mileage_from', '').strip()
            mileage_to = request.GET.get('mileage_to', '').strip()
            sort = request.GET.get('sort', '-created_at')
            page = int(request.GET.get('page', 1))
            per_page = int(request.GET.get('per_page', 50))

            # Начинаем с базового QuerySet
            cars_qs = Car.objects.select_related().prefetch_related('images').all()

            # Применяем фильтры
            if search:
                cars_qs = cars_qs.filter(
                    Q(brand__icontains=search) |
                    Q(model__icontains=search) |
                    Q(lot_number__icontains=search)
                )

            if brand:
                cars_qs = cars_qs.filter(brand=brand)

            if year_from:
                cars_qs = cars_qs.filter(year__gte=int(year_from))
            if year_to:
                cars_qs = cars_qs.filter(year__lte=int(year_to))

            if price_from:
                cars_qs = cars_qs.filter(price__gte=int(price_from))
            if price_to:
                cars_qs = cars_qs.filter(price__lte=int(price_to))

            if mileage_from:
                cars_qs = cars_qs.filter(mileage__gte=int(mileage_from))
            if mileage_to:
                cars_qs = cars_qs.filter(mileage__lte=int(mileage_to))

            # Применяем сортировку
            cars_qs = cars_qs.order_by(sort)

            # Пагинация
            paginator = Paginator(cars_qs, per_page)

            try:
                cars_page = paginator.page(page)
            except:
                cars_page = paginator.page(1)

            # Подготавливаем данные для JSON
            cars_data = []
            for car in cars_page:
                car_dict = {
                    'id': car.id,
                    'brand': car.brand,
                    'model': car.model,
                    'year': car.year,
                    'price': car.price,
                    'mileage': car.mileage,
                    'lot_number': car.lot_number,
                    'engine_volume': car.engine_volume,
                    'auction_date': car.auction_date,
                    'lot_url': car.lot_url,
                    'created_at': car.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'images': [
                        {'url': image.url}
                        for image in car.images.all()[:3]  # Берем первые 3 изображения
                    ]
                }
                cars_data.append(car_dict)

            response_data = {
                'success': True,
                'cars': cars_data,
                'page': cars_page.number,
                'total_pages': paginator.num_pages,
                'total_count': paginator.count,
                'has_previous': cars_page.has_previous(),
                'has_next': cars_page.has_next(),
            }

            return JsonResponse(response_data, safe=False)

        except Exception as e:
            print(f"Ошибка в CarsAjaxView: {e}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            })


class ParserView(TemplateView):
    template_name = 'parser.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['recent_logs'] = ParserLog.objects.all().order_by('-created_at')[:10]
        context['total_cars'] = Car.objects.count()
        context['total_images'] = Image.objects.count()

        # Только статистика, автомобили будут загружаться через AJAX
        context['recent_cars_count'] = Car.objects.filter(
            created_at__gte=timezone.now() - timezone.timedelta(days=7)
        ).count()

        # Добавляем список уникальных марок для фильтра
        context['brands'] = Car.objects.exclude(brand='').values_list('brand', flat=True).distinct().order_by('brand')

        return context


class StartParserView(View):
    def post(self, request):
        url = request.POST.get('url', '').strip()

        if not url:
            messages.error(request, 'Пожалуйста, введите URL для парсинга')
            return redirect('parser_view')

        # Создаем запись в логе
        parser_log = ParserLog.objects.create(url=url)

        # Запускаем парсер в отдельном потоке
        thread = threading.Thread(
            target=self.run_parser_in_thread,
            args=(url, parser_log.id)
        )
        thread.daemon = True
        thread.start()

        messages.success(request, f'Парсинг запущен для URL: {url}')
        return redirect('parser_view')

    def run_parser_in_thread(self, url, log_id):
        """Запуск парсера в отдельном потоке"""
        try:
            parser_log = ParserLog.objects.get(id=log_id)
            parser = AuctionParser()
            parser.run_parser(url, parser_log)
        except Exception as e:
            # Обновляем лог с ошибкой
            try:
                parser_log = ParserLog.objects.get(id=log_id)
                parser_log.mark_error(str(e))
            except ParserLog.DoesNotExist:
                pass

            # Логируем ошибку
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка в потоке парсера: {e}")


class StartMultiPageParserView(View):
    """Запуск многостраничного парсера"""

    def post(self, request):
        start_page = request.POST.get('start_page', '1').strip()
        end_page = request.POST.get('end_page', '').strip()

        try:
            start_page = int(start_page)
            if start_page < 1:
                start_page = 1
        except ValueError:
            start_page = 1

        if end_page:
            try:
                end_page = int(end_page)
                if end_page < start_page:
                    end_page = start_page
                # Ограничиваем максимум 50 страниц за раз
                if end_page > start_page + 49:
                    end_page = start_page + 49
            except ValueError:
                end_page = None
        else:
            end_page = None

        # Создаем лог
        if end_page:
            url_text = f"Парсинг страниц {start_page}-{end_page}"
        else:
            url_text = f"Парсинг с страницы {start_page}"

        parser_log = ParserLog.objects.create(url=url_text)

        # Запускаем многостраничный парсер в отдельном потоке
        multi_parser = MultiPageParser()
        log_id = multi_parser.run_in_thread(start_page, end_page, parser_log.id)

        if end_page:
            message = f'Запущен многостраничный парсинг: страницы {start_page}-{end_page}'
        else:
            message = f'Запущен многостраничный парсинг начиная со страницы {start_page}'

        messages.success(request, message)
        return redirect('parser_view')


class StopParserView(View):
    """Остановка всех активных парсеров"""

    def post(self, request):
        # Находим все запущенные парсеры
        running_logs = ParserLog.objects.filter(status='running')
        stopped_count = 0

        for log in running_logs:
            log.status = 'stopped'
            log.finished_at = timezone.now()
            log.error_message = 'Остановлен пользователем'
            log.save()
            stopped_count += 1

        if stopped_count > 0:
            messages.success(request, f'Остановлено {stopped_count} активных парсеров')
        else:
            messages.info(request, 'Нет активных парсеров для остановки')

        return redirect('parser_view')


class ParserStatusView(View):
    def get(self, request):
        """API для получения статуса парсера"""
        try:
            # Ищем сначала запущенные парсеры, потом последние завершенные
            recent_log = ParserLog.objects.filter(status='running').first()
            if not recent_log:
                recent_log = ParserLog.objects.order_by('-created_at').first()

            if recent_log:
                data = {
                    'status': recent_log.status,
                    'status_display': recent_log.get_status_display(),
                    'cars_parsed': recent_log.cars_parsed,
                    'images_parsed': recent_log.images_parsed,
                    'created_at': recent_log.created_at.strftime('%d.%m.%Y %H:%M'),
                    'url': recent_log.url,
                }
                if recent_log.finished_at:
                    data['finished_at'] = recent_log.finished_at.strftime('%d.%m.%Y %H:%M')
                if recent_log.error_message:
                    data['error_message'] = recent_log.error_message
            else:
                data = {'status': 'no_data'}

            return JsonResponse(data)

        except Exception as e:
            print(f"Ошибка в ParserStatusView: {e}")
            return JsonResponse({'status': 'error', 'error_message': str(e)})


class ClearDataView(View):
    def post(self, request):
        """Очистка всех данных"""
        try:
            cars_count = Car.objects.count()
            images_count = Image.objects.count()
            logs_count = ParserLog.objects.count()

            Image.objects.all().delete()
            Car.objects.all().delete()
            ParserLog.objects.all().delete()

            messages.success(request,
                             f'Данные очищены. Удалено: {cars_count} автомобилей, {images_count} изображений, {logs_count} логов')
        except Exception as e:
            messages.error(request, f'Ошибка при очистке данных: {str(e)}')

        return redirect('parser_view')