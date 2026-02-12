"""Workers package exports for RQ dotted-path task resolution."""

# RQ may resolve tasks through `app.workers.tasks.*`.
# Ensure `tasks` is available as package attribute.
from . import tasks  # noqa: F401
