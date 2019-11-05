import asyncio
import logging
from abc import abstractmethod
from dataclasses import dataclass
from typing import List, Callable, Tuple, Dict

from aiohttp.abc import Application
from aiohttp.client import ClientSession
from aiohttp.client_ws import ClientWebSocketResponse
from aiohttp.connector import SSLContext
from aiohttp.helpers import BasicAuth
from jsonrpcserver.methods import Methods

from jsonrpcserver.response import Response as MyResponse
from jsonrpcclient.requests import Request as MRequest, Notification as MNotification
from jsonrpcclient.response import Response as OResponse
from jsonrpcclient.requests import Request as ORequest


@dataclass
class ConnectionConfig:
    url: str
    session: ClientSession
    methods: Methods
    connection_name: str = "ws-connection"
    auto_ping: bool = True
    timeout: float = 5.0
    debug: bool = False
    protocols: Tuple = None
    receive_timeout: float = 600.0
    auto_close: bool = True
    heartbeat: float = 30.0
    origin: str = None
    headers: Dict = None
    proxy: str = None
    proxy_auth: BasicAuth = None
    proxy_headers: Dict = None
    ssl: SSLContext = None
    compress: int = 0
    max_msg_size: int = 4194304
    method: str = 'GET'


class OtherRequest(ORequest):
    """Request from other"""
    pass


class MyRequest(MRequest):
    """Request from me"""
    pass


class OtherResponse(OResponse):
    """Response to my request action to MyRequest"""
    pass


class MyNotification(MNotification):
    """Notification from me"""
    pass


class ConnectionContext:
    """ConnectionContext for websocket connection"""
    session: ClientSession
    app: Application
    log: logging.Logger
    url: str
    ws: ClientWebSocketResponse = None
    methods: Methods

    def __init__(self, app: Application, config: ConnectionConfig):
        self.app = app
        self.session = config.session
        self.log = app['logger']
        self.url = config.url
        self.methods = config.methods

    @abstractmethod
    async def register_future(self, future: asyncio.Future) -> str:
        raise NotImplemented

    @abstractmethod
    async def cancel_future(self, future_id: str) -> bool:
        raise NotImplemented

    @abstractmethod
    def get_all_futures(self) -> List[asyncio.Future]:
        raise NotImplemented

    @abstractmethod
    async def send_with_response(self, request: MyRequest) -> OtherResponse:
        """To send my request and wait for somebody's response"""
        raise NotImplemented

    @abstractmethod
    async def send_my_response(self, response: MyResponse) -> None:
        """To send response
        - usually based on somebody's request.
        """
        raise NotImplemented

    @abstractmethod
    async def send_my_notification(self, notification: MyNotification) -> None:
        raise NotImplemented

    @abstractmethod
    async def handle_result(self, response: OtherResponse) -> None:
        """
        Receive response data async and forward them to waiting task.
        (Handle response data that does not come in same order as belonging task were called.)
        :param response:
        :return: None
        :raise: ReceivedErrorResponseError
        """
        raise NotImplemented
