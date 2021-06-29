#!/usr/bin/env python3
import logging
import os
import sched
import sys
import time
from queue import Queue

import cv2
from PyQt5 import QtGui
from PyQt5.QtWidgets import QApplication, QWidget, QMessageBox
# from PyQt5.uic import loadUi
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QThread, QTimer
from PyQt5.QtGui import QIcon
from Carousel_ui import Ui_Form
from QWEBtest import Client, do_quque
from enum import Enum
from CalcDistance import CalcDistance
# import cv2

week = Enum("WEEK", ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"))

MY_VERSION = 1.1
MACHINE = "DVT9"
try:
    with open('./config.txt', "r") as f:
        IP = f.readline().strip()
    if IP == "":
        raise TypeError("IP cannot be empty")
except FileNotFoundError:
    print("请在config.txt文件中添加正确ip")
    exit(-1)
except TypeError as e:
    print("IP 不能为空")
# IP = "10.68.178.127"


class Scheduler(QObject):
    start = pyqtSignal()

    def __init__(self):
        super(Scheduler, self).__init__()
        self.s = sched.scheduler(time.time, time.sleep)
        self.start.connect(self.start_work)

    def start_work(self):

        # After init( dev init , home)
        # 1. unlock cell tray 3s
        # 2. move to 240000 30s
        # 3. clamp 2s
        # 4. move to 180000 20s
        # 5. unclamp 2s
        # 6. move to 260000(lock) 30s
        # 7. move to 180000 20s
        # repeat
        self.s.run()
        print("Finish one cycle task")

    def stop_work(self):
        pass


# class TakeShots(QThread):
#     def __init__(self):
#         super(TakeShots, self).__init__(None)
#
#     def run(self) -> None:
#         for cell in range(4):
#             cap = cv2.VideoCapture(1)
#             ret, frame = cap.read()  # cap.read()返回两个值，第一个存储一个bool值，表示拍摄成功与否。第二个是当前截取的图片帧。
#             cv2.imwrite(f"./cap/capture{cell+1}.jpg", frame)  # 写入图片
#             cap.release()  # 释放

class MainWindow(QWidget, Ui_Form):
    task_finish_trigger = pyqtSignal()

    def __init__(self):
        super(MainWindow, self).__init__(parent=None)
        self.setupUi(self)
        self._init_logger()

        # self.timer_cam = QTimer()
        # self.cap = cv2.VideoCapture()  # 准备获取图像
        # self.CAM_NUM = 1
        # w = loadUi("testmodbus_ui_double.ui", self)
        self.logfile = "data.txt"
        self.logfile_r = "data_r.txt"
        self.cycles = self.get_cycle()
        self.txt_run_all.setText(f"{self.cycles}")
        # self.cycles_r = self.get_cycle()  # right cycle times
        self.emegency_stop = False
        self.task_index = 0
        self.prepare_task_index = 0
        # Web socket config
        self.ws = Client(ip=IP)
        self.q = Queue()
        self.loop_queue = Queue()
        self.th = QThread()
        self.s = sched.scheduler(time.time, time.sleep)
        self.ws.moveToThread(self.th)
        self.q.put((self.ws.connectinst,))
        # self.q.put((self.ws.ase_cmd, "SUBS ERROR", None, "订阅错误"))
        self.th.started.connect(lambda: do_quque(self.q, self.ws))
        QTimer().singleShot(1000, self.th.start)
        self.tasks = self.gen_tasks()
        # self.shots = TakeShots()
        # self.shots.finished.connect(self.enable_button)
        self.setWindowTitle('Carousel Tester ' + MACHINE)
        self.setWindowIcon(QIcon('favicon.ico'))
        self.status = "not init"
        self.running_seq = False
        self.ldt_ip.setText(IP)
        self.btn_start.clicked.connect(self.prepare)
        self.btn_end.setEnabled(False)
        self.btn_end.clicked.connect(self._stop)
        self.btn_bpv_set.clicked.connect(self.manual_set)
        self.btn_cap.setEnabled(False)
        # self.btn_cap.clicked.connect(self.snap_shot)
        self.ws.sigError.connect(self.handle_error)

    def handle_error(self, msg):
        # 设定错误消息
        self._log_info(f"ERROR:{msg}")
        self.txt_error_msg.setText(msg)
        # 检测到设备报错，尝试停止继续
        self._stop()
        # pass

    # def snap_shot(self):  # camera_idx的作用是选择摄像头。如果为0则使用内置摄像头，比如笔记本的摄像头，用1或其他的就是切换摄像头。
    #     self.btn_cap.setEnabled(False)
    #     self.shots.start()
    def calc(self, position):
        camera = cv2.VideoCapture(0)
        return_value, image = camera.read()
        if return_value:
            c = CalcDistance(image)
            ret = c.process()
            if not os.path.isdir(f'{position}'):
                # 创建文件夹
                os.makedirs(f'{position}')
            cv2.imwrite(f'{position}/{time.strftime("%Y-%m-%d-%H_%M_%S",time.localtime(time.time()))}.png', image)
            self._log_info(f'{position} diff: {ret}')
            self.debounce()
            # return ret

        else:
            raise Exception("Cannot take shot")

    def enable_button(self):
        self.btn_cap.setEnabled(True)

    def manual_set(self, is_load):
        position = self.cbx_position.currentText()
        if position == "HOME":
            self.ws.ase_cmd('ASE:COLLECTION_HOME')
        elif position in "ABCDE":
            self.ws.ase_cmd(f"ASE:LOAD_COLLECTION {position}")
        else:
            raise Exception("Unknow position")

    def _stop(self):
        self.emegency_stop = True
        self.btn_end.setText("收尾中")
        self.btn_end.setEnabled(False)

    # region logging functions
    def _init_logger(self):
        self._logger = logging.getLogger('main')
        self._logger.setLevel(logging.DEBUG)
        self._fh = logging.FileHandler('main.log')
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
    def get_cycle(self):

        log = self.logfile
        if not os.path.exists(log):
            with open(log, "w+") as f:
                f.write("0")
                print("没有日志文件，创建并初始化")
                print(f"已经执行次数0")
                return 0
        else:
            with open(log, "r") as f:
                cycles = int(f.readline())
                print(f"已经执行次数{cycles}")
                return cycles

    def save_cycles(self):
        log = self.logfile
        cycles = self.cycles
        cycles += 1

        self.cycles = cycles
        self.txt_run_all.setText(f"{self.cycles}")
        self._log_info(f"cycles:{self.cycles}")
        try:
            with open(log, "w") as f:
                f.write(str(cycles))
                print(f"已经执行次数{cycles}写入文件")
                return cycles
        except IOError as e:
            print("文件无法写入")
            raise e

    def timeout(self):
        raise Exception("Time out")

    def do_next(self):
        if self.loop_queue.empty():
            self.loop_queue.get()

    def prepare(self):
        prep_tasks = [
            {
                "description": "Setting Cap to position 1.",
                "command": "ASE:LOAD_CAP 1"
            },
            {
                "description": "Setting Needle to position 1.",
                "command": "ASE:LOAD_NEEDL 1"
            },
            {
                "description": "Loading cartridge to E.",
                "command": "ASE:LOAD_CARTRIDGE E"
            }]  # prepare tasks
        if self.prepare_task_index == 0:
            self.ws.sigCmdDone.connect(self.prepare)
        if self.prepare_task_index < len(prep_tasks):
            self.add_prepare_task(prep_tasks[self.prepare_task_index])
            self.prepare_task_index += 1
        else:
            self.ws.sigCmdDone.disconnect(self.prepare)
            self.run_task()

    def add_prepare_task(self, task):
        self.txt_current_cmd.setText(
            f'{task["description"]}'
        )
        self.ws.ase_cmd(task["command"])

    def debounce(self, delay=2000):
        QTimer.singleShot(delay, self.run_task)

    @staticmethod
    def gen_tasks():
        # dd = ["cart_home", "cart_e", "go_home", "holder", "cap 1", "cap 3", "needle_4", "cap_1"]
        cd = ["ASE:CARTRIDGE_HOME",
              "ASE:LOAD_CARTRIDGE E",
              "ASE:COLLECTION_HOME",
              "SHOT:HOME",
              "HOLDER",
              "SHOT",
              "ASE:LOAD_CAP 1",
              "ASE:LOAD_CAP 3",
              "ASE:LOAD_NEEDL 4",
              "ASE:LOAD_NEEDL 1",
              "ASE:LOAD_CAP 1"]
        tasks = []
        for group in "ABCDE":
            # dd[3] = "go_" + group
            cd[4] = "ASE:LOAD_COLLECTION " + group
            cd[5] = "SHOT:" + group
            tasks.extend(cd)
        return tasks

    def run_task(self):

        if self.task_index == 0 and self.running_seq:
            # cycle += 1
            self.save_cycles()

        if not self.emegency_stop:
            if not self.running_seq:
                self.btn_start.setEnabled(False)
                self.btn_end.setEnabled(True)
                self.ws.sigCmdDone.connect(self.debounce)
                self.running_seq = True
            task = self.tasks[self.task_index]
            self.add_task(task)
            self.task_index += 1  # Forward next task
            self.task_index %= len(self.tasks)
        else:
            self.emegency_stop = False
            self.ws.sigCmdDone.disconnect(self.debounce)
            # self.ws.close()
            self.txt_current_cmd.setText("已停止")
            self.btn_start.setEnabled(True)
            self.btn_end.setEnabled(False)
            self.btn_end.setText("停止")
            self.running_seq = False
            self._logger.info(f"Emergency stop")

    def add_task(self, task):
        if task.startswith("ASE:"):
            self.txt_current_cmd.setText(
              f'Running { task.replace("ASE:","") }'
            )
            self.ws.ase_cmd(task)
        else:
            self.calc(task.split(":")[1])

    def breakconnection(self):
        self.q.put((self.ws.dis_connect,))
        do_quque(self.q)

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        try:
            self.ws.close()
        except:
            pass



    def warn(self, message):
        QMessageBox.critical(self, "错误", message, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)





if __name__ == '__main__':
    app = QApplication([])
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
