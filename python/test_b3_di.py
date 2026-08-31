from datetime import datetime

from brasa import get_marketdata


data = get_marketdata(
    "b3-futures-settlement-prices",
    refdate=datetime(2026, 8, 28)
)

print(data)