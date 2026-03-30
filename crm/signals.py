from django.db.models.signals import post_migrate
from django.dispatch import receiver
from .models import Market, Pair, Expiration


@receiver(post_migrate)
def init_default_data(sender, **kwargs):
    if not Market.objects.exists():
        Market.objects.bulk_create([
            Market(name="Stock"),
            Market(name="OTC"),
        ])

    if not Expiration.objects.exists():
        Expiration.objects.bulk_create([
            Expiration(label="1 minute"),
            Expiration(label="5 minutes"),
            Expiration(label="20 minutes"),
        ])

    if not Pair.objects.exists():
        PAIRS_LIST = [
            ("AUD/CAD", "Stock"),
            ("AUD/CHF", "Stock"),
            ("AUD/CHF", "OTC"),
            ("AUD/JPY", "Stock"),
            ("AUD/JPY", "OTC"),
            ("AUD/USD", "Stock"),
            ("AUD/USD", "OTC"),
            ("EUR/AUD", "Stock"),
            ("EUR/AUD", "OTC"),
            ("EUR/CAD", "Stock"),
            ("EUR/CAD", "OTC"),
            ("EUR/GBP", "Stock"),
            ("EUR/GBP", "OTC"),
            ("EUR/JPY", "Stock"),
            ("EUR/JPY", "OTC"),
            ("EUR/USD", "Stock"),
            ("EUR/USD", "OTC"),
            ("GBP/AUD", "Stock"),
            ("GBP/AUD", "OTC"),
            ("GBP/CAD", "Stock"),
            ("GBP/CAD", "OTC"),
            ("GBP/CHF", "Stock"),
            ("GBP/CHF", "OTC"),
            ("GBP/USD", "Stock"),
            ("GBP/USD", "OTC"),
            ("USD/BDT", "OTC"),
            ("USD/BRL", "OTC"),
            ("USD/CAD", "Stock"),
            ("USD/CAD", "OTC"),
            ("USD/CHF", "Stock"),
            ("USD/CHF", "OTC"),
            ("USD/JPY", "Stock"),
            ("GBP/JPY", "Stock"),
            ("NZD/USD", "OTC"),
        ]
        
        stock_market, _ = Market.objects.get_or_create(name="Stock")
        otc_market, _ = Market.objects.get_or_create(name="OTC")

        for symbol, market_type in PAIRS_LIST:
            market = otc_market if market_type == "OTC" else stock_market
            Pair.objects.get_or_create(symbol=symbol, market=market)