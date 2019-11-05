import asyncio

from aiohttp.abc import Application
from typing import Dict, Union, List, Coroutine
from .typing import ConnectionContext, OtherResponse, MyRequest, MyResponse, MyNotification, ConnectionConfig

from jsonrpcclient.exceptions import ReceivedErrorResponseError
from jsonrpcclient.response import JSONRPCResponse, ErrorResponse
from jsonrpcclient.parse import parse


class ConnectionContextImpl(ConnectionContext):
    def __init__(self, app: Application, config: ConnectionConfig):
        super().__init__(app, config)

        # for storage of additional information (Subscription,CancellationTokens,etc.)
        self.data: Dict[str, any] = {}

        # send messages waiting for response
        self.out_requests: Dict[int, asyncio.Event] = {}
        self.out_tasks: Dict[int, Coroutine]
        self.out_responses: Dict[int, Union[JSONRPCResponse, List[JSONRPCResponse]]] = {}

        # running tasks/futures/coroutine for request/notification
        self.__futures_counter = 0
        self.__futures: Dict[str, asyncio.Future] = {}

    async def register_future(self, future: asyncio.Future) -> str:
        tid = str(self.__futures_counter)
        self.__futures.update({tid: future})
        self.__futures_counter += 1
        return str(tid)

    async def cancel_future(self, future_id: str) -> bool:
        try:
            f = self.__futures.pop(future_id)
            f.cancel()
            return True
        except KeyError:
            return False

    def get_all_futures(self) -> List[asyncio.Future]:
        try:
            return list(self.__futures.values())
        except KeyError:
            return []

    async def send_with_response(self, request: MyRequest) -> any:
        """To send my request and wait for somebody's response"""
        return await RequestWithResponse(self).send_async(request)

    async def send_my_response(self, response: MyResponse) -> None:
        """To send response
        - usually based on somebody's request.
        """
        return await self.ws.send_str(str(response))

    async def send_my_notification(self, notification: MyNotification) -> None:
        return await self.ws.send_str(str(notification))

    async def handle_result(self, response: OtherResponse) -> None:
        response.data = parse(response.text, batch=True, validate_against_schema=True)
        # If received a single error response, raise
        if isinstance(response.data, ErrorResponse):
            raise ReceivedErrorResponseError(response.data)
        else:
            rid: int = response.data.id
            self.out_responses.update({rid: response.data})
            # fire event
            event = self.out_requests.pop(rid)
            event.set()


class RequestWithResponse:
    def __init__(self, context: ConnectionContextImpl):
        self.event: asyncio.Event = asyncio.Event()
        self.context = context

    async def send_async(self, request: MyRequest):
        self.context.out_requests.update({request["id"]: self.event})
        await self.context.ws.send_str(str(request))
        await self.event.wait()
        res = self.context.out_responses.pop(request["id"])
        return res.result


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
