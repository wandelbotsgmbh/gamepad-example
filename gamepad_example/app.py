import asyncio
import copy
from typing import List

import wandelbots_api_client as wb
from decouple import config
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import RedirectResponse
from loguru import logger

from gamepad_example.move_robot import move_robot, stop_movement
from gamepad_example.utils import CELL_ID
from gamepad_example.utils import get_api_client
from inputs import get_gamepad

BASE_PATH = config("BASE_PATH", default="", cast=str)
app = FastAPI(title="gamepad_example", root_path=BASE_PATH)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", summary="Redirects to the swagger docs page")
async def root():
    # One could serve a nice UI here as well. For simplicity, we just redirect to the swagger docs page.
    return RedirectResponse(url=BASE_PATH + "/docs")


@app.get("/app_icon.png", summary="Services the app icon for the homescreen")
async def get_app_icon():
    try:
        return FileResponse(path="static/app_icon.png", media_type='image/png')
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Icon not found")


@app.post(
    "/activate_jogging",
    status_code=201,
    summary="Moves the robot via jogging with Gamepad input",
    description="oves the robot via jogging with Gamepad input")
async def activate_jogging(background_tasks: BackgroundTasks):
    logger.info("creating api clients...")
    api_client = get_api_client()
    motion_group_api = wb.MotionGroupApi(api_client)
    controller_api = wb.ControllerApi(api_client)

    # get the motion group id
    controllers = await controller_api.list_controllers(cell=CELL_ID)

    if len(controllers.instances) != 1:
        raise HTTPException(
            status_code=400,
            detail="No or more than one controllers found. Example just works with one controllers. "
                   "Go to settings app and create one or delete all except one.")
    controller_id = controllers.instances[0].controller
    logger.info("using controller {}", controller_id)

    logger.info("selecting motion group...")
    motion_groups = await motion_group_api.list_motion_groups(cell=CELL_ID)
    if len(motion_groups.instances) != 1:
        raise HTTPException(
            status_code=400,
            detail="No or more than one motion group found. Example just works with one motion group. "
                   "Go to settings app and create one or delete all except one.")
    motion_group_id = motion_groups.instances[0].motion_group
    logger.info("using motion group {}", motion_group_id)

    logger.info("activating motion groups...")
    await motion_group_api.activate_motion_group(
        cell=CELL_ID,
        motion_group=motion_group_id)
    await controller_api.set_default_mode(cell=CELL_ID, controller=controller_id, mode="MODE_CONTROL")

    background_tasks.add_task(move_robot, motion_group_id)
    api_client.close()
    return {"status": "jogging activated"}


@app.post(
    "/deactivate_jogging",
    status_code=201,
    summary="Stops the robot jogging",
    description="stops the robot jogging")
async def deactivate_jogging():
    stop_movement()
    return {"status": "jogging deactivated"}
