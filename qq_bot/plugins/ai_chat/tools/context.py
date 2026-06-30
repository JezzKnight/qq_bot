import contextvars
current_scope: contextvars.ContextVar[str] = contextvars.ContextVar("current_scope")
current_sender_name: contextvars.ContextVar[str] = contextvars.ContextVar("current_sender_name")