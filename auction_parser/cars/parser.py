import os
import json
import requests
from bs4 import BeautifulSoup
import re
from django.utils import timezone
from django.conf import settings
from .models import Car, Image, ParserLog


class AuctionParser:
    def __init__(self):
        self.session = requests.Session()
        self.setup_headers()

    def setup_headers(self):
        """Настройка заголовков для обхода защиты"""
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })

    def run_parser(self, url, parser_log):
        """
        Основной метод парсинга
        """
        try:
            # Получаем HTML
            html_content = self.fetch_html(url)
            if not html_content:
                parser_log.mark_error("Не удалось получить HTML содержимое")
                return

            # Парсим данные
            cars_data = self.parse_car_data(html_content)

            if not cars_data:
                parser_log.mark_error("Не найдено данных об автомобилях")
                return

            # Сохраняем в JSON
            json_filename = self.save_to_json(cars_data, parser_log.id)

            # Сохраняем в базу данных
            cars_count, images_count = self.save_to_database(cars_data)

            # Обновляем лог
            parser_log.mark_completed(cars_count, images_count)

            print(f"Парсинг завершен. Создано: {cars_count} автомобилей, {images_count} изображений")

        except Exception as e:
            parser_log.mark_error(str(e))
            print(f"Ошибка при парсинге: {e}")

    def fetch_html(self, url):
        """
        Получает HTML содержимое по URL
        """
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"Ошибка при получении HTML: {e}")
            return None

    def parse_car_data(self, html_content):
        """
        Парсит HTML и извлекает данные об автомобилях
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        cars = []

        # Находим все блоки с автомобилями
        car_blocks = soup.find_all('div', class_=lambda x: x and 'flex flex-col md:table-row-group' in x)

        print(f"Найдено блоков автомобилей: {len(car_blocks)}")

        for i, block in enumerate(car_blocks):
            print(f"Обрабатываем блок {i + 1}...")
            car_data = self.extract_car_from_block(block)
            if car_data:
                cars.append(car_data)
                print(
                    f"  ✓ Автомобиль: {car_data.get('brand', '')} {car_data.get('model', '')} - Цена: {car_data.get('price', 'не указана')}")

        return cars

    def extract_car_from_block(self, block):
        """
        Извлекает данные об одном автомобиле из блока
        """
        try:
            car = {}

            # Лот номер
            lot_info = block.find('span', class_='font-semibold')
            if lot_info:
                lot_text = lot_info.get_text(strip=True)
                car['lot_number'] = re.sub(r'[^\d]', '', lot_text)

            # Марка и модель
            brand_model_div = block.find('div', class_='mt-1 text-sm font-bold')
            if brand_model_div:
                brand_model_text = brand_model_div.get_text(strip=True)
                car['brand'], car['model'] = self.split_brand_model(brand_model_text)

            # Дата аукциона
            date_div = block.find('div', class_='text-darkblue')
            if date_div:
                car['auction_date'] = date_div.get_text(strip=True)

            # Год выпуска
            year_span = block.find('span', class_='text-red-700')
            if year_span:
                year_text = year_span.get_text(strip=True)
                year_match = re.search(r'\d{4}', year_text)
                if year_match:
                    car['year'] = int(year_match.group())

            # Объем двигателя
            engine_div = block.find('div', string=lambda x: x and 'cc' in str(x))
            if engine_div:
                parent_div = engine_div.parent
                if parent_div:
                    engine_text = parent_div.get_text()
                    engine_match = re.search(r'(\d+)\s*cc', engine_text)
                    if engine_match:
                        car['engine_volume'] = engine_match.group(1) + ' cc'

            # Пробег
            mileage_div = block.find('div', string=lambda x: x and 'км' in str(x))
            if mileage_div:
                mileage_text = mileage_div.get_text(strip=True)
                mileage_match = re.search(r'([\d\s]+)\s*км', mileage_text)
                if mileage_match:
                    mileage_clean = mileage_match.group(1).replace(' ', '')
                    if mileage_clean.isdigit():
                        car['mileage'] = int(mileage_clean)

            # ЦЕНА - УЛУЧШЕННЫЙ ПАРСИНГ
            car['price'] = self.extract_price(block)

            # Ссылка на аукцион
            link = block.find('a', href=lambda x: x and '/auctions/' in x)
            if link:
                href = link.get('href', '')
                if href.startswith('/'):
                    car['lot_url'] = f"https://japantransit.ru{href}"
                else:
                    car['lot_url'] = href

            # Изображения
            images = []
            img_links = block.find_all('a', class_=lambda x: x and 'group h-16 w-20 rounded-md' in x)
            for img_link in img_links:
                style = img_link.get('style', '')
                bg_match = re.search(r"url\('([^']+)'\)", style)
                if bg_match:
                    images.append(bg_match.group(1))

            if images:
                car['images'] = images

            return car

        except Exception as e:
            print(f"Ошибка при парсинге блока: {e}")
            return None

    def extract_price(self, block):
        """
        Парсинг цены для элемента с классом rounded-full shadow-lg shadow-red-800/40
        """
        print("  Поиск цены в блоке...")

        # Ищем конкретный элемент с ценой из вашего примера
        price_element = block.select_one('div.rounded-full.shadow-lg.shadow-red-800\\/40')

        if not price_element:
            # Пробуем другие варианты селектора на случай если классы немного отличаются
            price_element = block.select_one('div.rounded-full.shadow-lg')
            if not price_element:
                price_element = block.select_one('[class*="rounded-full"][class*="shadow-lg"]')

        if price_element:
            price_text = price_element.get_text(strip=True)
            print(f"  Найден элемент цены: '{price_text}'")

            # Обрабатываем &nbsp; и другие специальные символы
            price = self.parse_price_text(price_text)

            if price:
                print(f"  ✓ Цена найдена: {price}")
                return price
            else:
                print(f"  ✗ Не удалось распарсить цену из текста: '{price_text}'")

        # Альтернативный поиск - ищем любые элементы с символом рубля
        ruble_elements = block.find_all(text=re.compile('[₽р]'))
        for element in ruble_elements:
            price_text = element.strip()
            print(f"  Найден элемент с символом рубля: '{price_text}'")
            price = self.parse_price_text(price_text)
            if price:
                print(f"  ✓ Цена найдена через символ рубля: {price}")
                return price

        print("  ✗ Цена не найдена")
        return None

    def parse_price_text(self, price_text):
        """
        Парсит текст цены, обрабатывает все виды пробелов и специальные символы
        """
        if not price_text:
            return None

        print(f"    Парсим текст цены: '{price_text}'")
        print(f"    Длина текста: {len(price_text)}")
        print(f"    Коды символов: {[ord(c) for c in price_text]}")

        # Заменяем ВСЕ виды неразрывных пробелов на обычные
        # Unicode для разных типов неразрывных пробелов:
        # \xa0 - NO-BREAK SPACE (самый распространенный)
        # \u202f - NARROW NO-BREAK SPACE
        # \u2009 - THIN SPACE
        # \u2007 - FIGURE SPACE
        # \u2060 - WORD JOINER

        replacements = {
            '&nbsp;': ' ',
            '\xa0': ' ',  # NO-BREAK SPACE
            '\u202f': ' ',  # NARROW NO-BREAK SPACE
            '\u2009': ' ',  # THIN SPACE
            '\u2007': ' ',  # FIGURE SPACE
            '\u2060': ' ',  # WORD JOINER
            '\u200a': ' ',  # HAIR SPACE
            '\u200b': '',  # ZERO WIDTH SPACE (удаляем)
            '\ufeff': '',  # ZERO WIDTH NO-BREAK SPACE (удаляем)
        }

        clean_text = price_text
        for old, new in replacements.items():
            clean_text = clean_text.replace(old, new)

        print(f"    После замены пробелов: '{clean_text}'")

        # Убираем тильду, приблизительные символы и валюту
        clean_text = re.sub(r'[~≈₽рRUBруб]', '', clean_text, flags=re.IGNORECASE)

        print(f"    После удаления символов: '{clean_text}'")

        # Убираем ВСЕ пробелы
        clean_text = clean_text.replace(' ', '')

        print(f"    Без пробелов: '{clean_text}'")

        if clean_text and clean_text.isdigit():
            price = int(clean_text)
            # Проверяем, что цена реалистичная
            if 10000 <= price <= 1000000000:  # увеличил до 1 млрд
                print(f"    ✓ Валидная цена: {price}")
                return price
            else:
                print(f"    ✗ Цена не в диапазоне: {price}")
        else:
            print(f"    ✗ Нечисловой текст после очистки: '{clean_text}'")

        return None


    def split_brand_model(self, text):
        """
        Разделяет текст на марку и модель
        """
        if not text:
            return "", ""

        # Очищаем текст
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        # Специальные случаи (многословные марки)
        special_cases = {
            'MERCEDES-BENZ': 'MERCEDES-BENZ',
            'LAND ROVER': 'LAND ROVER',
            'ALFA ROMEO': 'ALFA ROMEO',
            'ASTON MARTIN': 'ASTON MARTIN',
        }

        text_upper = text.upper()
        for multi_brand, brand_name in special_cases.items():
            if text_upper.startswith(multi_brand):
                brand = brand_name
                model = text[len(multi_brand):].strip()
                return brand.title(), model

        # Известные марки
        known_brands = [
            'TOYOTA', 'NISSAN', 'HONDA', 'MAZDA', 'SUBARU', 'MITSUBISHI', 'SUZUKI',
            'DAIHATSU', 'ISUZU', 'LEXUS', 'INFINITI', 'ACURA', 'BMW', 'AUDI',
            'VOLKSWAGEN', 'VOLVO', 'FORD', 'CHEVROLET', 'HYUNDAI', 'KIA', 'PEUGEOT',
            'RENAULT', 'FIAT', 'JEEP', 'CHRYSLER', 'DODGE', 'CADILLAC', 'BUICK',
        ]

        for brand in known_brands:
            if text_upper.startswith(brand):
                brand_part = brand
                model_part = text[len(brand):].strip()
                return brand_part.title(), model_part

        # Базовый алгоритм
        words = text.split()
        if len(words) == 0:
            return "", ""
        elif len(words) == 1:
            return words[0], ""
        else:
            brand = words[0]
            model = ' '.join(words[1:])
            model = re.sub(r'^[\s\-–—]+', '', model).strip()
            return brand, model

    def save_to_json(self, cars_data, log_id):
        """
        Сохраняет данные в JSON файл в папке cars/json_results/
        """
        # Получаем путь из настроек
        json_dir = settings.JSON_RESULTS_DIR

        # Создаем папку, если она не существует
        os.makedirs(json_dir, exist_ok=True)

        # Формируем полный путь к файлу
        filename = f'parser_results_{log_id}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json'
        full_path = os.path.join(json_dir, filename)

        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                json.dump(cars_data, f, ensure_ascii=False, indent=2)
            print(f"Данные сохранены в JSON: {full_path}")
            return full_path
        except Exception as e:
            print(f"Ошибка при сохранении JSON: {e}")
            return None

    def save_to_database(self, cars_data):
        """
        Сохраняет данные в базу данных Django
        """
        cars_count = 0
        images_count = 0

        for car_data in cars_data:
            try:
                # Проверяем обязательные поля
                if not car_data.get('brand') or not car_data.get('year'):
                    print(f"  Пропускаем автомобиль без марки или года: {car_data}")
                    continue

                if car_data.get('lot_number'):
                    car, created = Car.objects.get_or_create(
                        lot_number=car_data.get('lot_number'),
                        defaults={
                            'brand': car_data.get('brand', ''),
                            'model': car_data.get('model', ''),
                            'year': car_data.get('year', 0),
                            'price': car_data.get('price'),
                            'mileage': car_data.get('mileage'),
                            'engine_volume': car_data.get('engine_volume'),
                            'auction_date': car_data.get('auction_date'),
                            'lot_url': car_data.get('lot_url'),
                        }
                    )
                else:
                    car = Car.objects.create(
                        brand=car_data.get('brand', ''),
                        model=car_data.get('model', ''),
                        year=car_data.get('year', 0),
                        price=car_data.get('price'),
                        mileage=car_data.get('mileage'),
                        engine_volume=car_data.get('engine_volume'),
                        auction_date=car_data.get('auction_date'),
                        lot_url=car_data.get('lot_url'),
                    )
                    created = True

                if created:
                    cars_count += 1
                    print(f"  Создан автомобиль: {car.brand} {car.model} ({car.year}) - Цена: {car.price}")

                # Сохраняем изображения
                for img_url in car_data.get('images', []):
                    img, img_created = Image.objects.get_or_create(
                        car=car,
                        url=img_url
                    )
                    if img_created:
                        images_count += 1

            except Exception as e:
                print(f"Ошибка при сохранении автомобиля в БД: {e}")
                continue

        return cars_count, images_count