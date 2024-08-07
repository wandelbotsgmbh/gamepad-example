import asyncio
from inputs import get_gamepad
from loguru import logger

import wandelbots_api_client as wb

from gamepad_example.utils import CELL_ID
from gamepad_example.utils import get_api_client

shall_run = False
max_position_velocity = 100
max_rotation_velocity = 0.5

gamepad_position_direction = wb.models.Vector3d(x=0, y=0, z=0)
gamepad_rotation_direction = wb.models.Vector3d(x=0, y=0, z=0)
gamepad_position_velocity = 0
gamepad_rotation_velocity = 0
gamepad_updated = False


async def read_gamepad():
    global gamepad_updated
    global gamepad_position_direction, gamepad_position_velocity, max_position_velocity
    global gamepad_rotation_direction, gamepad_rotation_velocity, max_rotation_velocity
    global shall_run

    while True:
        if not shall_run:
            return
        latest_gamepad_events = get_gamepad()
        for event in latest_gamepad_events:
            if event.ev_type == "Absolute" and event.code == "ABS_X":
                gamepad_position_direction.x = event.state / 32767
            elif event.ev_type == "Absolute" and event.code == "ABS_Y":
                gamepad_position_direction.y = event.state / 32767
            elif event.ev_type == "Absolute" and event.code == "ABS_Z":
                gamepad_position_direction.z = - event.state / 255
            elif event.ev_type == "Absolute" and event.code == "ABS_RZ":
                gamepad_position_direction.z = event.state / 255

            elif event.ev_type == "Absolute" and event.code == "ABS_RX":
                gamepad_rotation_direction.y = event.state / 32767
            elif event.ev_type == "Absolute" and event.code == "ABS_RY":
                gamepad_rotation_direction.x = -event.state / 32767
            elif event.code == "BTN_TL":
                gamepad_rotation_direction.z = -event.state
            elif event.code == "BTN_TR":
                gamepad_rotation_direction.z = event.state
            logger.info("read event...")
            gamepad_updated = True

        gamepad_position_velocity = (
                                                gamepad_position_direction.x ** 2 + gamepad_position_direction.y ** 2 + gamepad_position_direction.z ** 2) ** 0.5
        gamepad_position_velocity = gamepad_position_velocity / 1.732 * max_position_velocity
        gamepad_rotation_velocity = (
                                                gamepad_rotation_direction.x ** 2 + gamepad_rotation_direction.y ** 2 + gamepad_rotation_direction.z ** 2) ** 0.5
        gamepad_rotation_velocity = gamepad_rotation_velocity / 1.732 * max_rotation_velocity

        await asyncio.sleep(0)  # yield control to other tasks


async def jogging_direction_generator(motion_group_id, responses_from_robot):
    async def read_responses(responses_from_robot):
        async for response in responses_from_robot:
            pass
            # print(response)

    asyncio.create_task(read_responses(responses_from_robot))

    global gamepad_position_direction, gamepad_position_velocity
    global gamepad_rotation_direction, gamepad_rotation_velocity
    global gamepad_updated
    global shall_run
    direction_request = wb.models.DirectionJoggingRequest(
        motion_group=motion_group_id,
        position_direction=wb.models.Vector3d(x=0, y=0, z=0),
        rotation_direction=wb.models.Vector3d(x=0, y=0, z=0),
        position_velocity=0,
        rotation_velocity=0,
        response_rate=1000
    )

    yield direction_request
    while True:
        if not shall_run:
            return

        if gamepad_updated:
            direction_request.position_direction = gamepad_position_direction
            direction_request.rotation_direction = gamepad_rotation_direction
            direction_request.position_velocity = gamepad_position_velocity
            direction_request.rotation_velocity = gamepad_rotation_velocity
            gamepad_updated = False
            yield direction_request
        await asyncio.sleep(0)  # yield control to other tasks


async def move_robot(motion_group_id):
    global shall_run

    shall_run = True
    api_client = get_api_client()
    jogging_api = wb.MotionGroupJoggingApi(api_client)

    # start the reading from gamepad
    asyncio.create_task(read_gamepad())

    # start the robot interaction
    await jogging_api.direction_jogging(
        cell=CELL_ID,
        client_request_generator=lambda response_stream: jogging_direction_generator(
            motion_group_id, response_stream
        ))
    api_client.close()


def stop_movement():
    global shall_run
    shall_run = False
