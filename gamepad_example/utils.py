import wandelbots_api_client as wb
import requests
from decouple import config
from requests.auth import HTTPBasicAuth

CELL_ID = config("CELL_ID", default="cell", cast=str)


def get_api_client() -> wb.ApiClient:
    """Creates a new API client for the wandelbots API.
    """
    # if there is basic auth required (e.g. when running this service locally)
    basic_user = config("NOVA_USERNAME", default=None, cast=str)
    basic_pwd = config("NOVA_PASSWORD", default=None, cast=str)

    base_url = get_base_url(basic_user, basic_pwd)

    client_config = wb.Configuration(host=base_url)
    client_config.verify_ssl = False

    if basic_user is not None and basic_pwd is not None:
        client_config.username = basic_user
        client_config.password = basic_pwd

    return wb.ApiClient(client_config)


def get_base_url(basic_user, basic_pwd) -> str:
    # in-cluster it is the api-gateway service
    # when working with a remote instance one needs to provide the host via env variable
    api_host = config("WANDELAPI_BASE_URL", default="api-gateway:8080", cast=str)
    api_host = api_host.strip()
    api_host = api_host.replace("http://", "")
    api_host = api_host.replace("https://", "")
    api_host = api_host.rstrip("/")
    api_base_path = "/api/v1"
    protocol = get_protocol(api_host, basic_user, basic_pwd)
    if protocol is None:
        msg = f"Could not determine protocol for host {api_host}. Make sure the host is reachable."
        raise Exception(msg)
    return f"{protocol}{api_host}{api_base_path}"


# get the protocol of the host (http or https)
def get_protocol(host, basic_user, basic_pwd) -> str:
    api = f"/api/v1/cells/{CELL_ID}/controllers"
    auth = None
    if basic_user is not None and basic_pwd is not None:
        auth = HTTPBasicAuth(basic_user, basic_pwd)

    try:
        response = requests.get(f"https://{host}{api}", auth=auth, timeout=5)
        if response.status_code == 200:
            return "https://"
    except requests.RequestException:
        pass

    try:
        response = requests.get(f"http://{host}{api}", auth=auth, timeout=5)
        if response.status_code == 200:
            return "http://"
    except requests.RequestException:
        pass

    return None
