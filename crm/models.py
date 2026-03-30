from django.db import models


class Market(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Маркет")

    def __str__(self):
        return self.name

class Pair(models.Model):
    market = models.ForeignKey(Market, on_delete=models.CASCADE)
    symbol = models.CharField(max_length=20, verbose_name="Пара")
    price = models.DecimalField(max_digits=12, decimal_places=5, verbose_name="Цена", null=True, blank=True)

    def __str__(self):
        return self.symbol

class Expiration(models.Model):
    label = models.CharField(max_length=50, unique=True, verbose_name="Отрезок времени")

    def __str__(self):
        return self.label