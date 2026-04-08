import time


def call_with_retry(func, *args, max_retries=2, **kwargs):
    """调用函数，失败重试max_retries次

    注意：
    - 只重试异常（Exception），不重试 {"success": False} 返回
    - {"success": False} 是预期返回，直接返回给调用者处理
    """
    for attempt in range(max_retries + 1):
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            if attempt < max_retries:
                time.sleep(1)
                continue
            else:
                return {"success": False, "error": str(e), "retries_exhausted": True}
