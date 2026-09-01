import base64
import hashlib
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

logger = logging.getLogger(__name__)

_NONCE_SIZE = 12  # AESGCM 推荐的 96-bit nonce

_warned_empty_master_key = False


class DecryptionError(ValueError):
    """API Key 密文格式非法或解密失败（继承 ValueError，兼容既有 except 处理）。"""


def _aes_key() -> bytes:
    """从 MASTER_KEY 派生 32 字节 AES 密钥。

    MASTER_KEY 正常为 64 位 hex（32 字节）；若格式不符则回退到 SHA-256 派生。
    """
    master = settings.master_key
    if not master:
        # 不阻断启动，但醒目告警一次：空密钥派生结果固定，加密形同虚设
        global _warned_empty_master_key
        if not _warned_empty_master_key:
            _warned_empty_master_key = True
            logger.warning(
                "MASTER_KEY 为空，已回退到空字符串派生密钥，API Key 加密形同明文存储！"
                "生产环境必须在 backend/.env 中设置 MASTER_KEY（64 位 hex）。"
            )
    try:
        key = bytes.fromhex(master)
        if len(key) == 32:
            return key
    except ValueError:
        pass
    return hashlib.sha256(master.encode("utf-8")).digest()


def encrypt_key(plain: str) -> str:
    """加密 API Key，返回 "base64(nonce):base64(cipher)" 格式。"""
    nonce = os.urandom(_NONCE_SIZE)
    cipher = AESGCM(_aes_key()).encrypt(nonce, plain.encode("utf-8"), None)
    return (
        base64.b64encode(nonce).decode("ascii")
        + ":"
        + base64.b64encode(cipher).decode("ascii")
    )


def decrypt_key(token: str) -> str:
    """解密 encrypt_key 产生的 "base64(nonce):base64(cipher)" 字符串。

    格式非法（缺少 ":"、分段为空、base64 损坏、校验失败等）统一抛 DecryptionError。
    """
    if not isinstance(token, str) or ":" not in token:
        raise DecryptionError("API Key 密文格式非法：缺少 ':' 分隔符")
    nonce_b64, _, cipher_b64 = token.partition(":")
    if not nonce_b64 or not cipher_b64:
        raise DecryptionError("API Key 密文格式非法：分段为空")
    try:
        nonce = base64.b64decode(nonce_b64)
        cipher = base64.b64decode(cipher_b64)
        plain = AESGCM(_aes_key()).decrypt(nonce, cipher, None)
        return plain.decode("utf-8")
    except Exception as exc:
        raise DecryptionError("API Key 密文解密失败") from exc


def mask_key(plain: str) -> str:
    """脱敏展示 API Key，如 sk-ab...****cd。"""
    if len(plain) <= 8:
        return "****"
    return f"{plain[:5]}...****{plain[-2:]}"
