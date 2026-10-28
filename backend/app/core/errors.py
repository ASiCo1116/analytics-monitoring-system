"""Error detail strings used by more than one module.

INACTIVE_USER is also part of the API contract: the frontend uses it to tell
a disabled account (log out) apart from a plain permission error (stay
logged in).
"""

INACTIVE_USER = "Inactive user"
NOT_ENOUGH_PERMISSIONS = "Not enough permissions"
INVALID_CREDENTIALS = "Could not validate credentials"
DATABASE_UNAVAILABLE = "Database unavailable"
