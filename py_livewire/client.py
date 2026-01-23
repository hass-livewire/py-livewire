import requests
import uuid
import random

from time import sleep
from dataclasses import dataclass
from dataclasses_json import dataclass_json

API_KEY = "4_6aX8cf8RFVt6F3JQQZaF3A"
API_URL = "https://mobileapi.livewire.com/api"


@dataclass_json
@dataclass
class Motorcycle:
    id: int
    vin: str

    make: str
    model: str
    year: int

    charge: int
    charging: bool
    charge_limit: int
    plugged_in: bool
    range: int
    odometer: int


class Client:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.device_id = str(uuid.uuid4())

        self.sess = requests.Session()
        self.sess.headers.pop("Accept")

    def login(self):
        nonce = f"{random.randrange(100000000000, 9999999999999)}_{random.randrange(100000000, 999999999)}"

        resp = self.sess.post(
            "https://accounts.us1.gigya.com/accounts.login",
            headers={
                "apikey": API_KEY,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
            },
            data={
                "loginID": self.email,
                "password": self.password,
                "apiKey": API_KEY,
                "format": "json",
                "include": "profile,data",
                "nonce": nonce,
            }
        )

        uid = resp.json()["UID"]
        resp = self.sess.post(
            f"{API_URL}/session",
            params={"brand": "LiveWire"},
            json={
                "UID": uid,
                "dataCenter": "us1",
                "deviceUUID": self.device_id
            }
        )

        token = resp.json()["jwt"]
        self.sess.headers.update({
            "Accept-Encoding": "gzip",
            "Accept-Language": "en-US",
            "Authorization": f"Bearer {token}",
            "Connection": "Keep-Alive",
            "Content-Type": "application/json",
            "model": "samsing SM-T820",
            "User-Agent": "Android",
        })

    def get_motorcycles(self):
        resp = self.sess.get(
            f"{API_URL}/getAllbikes/pairingStatus",
            params={
                "deviceUUID": self.device_id,
                "brand": "LiveWire"
            },
        )
        self.sess.cookies.clear()

        for bike in resp.json()["bikes"]:
            # resp = self.sess.get(
            #     f"{API_URL}/bike/{bike["id"]}/location",
            #     headers={
            #         "Authorization": f"Bearer {self.token}",
            #         "Content-Type": "application/json",
            #         "Accept-Encoding": "gzip",
            #         "Accept-Language": "en-US",
            #         "model": "samsung SM-T820",
            #         "User-Agent": "Android",
            #     },
            #     params={
            #         "brand": "LiveWire"
            #     },
            # )

            # print(resp.text)

            resp = self.sess.get(
                f"{API_URL}/bikes/{bike["id"]}/charging/status",
                params={
                    "brand": "LiveWire",
                },
            )

            print(resp.request.headers)

            print(resp.text)
            # d = resp.json()['bikeChargingData']
            # print(d)
