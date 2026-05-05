"""Phone validation, region/carrier metadata. All offline — uses the
`phonenumbers` library (Google's libphonenumber port). No paid lookup
services."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import phonenumbers
from phonenumbers import carrier, geocoder, timezone


@dataclass
class PhoneReport:
    raw: str
    is_valid: bool
    e164: Optional[str]
    region: Optional[str]
    country_code: Optional[int]
    carrier: Optional[str]
    location: Optional[str]
    timezones: list[str]
    line_type: Optional[str]


_TYPES = {
    phonenumbers.PhoneNumberType.MOBILE: "mobile",
    phonenumbers.PhoneNumberType.FIXED_LINE: "fixed_line",
    phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_or_mobile",
    phonenumbers.PhoneNumberType.TOLL_FREE: "toll_free",
    phonenumbers.PhoneNumberType.PREMIUM_RATE: "premium_rate",
    phonenumbers.PhoneNumberType.VOIP: "voip",
    phonenumbers.PhoneNumberType.PERSONAL_NUMBER: "personal",
    phonenumbers.PhoneNumberType.PAGER: "pager",
    phonenumbers.PhoneNumberType.UAN: "uan",
    phonenumbers.PhoneNumberType.UNKNOWN: "unknown",
}


def analyze_phone(raw: str, default_region: str = "US") -> PhoneReport:
    try:
        num = phonenumbers.parse(raw, None if raw.strip().startswith("+") else default_region)
    except phonenumbers.NumberParseException:
        return PhoneReport(raw=raw, is_valid=False, e164=None, region=None, country_code=None,
                           carrier=None, location=None, timezones=[], line_type=None)
    valid = phonenumbers.is_valid_number(num)
    return PhoneReport(
        raw=raw,
        is_valid=valid,
        e164=phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164) if valid else None,
        region=phonenumbers.region_code_for_number(num),
        country_code=num.country_code,
        carrier=carrier.name_for_number(num, "en") or None,
        location=geocoder.description_for_number(num, "en") or None,
        timezones=list(timezone.time_zones_for_number(num)),
        line_type=_TYPES.get(phonenumbers.number_type(num)),
    )
