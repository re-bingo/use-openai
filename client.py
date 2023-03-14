from random import choice

from httpx import AsyncClient, Timeout
from starlite import Provide

from env import api_keys, proxies

inject_sk = {"bearer": Provide(lambda: {"Authorization": f"Bearer {choice(api_keys)}"})}

client = AsyncClient(
    base_url="https://api.openai.com/v1/",
    proxies=proxies,
    http2=True,
    headers={"Content-Type": "application/json", "Accept-Encoding": "br"},
    timeout=Timeout(connect=5, write=5, read=30, pool=5),
)
