# run with "python3 src/hatch_rest_api/stub.py"
import logging
import asyncio

from getpass import getpass
from pathlib import Path
import sys

path_root = Path(__file__).parents[2]
sys.path.append(str(path_root))
from src.hatch_rest_api.util_bootstrap import get_rest_devices

logger = logging.getLogger("src.hatch_rest_api")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)


async def testing():
    email = input("Email: ")
    password = getpass()
    mqtt_connection = None
    api = None
    try:
        api, mqtt_connection, iot_devices, expiration = await get_rest_devices(
            email, password
        )

        for iot_device in iot_devices:
            def output():
                print(f"******-{iot_device}")

            iot_device.register_callback(output)

        await asyncio.sleep(60)
        mqtt_connection.disconnect().result()
    finally:
        if mqtt_connection:
            mqtt_connection.disconnect().result()
        if api:
            await api.cleanup_client_session()


asyncio.run(testing())
