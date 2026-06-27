import contextvars
current_scope: contextvars.ContextVar[str] = contextvars.ContextVar("current_scope")