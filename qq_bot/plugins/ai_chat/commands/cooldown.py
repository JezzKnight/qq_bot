import time

_cooldowns: dict[str, float] = {}

def check_cooldown(key: str, seconds: int) -> bool:
    """
    用内存字典来储存指令触发事件并作冷却校验，True=没冷却，False=冷却中
    """
    now = time.time()
    if now - _cooldowns.get(key, 0) < seconds:
        return False
    
    _cooldowns[key] = now
    return True