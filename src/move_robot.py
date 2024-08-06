import asyncio
from inputs import get_gamepad

import wandelbots_api_client as wb

ipc_ip = "172.31.10.35"
cell_id = "cell"

max_position_velocity = 100  # mm/s. Specify the maximum velocity for the position jogging
max_rotation_velocity = 0.5  # rad/s. Specify the maximum rotation velocity for the rotation jogging

gamepad_position_direction = wb.models.Vector3d(x=0, y=0, z=0)
gamepad_rotation_direction = wb.models.Vector3d(x=0, y=0, z=0)
gamepad_position_velocity = 0
gamepad_rotation_velocity = 0
gamepad_updated = False  # Sync between gamepad reading and jogging direction generator "threads"


async def read_gamepad():
    # use globals here to sync between the gamepad reading and sending the direction requests to robot
    # in a more elaborate example I suggest a class to encapsulate the variables properly
    global gamepad_updated
    global gamepad_position_direction, gamepad_position_velocity, max_position_velocity
    global gamepad_rotation_direction, gamepad_rotation_velocity, max_rotation_velocity

    while True:
        latest_gamepad_events = get_gamepad()
        for event in latest_gamepad_events:
            if event.ev_type == "Absolute" and event.code == "ABS_X":
                gamepad_position_direction.x = event.state / 32767
                gamepad_updated = True
            elif event.ev_type == "Absolute" and event.code == "ABS_Y":
                gamepad_position_direction.y = event.state / 32767
                gamepad_updated = True
            elif event.ev_type == "Absolute" and event.code == "ABS_Z":
                gamepad_position_direction.z = - event.state / 255
                gamepad_updated = True
            elif event.ev_type == "Absolute" and event.code == "ABS_RZ":
                gamepad_position_direction.z = event.state / 255
                gamepad_updated = True

            elif event.ev_type == "Absolute" and event.code == "ABS_RX":
                gamepad_rotation_direction.y = event.state / 32767
                gamepad_updated = True
            elif event.ev_type == "Absolute" and event.code == "ABS_RY":
                gamepad_rotation_direction.x = -event.state / 32767
                gamepad_updated = True
            elif event.code == "BTN_TL":
                gamepad_rotation_direction.z = -event.state
                gamepad_updated = True
            elif event.code == "BTN_TR":
                gamepad_rotation_direction.z = event.state
                gamepad_updated = True
            else:
                pass  # ignore other events

        # calculate new velocity
        if gamepad_updated:
            gamepad_position_velocity = (
                                                    gamepad_position_direction.x ** 2 + gamepad_position_direction.y ** 2 + gamepad_position_direction.z ** 2) ** 0.5
            # divide by sqrt(3) because it is a 3D vector and we want to normalize it to 1
            gamepad_position_velocity = gamepad_position_velocity / 1.732 * max_position_velocity
            gamepad_rotation_velocity = (
                                                    gamepad_rotation_direction.x ** 2 + gamepad_rotation_direction.y ** 2 + gamepad_rotation_direction.z ** 2) ** 0.5
            gamepad_rotation_velocity = gamepad_rotation_velocity / 1.732 * max_rotation_velocity

        # only here the control is handed over to the other 'thread', so
        # only here the gamepad_updated flag gets propagated to the other 'thread', so
        # only here we need to guarantee that all current events from the gamepad are read to have a clean state
        await asyncio.sleep(0)  # yield control to other tasks


"""
This generator will provide the direction requests for the jogging of the robot.
We have acces to the responses from the robot as 'resonses_from_robot' and can react to them.
"""


async def jogging_direction_generator(motion_group_id, responses_from_robot):
    # use globals here to sync between the gamepad reading and sending the direction requests to robot
    # in a more elaborate example I suggest a class to encapsulate the variables properly
    global gamepad_position_direction, gamepad_position_velocity
    global gamepad_rotation_direction, gamepad_rotation_velocity
    global gamepad_updated

    async def read_responses(responses_from_robot):
        async for response in responses_from_robot:
            # Here we could deal with the responses from the robotic component, e.g
            # - print them,
            # - check for errors
            # - check wether the robot has reached a specific position etc.
            pass

    # Start to read the responses from the robot in the background.
    # This decouples the reading of the responses from the generation of the requests
    # I could also use the responses to adapt the next request, but here this is not needed
    # so just read the responses in the background and ignore them
    asyncio.create_task(read_responses(responses_from_robot))

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
        if gamepad_updated:
            direction_request.position_direction = gamepad_position_direction
            direction_request.rotation_direction = gamepad_rotation_direction
            direction_request.position_velocity = gamepad_position_velocity
            direction_request.rotation_velocity = gamepad_rotation_velocity
            gamepad_updated = False
            yield direction_request
        await asyncio.sleep(0)  # yield control to other tasks


async def move_robot(ipc_ip, cell_id):
    # setup
    config = wb.Configuration(host=f"http://{ipc_ip}/api/v1")
    config.verify_ssl = False
    api_client = wb.ApiClient(config)
    motion_group_api = wb.MotionGroupApi(api_client)
    controller_api = wb.ControllerApi(api_client)
    jogging_api = wb.MotionGroupJoggingApi(api_client)

    # check which controller and motion group are available and use the first one
    controller = await controller_api.list_controllers(cell=cell_id)
    controller_id = controller.instances[0].controller
    motion_groups = await motion_group_api.list_motion_groups(cell=cell_id)
    motion_group_id = motion_groups.instances[0].motion_group
    print(f"will move motion group: {motion_group_id}")

    # start the reading from gamepad
    asyncio.create_task(read_gamepad())
    print("ready for gamepad input")

    # start the robot interaction
    # jogging is a bidirectional interaction with the wandelbots components
    # using that approach it is possible to alter the direction of the movement while the robot is moving

    # As a user, I provide a generator that will provide the direction requests
    # Inside the generator I have acces to the state of the Controller I am working with.
    # I can react to the state of the robot and adapt my next request accordingly (see jogging_direction_generator)
    await jogging_api.direction_jogging(
        cell=cell_id,
        # use a lambda here to be able to pass the motion_group_id to the generator additionally to the response_stream
        client_request_generator=lambda response_stream: jogging_direction_generator(
            motion_group_id, response_stream
        ))

    await api_client.close()


if __name__ == '__main__':
    # make sure to specifiy the correct ip address and cell id at the top of the file
    asyncio.run(move_robot(ipc_ip, cell_id))
