
import logging
import sys
import time
from datetime import datetime
from enum import IntEnum
from queue import Queue

from PyQt5 import QtCore, QtWebSockets
from PyQt5.QtCore import QUrl, QCoreApplication, QTimer, pyqtSignal, QThread
from PyQt5.QtWidgets import QApplication
from parse import parse


class Status(IntEnum):
    INIT = 0
    REQ = 1
    RUNNING = 2
    DONE = 3


class WebsocketError(Exception):
    """Web socket error"""
    pass


class WsUnknownRespError(WebsocketError):
    """Unknown Response"""
    pass


class WsCommandError(WebsocketError):
    """Command returned error"""
    pass


class WsLostConnectionError(WebsocketError):
    """Unexpected connection lost"""
    pass


def now():
    return datetime.now().timestamp()


# region Class Request
class Request:
    count = 0

    def __init__(self, cmd, txtime=None, sync=True, status=Status.INIT):
        self.cmd = cmd
        self.txtime = txtime
        self.sync = sync  # wait OK，block
        self._status = status
        self.count += 1

    # remove requests list using:
    #   list.remove(Request(cmd))
    def __eq__(self, other):
        return self.cmd == other.cmd

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value


# region Client class definition
class Client(QtCore.QObject):
    sigConnected = pyqtSignal(bool)
    sigCmdDone = pyqtSignal()
    sigTrigger = pyqtSignal()
    sigError = pyqtSignal(str)
    def __init__(self, ip = None):
        super().__init__(None)
        self._init_logger()
        self.request = None
        self.ip = ip
        # async requests also put here
        self.async_requests = []
        # When transmitting the request, if the request is async meanwhile the "Next" is received,
        # it shows the communication is OK. Also this command will be executed,
        # but when it will be "OK" is unknown, maybe take very long.
        # Once the "OK" response is received, and current request.cmd !== resp.cmd, it should search the async requests
        # to see if request is in that, if yes, log information and delete that request in async requests.
        # Else error happened.
        self.rid = 0
        self.client = QtWebSockets.QWebSocket("", QtWebSockets.QWebSocketProtocol.Version13, None)
        self.client.error.connect(self.error)
        self.heart_timer = QTimer()
        self.heart_timer.setInterval(10000)
        self.heart_timer.timeout.connect(self.start_heart_beat)
        self.heart_timer.start()
        # self.client.open(QUrl("ws://echo.websocket.org"))
        self.isConnected = False
        self.client.open(QUrl("ws://10.68.178.3:7000/socket.io/?EIO=3&transport=websocket"))
        self.client.pong.connect(self.onPong)
        self.client.textMessageReceived.connect(self.rx_handle)
        self.result = None  # Keep the last result value

        # self.sigConnected.connect(self.unlock)
        # self.sigCmdDone.connect(quit_app)

        print(f"@{time.time()}__init__ finished ")

    def get_id(self):
        self.rid += 1
        return self.rid

    # region logging functions
    def _init_logger(self):
        self._logger = logging.getLogger('qWebsocketClient')
        self._logger.setLevel(logging.DEBUG)
        self._fh = logging.FileHandler('qWebsocketClient.log')
        # self._fh.setLevel(logging.DEBUG)
        self._fh.setLevel(logging.INFO)
        # self._fh.setLevel(logging.ERROR)
        self._ch = logging.StreamHandler()
        self._ch.setLevel(logging.ERROR)
        self._formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self._fh.setFormatter(self._formatter)
        self._ch.setFormatter(self._formatter)
        self._logger.addHandler(self._fh)
        self._logger.addHandler(self._ch)
        self._log_debug('Logger has been initialized')
        return

    def _log_info(self, msg):
        if self._logger:
            self._logger.info(msg)
        return

    def _log_error(self, msg):
        if self._logger:
            self._logger.error(msg)
        return

    def _log_debug(self, msg):
        if self._logger:
            self._logger.debug(msg)
        return

    # endregion

    def rx_handle(self, message):
        # Every message received will be processed here.
        # message in ['3', '42["scpi-response","{status} {cmd}\\n"]'
        # status in [connected, Disconnected, Lost connection , OK, NEXT ]
        # cmd in [ASE:XXX]
        # todo: add query cmd parse
        if message == '3':
            self._log_debug("Heart beat response received.")
            return
        self._log_info(f'Received {message}')
        self._log_debug(self.request)
        if message.startswith('42["scpi-response"'):
            result = parse("""42["scpi-response","{status} {cmd}\\n"]""", message)
            # assert result
            # assert self.request
            if "connected" in message:
                self.isConnected = True
                txstamp = self.request.txtime
                time = datetime.now().timestamp() - txstamp
                self._log_info(f"""Command connect cost time:{time:.2f}s""")
                print(f"""Command connect cost time:{time:.2f}s""")
                self.request = None
                self.sigConnected.emit(True)
                self.ase_cmd("SUBS ERROR")
            elif "MESSage Error" in message:
                if "-id=950" in message:
                    print("BPV error, stop")
                    # send error signal.
                    self.sigError.emit(message)
                else:
                    print(f"System Warning ->.")

            elif "Lost Connection" in message:
                self.isConnected = False
                self._log_info(f"""Lost connection""")
                if self.request:
                    raise WsLostConnectionError
                else:
                    self._log_info("Sequence ended.")
                    print("End")
            elif "Disconnect" in message:
                self.isConnected = False
                txstamp = self.request.txtime
                time = datetime.now().timestamp() - txstamp
                self._log_info(f"""Command disconnect cost time:{time:.2f}s""")
                self.request = None
                self.sigConnected.emit(False)
            elif result["status"] == "ERRor":
                self._log_error(f"""{result["cmd"]} error!""")
                raise WsCommandError
            elif result["status"] == "NEXT":
                if self.request.sync:
                    assert self.request.cmd == result["cmd"]
                    self._log_info(f"""Command {result["cmd"]} is in running status.""")
                    self.request.status = Status.RUNNING
                else:  # Async
                    txstamp = self.request.txtime
                    time = datetime.now().timestamp() - txstamp
                    self._log_info(f"""Async command {result["cmd"]} is running in background, cost {time:.2f}s.""")
                    self.request = None
                    r = Request(result["cmd"])
                    if r in self.async_requests:
                        self.async_requests[self.async_requests.index(r)].status = Status.RUNNING
                    else:
                        raise WsUnknownRespError
            elif result["status"] == "OK":
                # If query, result need to be returned
                # result
                txstamp = self.request.txtime
                time = datetime.now().timestamp() - txstamp
                if self.request.sync:
                    # Query command must be Sync.
                    # Following lines try to get the return value
                    # “OK ASE:GET_CELLTRAY_DOOR1 1"
                    ret = result["cmd"].split(self.request.cmd)[1].strip()
                    if ret != "":
                        self.result = ret
                    else:
                        self.result = None
                    self._log_info(f"""Command {result["cmd"]} is finished and cost time:{time:.2f}s""")
                    self.request = None
                    self.sigCmdDone.emit()
                else:
                    r = Request(result["cmd"])
                    if r in self.async_requests:
                        self._log_info(f"""Async command {result["cmd"]} is finished and cost time:{time:.2f}s""")
                        self.async_requests.remove(r)
                    else:
                        raise WsUnknownRespError
            else:
                raise WsUnknownRespError

    def do_ping(self):
        print("client: do_ping")
        self.client.ping(b"foo")

    def ase_cmd(self, cmd, args=None, hint=None, sync=True):
        hints = cmd if hint is None else hint
        print(f"Sending command {hints}")
        if args is None:
            self.transmit(f"""42["scpi-cmd","{cmd}"]""", sync=sync)
        else:
            self.transmit(f"""42["scpi-cmd","{cmd} {args}"]""", sync=sync)

    def unlock(self, connected):
        # self.transmit(f"""42["scpi-connect",{{"ip":"{ip}"}}]""")
        if connected:
            self.ase_cmd("ASE:Open_DOOR_CellTray1", None, "Unlock")
        else:
            print("Not connected.")

    def unlock2(self, connected):
        # self.transmit(f"""42["scpi-connect",{{"ip":"{ip}"}}]""")
        if connected:
            self.ase_cmd("ASE:Open_DOOR_CellTray2", None, "Unlock")
        else:
            print("Not connected.")

    def start_heart_beat(self):
        if self.isConnected:
            self.transmit('2')

    def connectinst(self):
        if not self.ip:
            ip = "10.68.66.70"
        else:
            ip = self.ip
        print(f"Connecting instrument who's ip={ip}")
        self.transmit(f"""42["scpi-connect",{{"ip":"{ip}"}}]""")
        # self.heart_timer.start(2000)

    def dis_connect(self):
        print("Disconnecting instrument")
        self.transmit(f"""42["scpi-disconnect"]""")
        self.heart_timer.stop()

    def transmit(self, msg, sync=True):
        self._log_debug(f"Transmitting {msg}")
        tx_timestamp = datetime.now().timestamp()
        if "disconnect" in msg:
            # self.requests.append(Request("disconnect", txtimestamp, True, REQ))
            cmd = "disconnect"
        elif "connect" in msg:
            # self.requests.append(Request("connect", txtimestamp, True, REQ))
            cmd = "connect"
            print("sending connect...")
        elif msg == '2':
            print("sending heart beat")
            self.client.sendTextMessage(msg)
            return
        else:
            result = parse("""42["scpi-{scpi}","{cmd}"]""", msg)
            assert result
            cmd = result["cmd"]
            # self.requests.append({result["cmd"]: txtimestamp, "status": "req"})
        self.request = Request(cmd, tx_timestamp, sync, Status.REQ)
        if not sync:
            # if this is a async command, then also push it in async_requests
            # Not allow duplicated commands
            if self.request in self.async_requests:
                raise Exception(f"Duplicated commands {cmd} is not allowed.")
            self.async_requests.append(self.request)
        self.client.sendTextMessage(msg)

    def heartbeat(self):
        self.client.sendTextMessage('2')

    def send_message(self, msg=None):
        print(f"发送消息{msg}")
        self.client.sendTextMessage(f"""42["scpi-cmd",{msg}]""")

    def onPong(self, elapsedTime, payload):
        print("onPong - time: {} ; payload: {}".format(elapsedTime, payload))

    def error(self, error_code):
        print("error code: {}".format(error_code))
        print(self.client.errorString())
        self.sigError.emit(self.client.errorString())

    def close(self):
        self.client.close()


# endregion
# region Quit
def quit_app(info):
    print(str(info))
    print("timer timeout - exiting")
    QCoreApplication.quit()


# endregion

def ping():
    client.do_ping()


def do_quque(q, ws):
    # global q
    if not q.empty() and ws.request is None:
        f, *argv = q.get()
        if len(argv) == 0:
            f()
        else:
            f(*argv)
    # else:
    #     client.heartbeat()



if __name__ == '__main__':
    global client

    app = QCoreApplication([])
    client = Client()
    th = QThread()
    client.moveToThread(th)
    q = Queue()
    q.put((client.connectinst, ))
    q.put((client.ase_cmd, "SUBS ERROR", None, "SUBS"))
    q.put((client.dis_connect,))
    q.put((quit_app,))
    th.started.connect(lambda : do_quque(q))
    QTimer.singleShot(2000,th.start)


    # QTimer().singleShot(10000, quit_app)




    # q = Queue()
    # q.put((client.connect, "10.68.178.117"))
    #
    # #
    # q.put((client.ase_cmd, "ASE:Open_DOOR_CellTray1", None, "解锁1"))
    #
    # #
    # q.put((client.dis_connect,))
    # q.put((quit_app,))
    # timer = QTimer()
    # timer.timeout.connect(lambda: do_quque(q))
    # timer.start(2000)

    # quit_app()
    # client.unlock()
    # time.sleep(3)
    # client.dis_connect()
    sys.exit(app.exec())
