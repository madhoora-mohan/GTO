# WHAT: The shared slowapi Limiter instance.
# WHY:  Both main.py (to attach it to app.state and register the 429 handler)
#       and individual routers (to apply @limiter.limit(...) to endpoints)
#       need the same Limiter instance. Defining it here avoids a circular
#       import between main.py and the routers.

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
