"""
OTPストア: Discord bot が生成し、Hono が検証する。
- OTP: 6桁数字、10分有効、1回限り
- セッション管理はHono側で行うため、ここでは検証のみ
"""
import secrets
import time
import logging

log = logging.getLogger("otp_store")

# {otp_code: {"created_at": float, "used": bool}}
_store: dict[str, dict] = {}

OTP_TTL = 600  # 10分


def generate() -> str:
    """6桁OTPを生成して保存し返す。"""
    # 期限切れを掃除
    _cleanup()
    code = f"{secrets.randbelow(1_000_000):06d}"
    _store[code] = {"created_at": time.time(), "used": False}
    log.info(f"OTP生成: {code} (有効期限 {OTP_TTL}秒)")
    return code


def verify(code: str) -> bool:
    """OTPを検証。有効なら True を返しその場で無効化する。"""
    entry = _store.get(code)
    if not entry:
        log.warning(f"OTP不正: {code!r} (存在しない)")
        return False
    if entry["used"]:
        log.warning(f"OTP不正: {code!r} (使用済み)")
        return False
    if time.time() - entry["created_at"] > OTP_TTL:
        log.warning(f"OTP不正: {code!r} (期限切れ)")
        del _store[code]
        return False
    entry["used"] = True
    log.info(f"OTP認証成功: {code!r}")
    return True


def _cleanup():
    now = time.time()
    expired = [k for k, v in _store.items() if now - v["created_at"] > OTP_TTL]
    for k in expired:
        del _store[k]
