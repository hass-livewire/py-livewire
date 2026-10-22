"""Constants of the LiveWire mobile API, as used by the LiveWire EV app 1.9.0."""

API_URL = "https://mobileapi.livewire.com/api"
GIGYA_URL = "https://accounts.us1.gigya.com"

# The app logs in with the global Gigya key and data center, regardless of the
# user's region
GIGYA_API_KEY = "4_6aX8cf8RFVt6F3JQQZaF3A"
DATA_CENTER = "us1"

BRAND = "LiveWire"
APP_VERSION = "1.9.0"

# What the app reports about the phone: "<manufacturer> <model>" and the
# Android SDK level
DEVICE_MODEL = "Google Pixel 8"
OS_VERSION = "34"
LANGUAGE = "en-US"

KM_PER_MILE = 1.609344

# Values of error.code in the response envelope
CODE_OK = "0"
CODE_PARTIAL = "-300"  # the app still shows the charging data that comes with it
CODE_NOT_PAIRED = "3000"
CODE_MAINTENANCE_OK = "5101"

# Values of the top-level "code" when verifying a pairing code
CODE_ATTEMPTS_EXCEEDED = 4003
CODE_WRONG_CODE = 4004

# Top-level "code" of the tire pressure response when the bike reported none
CODE_NO_DATA = 3000

# Charging schedules use English short day names
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
