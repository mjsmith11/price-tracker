from app.adapters.amazon import AmazonAdapter
from app.adapters.barnesandnoble import BarnesNobleAdapter
from app.adapters.base import StoreAdapter
from app.adapters.bestbuy import BestBuyAdapter
from app.adapters.lego import LegoAdapter
from app.adapters.target import TargetAdapter
from app.adapters.walmart import WalmartAdapter
from app.adapters.woot import WootAdapter

ADAPTERS: dict[str, StoreAdapter] = {
    adapter.name: adapter
    for adapter in [
        LegoAdapter(),
        BarnesNobleAdapter(),
        WootAdapter(),
        TargetAdapter(),
        BestBuyAdapter(),
        WalmartAdapter(),
        AmazonAdapter(),
    ]
}
