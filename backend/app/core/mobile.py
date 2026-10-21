"""Kuwait mobile numbers: the member portal signs families in by mobile, so every stored
number used for sign-in is kept in one form, +965XXXXXXXX."""

import re

# Parents on Arabic keyboards type Arabic-Indic (and Persian) digits; accept them.
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_MOBILE = re.compile(r"^(?:\+?965|00965)?([4569]\d{7})$")


def normalize_kuwait_mobile(value: str | None) -> str:
    """Return the number as +965XXXXXXXX, or raise ValueError."""
    compact = re.sub(r"[\s\-().]", "", (value or "").translate(_DIGITS))
    match = _MOBILE.match(compact)
    if not match:
        raise ValueError("Enter a Kuwait mobile number: 8 digits starting with 4, 5, 6 or 9.")
    return "+965" + match.group(1)


def try_normalize(value: str | None) -> str | None:
    try:
        return normalize_kuwait_mobile(value)
    except ValueError:
        return None
