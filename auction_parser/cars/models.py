from django.db import models


class Car(models.Model):
    brand = models.CharField("Марка", max_length=100)
    model = models.CharField("Модель", max_length=100)
    year = models.PositiveIntegerField("Год выпуска")
    price = models.IntegerField("Цена", null=True, blank=True)
    mileage = models.IntegerField("Пробег", null=True, blank=True)
    lot_number = models.CharField("Номер лота", max_length=50, null=True, blank=True)
    lot_url = models.TextField("URL Объявления", null=True, blank=True)
    engine_volume = models.CharField("Объем двигателя", max_length=50, null=True, blank=True)
    auction_date = models.CharField("Дата аукциона", max_length=50, null=True, blank=True)
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)

    def __str__(self):
        return f"{self.brand} {self.model} ({self.year})"

    class Meta:
        verbose_name = "Автомобиль"
        verbose_name_plural = "Автомобили"
        ordering = ['-year', 'brand', 'model']


class Image(models.Model):
    car = models.ForeignKey(
        Car,
        on_delete=models.CASCADE,
        related_name='images',
        verbose_name="Автомобиль"
    )
    url = models.URLField("URL изображения", max_length=500)

    def __str__(self):
        return f"Изображение для {self.car}"

    class Meta:
        verbose_name = "Изображение"
        verbose_name_plural = "Изображения"


class ParserLog(models.Model):
    STATUS_CHOICES = [
        ('running', 'Выполняется'),
        ('completed', 'Завершен'),
        ('error', 'Ошибка'),
    ]

    url = models.URLField("URL для парсинга", max_length=500)
    cars_parsed = models.IntegerField("Спарсено автомобилей", default=0)
    images_parsed = models.IntegerField("Спарсено изображений", default=0)
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default='running')
    error_message = models.TextField("Сообщение об ошибке", blank=True, null=True)
    created_at = models.DateTimeField("Дата запуска", auto_now_add=True)
    finished_at = models.DateTimeField("Дата завершения", null=True, blank=True)

    def __str__(self):
        return f"Парсинг {self.url} - {self.status}"

    def mark_completed(self, cars_count=0, images_count=0):
        """Отметить парсинг как завершенный"""
        from django.utils import timezone
        self.status = 'completed'
        self.cars_parsed = cars_count
        self.images_parsed = images_count
        self.finished_at = timezone.now()
        self.save()

    def mark_error(self, error_message):
        """Отметить парсинг как завершенный с ошибкой"""
        from django.utils import timezone
        self.status = 'error'
        self.error_message = str(error_message)
        self.finished_at = timezone.now()
        self.save()

    class Meta:
        verbose_name = "Лог парсинга"
        verbose_name_plural = "Логи парсинга"