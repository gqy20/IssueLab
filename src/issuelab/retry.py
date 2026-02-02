"""重试机制 - 处理网络错误和 API 限流"""

import asyncio
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryError(Exception):
    """重试失败异常"""

    pass


async def retry_async(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    **kwargs: Any,
) -> Any:
    """异步函数重试装饰器

    Args:
        func: 要重试的异步函数
        max_retries: 最大重试次数
        initial_delay: 初始延迟（秒）
        backoff_factor: 退避因子（指数退避）
        *args, **kwargs: 函数参数

    Returns:
        函数返回值

    Raises:
        RetryError: 所有重试失败后抛出
    """
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e

            if attempt < max_retries:
                logger.warning(
                    f"尝试 {attempt + 1}/{max_retries + 1} 失败: {type(e).__name__}: {e}. 将在 {delay:.1f}秒 后重试..."
                )
                await asyncio.sleep(delay)
                delay *= backoff_factor
            else:
                logger.error(f"所有 {max_retries + 1} 次尝试均失败: {type(e).__name__}: {e}")

    raise RetryError(f"重试 {max_retries + 1} 次后仍然失败") from last_exception


def retry_sync(max_retries: int = 3, initial_delay: float = 1.0, backoff_factor: float = 2.0):
    """同步函数重试装饰器

    Args:
        max_retries: 最大重试次数
        initial_delay: 初始延迟（秒）
        backoff_factor: 退避因子（指数退避）

    Returns:
        装饰器函数
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            import time

            delay = initial_delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    if attempt < max_retries:
                        logger.warning(
                            f"尝试 {attempt + 1}/{max_retries + 1} 失败: {type(e).__name__}: {e}. "
                            f"将在 {delay:.1f}秒 后重试..."
                        )
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        logger.error(f"所有 {max_retries + 1} 次尝试均失败: {type(e).__name__}: {e}")

            raise RetryError(f"重试 {max_retries + 1} 次后仍然失败") from last_exception

        return wrapper

    return decorator
