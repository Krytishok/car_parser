import time
import random
from django.utils import timezone
from .parser import AuctionParser
from .models import ParserLog
import threading


class MultiPageParser:
    def __init__(self):
        self.parser = AuctionParser()
        self.base_url = "https://japantransit.ru/auctions/?sortstat=AUCTION_DATE+asc&page={}"
        self.delay_between_pages = 3  # секунды между страницами
        self.delay_variation = 2  # ± секунды для случайной задержки
        self.max_pages = 50  # максимальное количество страниц для парсинга

    def run_multi_page_parser(self, start_page=1, end_page=None, parser_log=None):
        """
        Запускает парсинг нескольких страниц
        """
        try:
            if not parser_log:
                # Создаем новый лог если не передан
                parser_log = ParserLog.objects.create(
                    url=f"Многостраничный парсинг с {start_page}",
                    status='running'
                )

            total_cars = 0
            total_images = 0
            successful_pages = 0

            if end_page is None:
                # Будем парсить пока не получим пустой результат или не достигнем max_pages
                current_page = start_page
                empty_page_count = 0

                while current_page <= (start_page + self.max_pages - 1):
                    url = self.base_url.format(current_page)
                    print(f"\n=== Страница {current_page} ===")
                    print(f"URL: {url}")

                    # Выполняем парсинг страницы
                    page_cars, page_images = self.parse_single_page(url, parser_log)

                    if page_cars == 0 and page_images == 0:
                        empty_page_count += 1
                        print(f"Страница {current_page} пустая")

                        # Если 3 пустых страницы подряд - останавливаемся
                        if empty_page_count >= 3:
                            print("Найдено 3 пустых страницы подряд. Завершаем парсинг.")
                            break
                    else:
                        empty_page_count = 0
                        total_cars += page_cars
                        total_images += page_images
                        successful_pages += 1
                        print(f"Страница {current_page}: {page_cars} авто, {page_images} изображений")

                    # Случайная задержка между страницами
                    if current_page < (start_page + self.max_pages - 1):
                        delay = self.delay_between_pages + random.uniform(
                            -self.delay_variation, self.delay_variation
                        )
                        delay = max(1, delay)  # Минимум 1 секунда
                        print(f"Пауза {delay:.1f} сек...")
                        time.sleep(delay)

                    current_page += 1
            else:
                # Парсим конкретный диапазон страниц
                for page in range(start_page, end_page + 1):
                    url = self.base_url.format(page)
                    print(f"\n=== Страница {page} ===")
                    print(f"URL: {url}")

                    page_cars, page_images = self.parse_single_page(url, parser_log)

                    if page_cars == 0 and page_images == 0:
                        print(f"Страница {page} пустая, пропускаем...")
                    else:
                        total_cars += page_cars
                        total_images += page_images
                        successful_pages += 1
                        print(f"Страница {page}: {page_cars} авто, {page_images} изображений")

                    # Случайная задержка между страницами
                    if page < end_page:
                        delay = self.delay_between_pages + random.uniform(
                            -self.delay_variation, self.delay_variation
                        )
                        delay = max(1, delay)
                        print(f"Пауза {delay:.1f} сек...")
                        time.sleep(delay)

            # Обновляем лог
            parser_log.mark_completed(total_cars, total_images)

            print(f"\n=== ПАРСИНГ ЗАВЕРШЕН ===")
            print(f"Обработано страниц: {successful_pages}")
            print(f"Всего автомобилей: {total_cars}")
            print(f"Всего изображений: {total_images}")

            return total_cars, total_images, successful_pages

        except Exception as e:
            print(f"Ошибка при многостраничном парсинге: {e}")
            if parser_log:
                parser_log.mark_error(str(e))
            return 0, 0, 0

    def parse_single_page(self, url, parser_log):
        """
        Парсит одну страницу
        """
        try:
            # Получаем HTML
            html_content = self.parser.fetch_html(url)
            if not html_content:
                print(f"Не удалось получить HTML с {url}")
                return 0, 0

            # Парсим данные
            cars_data = self.parser.parse_car_data(html_content)

            if not cars_data:
                print(f"Не найдено данных на странице {url}")
                return 0, 0

            # Сохраняем в базу данных
            cars_count, images_count = self.parser.save_to_database(cars_data)

            return cars_count, images_count

        except Exception as e:
            print(f"Ошибка при парсинге страницы {url}: {e}")
            return 0, 0

    def run_in_thread(self, start_page=1, end_page=None, log_id=None):
        """
        Запускает парсинг в отдельном потоке
        """
        if log_id:
            parser_log = ParserLog.objects.get(id=log_id)
        else:
            parser_log = ParserLog.objects.create(
                url=f"Многостраничный парсинг (страницы {start_page}-{end_page or 'auto'})",
                status='running'
            )

        thread = threading.Thread(
            target=self.run_multi_page_parser,
            args=(start_page, end_page, parser_log)
        )
        thread.daemon = True
        thread.start()

        return parser_log.id