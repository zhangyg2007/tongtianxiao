"""BettaFish 基座 HTTP 客户端（同步 httpx，集中管理超时与错误）"""
import httpx

from .config import get_settings

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class BettaFishError(Exception):
    """基座调用失败（网络错误或非 2xx 响应）"""


def bettafish_request(method: str, path: str, *, json_body: dict | None = None) -> dict:
    url = f"{get_settings().bettafish_base_url.rstrip('/')}{path}"
    try:
        resp = httpx.request(method, url, json=json_body, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise BettaFishError(f"基座不可达: {exc}") from exc
    if resp.status_code >= 400:
        raise BettaFishError(f"基座返回 {resp.status_code}: {resp.text[:300]}")
    try:
        return resp.json()
    except ValueError as exc:
        raise BettaFishError("基座响应不是 JSON") from exc


def stream_request(method: str, path: str):
    """用于文件下载代理，返回 (httpx.Response)；调用方负责关闭"""
    url = f"{get_settings().bettafish_base_url.rstrip('/')}{path}"
    client = httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0))
    req = client.build_request(method, url)
    resp = client.send(req, stream=True)
    if resp.status_code >= 400:
        content = resp.read()
        client.close()
        raise BettaFishError(f"基座返回 {resp.status_code}: {content[:300]!r}")
    return resp, client
