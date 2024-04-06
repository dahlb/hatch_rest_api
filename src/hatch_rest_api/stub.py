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

            if iot_device.set_sound:
                # set volume safely low
                print("******-Adjusting volume to safe level")
                iot_device.set_volume(25)
                # play each available sound
                for sound in iot_device.sounds:
                    print(f"******-PLAYING SOUND {sound['title']}")
                    iot_device.set_sound(sound)
                    await asyncio.sleep(5)
                iot_device.turn_off()

        await asyncio.sleep(60)
    finally:
        if mqtt_connection:
            mqtt_connection.disconnect().result()
        if api:
            await api.cleanup_client_session()

if __name__ == "__main__":
    asyncio.run(testing())
