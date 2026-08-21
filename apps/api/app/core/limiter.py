from slowapi import Limiter
from slowapi.util import get_remote_address

# Separate module (not defined in main.py) so routers can import it without
# a circular import back to the app entrypoint.
limiter = Limiter(key_func=get_remote_address)
