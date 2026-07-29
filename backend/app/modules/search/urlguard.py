"""SSRF 防护：外部 URL 公网校验。

供 search 模块内三个应用点复用：
- 设置接口保存 searxngUrl 时校验（可按配置放行私网）
- SearXNGProvider 请求前校验（防止绕过设置接口直接写库）
- fetcher 抓取搜索结果 URL 前校验（无例外，一律拒绝私网）
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """是否公网地址：拒绝私网/回环/链路本地/组播/保留/0.0.0.0 等。"""
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_url(url: str, *, allow_private: bool = False) -> str | None:
    """校验 URL 是否可安全访问；返回 None 表示通过，否则返回可读错误信息。

    仅允许 http/https scheme；用 socket.getaddrinfo 解析主机名后逐个
    检查解析出的 IP。allow_private=True 时仅放宽 IP 检查（自建 SearXNG
    场景），scheme/主机名校验仍然生效。

    注意：getaddrinfo 是阻塞调用，异步上下文请用 validate_public_url_async。
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return "URL 格式不合法"
    if parsed.scheme not in ("http", "https"):
        return "仅允许 http/https 协议"
    host = parsed.hostname
    if not host:
        return "URL 缺少主机名"
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, OSError):
        return f"无法解析主机名 {host}"
    for info in infos:
        # IPv6 地址可能带 %scope 后缀（如 fe80::1%eth0），ipaddress 无法解析
        raw = str(info[4][0]).split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            return f"主机 {host} 解析到无法识别的地址 {raw}"
        if not _is_public(ip):
            if allow_private:
                continue
            return f"主机 {host} 解析到非公网地址 {ip}，已拒绝访问"
    return None


async def validate_public_url_async(
    url: str, *, allow_private: bool = False
) -> str | None:
    """validate_public_url 的异步包装（DNS 解析放入线程避免阻塞事件循环）。"""
    return await asyncio.to_thread(
        validate_public_url, url, allow_private=allow_private
    )
