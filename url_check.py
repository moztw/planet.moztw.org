'''
檢查 ``moztw/config.ini`` 訂閱的 URL 是否已經 301 或失效。

使用方法
---

.. code:: bash
    # 安裝依賴
    pip install -r url_check.requirements.txt

    # 執行程式，並將結果輸出至 url_check.md
    python3 url_check.py > url_check.md

注意事項
---

您可能需要安裝 Python 3.10 及 url_check.requirements.txt
列出的相依套件才能使用本 script。

考慮到 ``config.ini`` 的格式與 ``ConfigParser`` 的 INI 格式有相當大的雷同，
本程式使用 ``ConfigParser`` 分析 ``config.ini``。

某些網站（如 Medium）會擋爬蟲。因此遇到 404 連結，請二次檢查而非盲目刪除。
'''

import asyncio
import configparser
from enum import Enum
from typing import Any, Iterable, Tuple, TypedDict, cast
import aiohttp
from loguru import logger

class SiteStatus(Enum):
    '''網站的狀態是正常運作、301 轉址，還是已經無法存取？'''
    Normal = 200
    Moved = 301
    Unavailable = 404

class SubscribedUrl(TypedDict):
    '''一個網址的結構''' 
    name: str  # ex. MozTW YouTube 頻道
    description: str  # ex. Mozilla 與 MozTW 社群影片
    blogname: str  # ex. MozTW YouTube
    icon: str  # ex. default
    truelink: str  # ex. https://www.youtube.com/moztw

def extract_urls_from_config(config: dict[str, Any]) -> dict[str, SubscribedUrl]:
    '''只留下來 key 是 ``http`` 開頭的資料（我們只打算處理網址）。

    留下來的網址全部假定為 ``SubscribedUrl`` 類型。'''
    return cast(
        dict[str, SubscribedUrl],
        { k: v for k, v in config.items() if k.startswith('http') }
    )

async def try_request(url: str) -> Tuple[SiteStatus, str | None]:
    '''嘗試請求 url 並回傳網站的狀態。
    
    如果 ``SiteStatus`` 是 ``Moved``，
    則會在回傳的 Tuple 的第二項回傳轉址後的網址。'''

    logger.debug(f"嘗試請求 {url}⋯⋯")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as resp:
                # 200~299 都屬 OK。
                if resp.status in range(200, 300):
                    # 檢查是否有轉址紀錄。
                    history = resp.history[0] if len(resp.history) > 0 else None

                    if history:
                        # 如果有，則認定是 301 (Moved)。回傳轉址後的連結。
                        return (SiteStatus.Moved, str(resp.url))
                    else:
                        # 反之，認定為普通的存取。
                        return (SiteStatus.Normal, None)
                else:
                    logger.error(f"無法存取 {url}，因為網站回傳了錯誤代碼 {resp.status}。")

        except aiohttp.ClientResponseError as cre:
            logger.error(f"無法連線至 {cre.request_info.url}，錯誤訊息是 {cre.message}。")

    # 沒有 early return 都是壞的。
    return (SiteStatus.Unavailable, None)

def interpret_result(url: str, response: Tuple[SiteStatus, str | None]) -> str | None:
    '''判讀結果，並將結果回傳為一個人類可讀的字串。
    
    參數
    ---
    :param url 請求的連結
    :param response ``try_request()` 回傳的結果'''

    status, redirect_url = response

    match status:
        case SiteStatus.Normal:
            # 正常狀態無視即可。
            return None
        case SiteStatus.Moved:
            # 告知使用者已經轉址。
            return f"| 301 轉址 | {url} | {redirect_url} |"
        case SiteStatus.Unavailable:
            # 告知使用者本服務已經失效。
            return f"| 404 失效 | {url} | |"

async def main():
    config = configparser.ConfigParser()
    config.read("./moztw/config.ini")

    http_urls = extract_urls_from_config(dict(config))
    
    async def request_action(url: str) -> str | None:
        '''for gathering'''

        resp = await try_request(url)
        return interpret_result(url, resp)

    # 進行並行請求，及格式化為人類可讀的文字。
    raw_response = await asyncio.gather(
        *(asyncio.gather(request_action(key), request_action(value["truelink"])) for (key, value) in http_urls.items())
    )

    # 進行資料展平及去 None。
    response = list(cast(Iterable[str], filter(lambda x: x != None, [entry for entries in raw_response for entry in entries])))
    # 排序回應
    response.sort()

    # 加上標題列
    response.insert(0, "| 狀態 | 網址 | 轉址網址 |")
    response.insert(1, "| --- | --- | ------ |")

    print("\n".join(response))

asyncio.run(main())
