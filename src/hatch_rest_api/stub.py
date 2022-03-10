# run with "python3 src/hatch_rest_api/us_kia_stub.py"
import logging
import asyncio
from threading import Event

from getpass import getpass
from pathlib import Path
import sys

path_root = Path(__file__).parents[2]
sys.path.append(str(path_root))
from src.hatch_rest_api.util_bootstrap import get_rest_minis
from src.hatch_rest_api.const import RestMiniAudioTrack


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
        count = 0
        while True:
            count = count + 1
            api, mqtt_connection, rest_minis, expiration = await get_rest_minis(
                email, password
            )

            def output():
                print(f"{count}******-{rest_minis[0]}")

            rest_minis[0].register_callback(output)

            def output2():
                print(f"{count}******-{rest_minis[1]}")

            rest_minis[1].register_callback(output2)

            #        print(rest_mini.shadow_value)
            #            rest_mini.set_audio_track(RestMiniAudioTrack.Ocean)
            rest_minis[1].set_volume(15)
            #        rest_mini.set_audio_track(RestMiniAudioTrack.NONE)
            await asyncio.sleep(60)
            mqtt_connection.disconnect().result()
    finally:
        if mqtt_connection:
            mqtt_connection.disconnect().result()
        if api:
            await api.cleanup_client_session()


asyncio.run(testing())
