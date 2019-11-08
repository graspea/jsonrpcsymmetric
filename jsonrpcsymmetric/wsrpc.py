import asyncio
from asyncio.futures import CancelledError, Future
from functools import partial

from typing import Dict, List
import json

import aiohttp
from aiohttp.abc import Application
from aiohttp.http_websocket import WSCloseCode, WSMessage
from aiohttp.client_exceptions import ClientError

from jsonrpcserver.async_dispatcher import dispatch

from .internals import ConnectionContextImpl
from .typing import ConnectionContext, OtherResponse, ConnectionConfig


class WebSocketConnection(object):
    """
    Main class for handling symmetric RPC.

    Handles:
    - outgoing messages
    - incoming messages
    - coroutines for this connection (context wise)
    - proper close and cancelling of connection coroutines

    """
    context: ConnectionContext
    config: ConnectionConfig
    registered: List[Future] = []

    def __init__(self, app: Application, config: ConnectionConfig, run_futures: List[partial] = None):
        if run_futures is None:
            run_futures = []
        self.config = config
        self.context = ConnectionContextImpl(app, config)
        self.__run_futures = run_futures

    def get_registered(self) -> List[Future]:
        """List of futures registered"""
        return self.registered

    async def add_future(self, func: partial) -> Future:
        """Add future to running"""
        return await self.__add_future(func, self.context)

    async def handle(self):
        """Main handler"""
        try:
            url = self.config.url
            if self.config.connection_identity is not None:
                url = str(self.config.url+self.config.connection_identity)
            # connect
            self.context.ws = await self.context.session.ws_connect(
                                                url=url,
                                                autoping=self.config.auto_ping,
                                                timeout=self.config.timeout,
                                                protocols=self.config.protocols,
                                                receive_timeout=self.config.receive_timeout,
                                                autoclose=self.config.auto_close,
                                                heartbeat=self.config.heartbeat,
                                                origin=self.config.origin,
                                                headers=self.config.headers,
                                                proxy=self.config.proxy,
                                                proxy_auth=self.config.proxy_auth,
                                                proxy_headers=self.config.proxy_headers,
                                                ssl=self.config.ssl,
                                                compress=self.config.compress,
                                                max_msg_size=self.config.max_msg_size,
                                                method=self.config.method)
            # run incoming handler
            incoming_handler = asyncio.ensure_future(self.incoming_handler())
            self.registered.append(incoming_handler)

            # other tasks
            for f in self.__run_futures:
                await self.__add_future(f, self.context)

            # await incoming handler
            await incoming_handler
            # end script
        except ClientError as e:
            raise e
        except CancelledError as ce:
            raise ce
        except Exception as ee:
            raise ee
        finally:
            # clean everything
            try:
                self.__clean_context()
                self.__clean_futures()
            except Exception as e:
                self.context.log.debug(str(e))
            # close websocket
            if self.context is not None and self.context.ws is not None:
                await self.context.ws.close(code=WSCloseCode.GOING_AWAY)

    def __clean_futures(self):
        for f in self.registered:
            if f is not None and not f.cancelled():
                f.cancel()

    def __clean_context(self):
        for t in self.context.get_all_futures():
            if t is not None and not t.cancelled():
                t.cancel()

    async def incoming_handler(self):
        """Consume data from WS"""
        async for msg in self.context.ws:
            msg: WSMessage
            if msg.type == aiohttp.WSMsgType.TEXT:
                req = msg.data
                rrd: Dict = json.loads(req)
                if "error" in rrd:
                    self.context.log.warning("OTHER: " + str(rrd))
                elif "result" in rrd:
                    await self.context.handle_result(OtherResponse(req))
                else:
                    response = await dispatch(req,
                                              context=self.context,
                                              debug=self.config.debug,
                                              methods=self.context.methods)
                    if response.wanted:
                        await self.context.send_my_response(response)
                    else:
                        pass
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                break  # wrapper takes care of ws closing
            elif msg.type == aiohttp.WSMsgType.ERROR:
                break  # wrapper takes care of ws closing

    async def __add_future(self, op, val) -> Future:
        """To add long running future, independently of subscribe"""
        try:
            func = await asyncio.ensure_future(op(context=val))
            self.registered.append(func)
            return func
        except Exception as e:
            self.context.log.warning("Failed adding future: " + str(e))
