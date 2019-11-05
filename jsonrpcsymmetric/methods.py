from typing import Any, Optional, Callable

from jsonrpcserver.methods import Methods

"""A default Methods object which can be used, or user can create their own."""
global_handlers = Methods()


def get_methods() -> Methods:
    """Return handlers (global list)"""
    return global_handlers


def add_method(*args: Any, **kwargs: Any) -> Optional[Callable]:
    """Add to handlers (global list)"""
    return global_handlers.add(*args, **kwargs)
