# coding=utf-8

import socket
import json
import traceback
import queue
import threading
import time
import traceback

class Listener:

    paused: bool

    __host: str
    __port: int
    __socket_: socket.socket | None
    __client_socket : socket.socket| None
    __plugin_version: str | None

    __should_stop : threading.Event
    __buffered_payloads : queue.Queue[int]
    __listener_thread: threading.Thread
    __checker_thread: threading.Thread

    __data_checker_thread: threading.Thread

    def __init__(self, port: int, plugin_version : str|None = None):

        self.paused = True

        self.__port = port
        self.__host = 'localhost'
        self.__socket_ = None
        self.__client_socket = None

        self.__plugin_version = plugin_version

        self.__should_stop = threading.Event()
        self.__buffered_payloads = queue.Queue()
    
    def __create_socket(self):
        if not self.__socket_:
            self.__socket_ = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.__socket_.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.__socket_.bind((self.__host, self.__port))
        else:
            print("Fab: Existing socket, not recreating it")
    
    def __receive_data(self) -> bytes | None:
        if self.__client_socket is not None:
            buffer_size = 4096*2
            data = self.__client_socket.recv(buffer_size)
            return data
        else:
            print("Fab: The client socket does not exist, cannot listen to incoming data")
    
    def __listen_in_thread(self):
        try:
            self.__create_socket()
            print(f"Fab plugin active{(' (v' + self.__plugin_version + ')') if self.__plugin_version else ''}, awaiting data on port {self.__port}")
            while not self.__should_stop.is_set():

                self.__socket_.listen(5)
                self.__client_socket, _ = self.__socket_.accept()
                data = self.__receive_data()
                
                if data == b'Bye Fab':
                    print(f"Fab: Received stop signal")
                    self.__should_stop.set()
                    break
                elif data == b"" or data == b"ping":
                    print(f"Fab: Received a ping")
                    self.__client_socket.sendall(str.encode("{'plugin_version': '" + self.__plugin_version + "'}"))
                else:
                    print(f"Fab: Data received on port {self.__port}")
                    buffered_data = b""
                    buffered_data += data
                    while not self.__should_stop.is_set():
                        if (data := self.__receive_data()) is None:
                            break
                        if data :
                            buffered_data += data
                        else:
                            try:
                                d = json.loads(buffered_data)
                                self.__add_payload_to_queue(d)
                                print("Fab: Payload added to queue")
                            except:
                                print(f"Fab: Did not manage to convert the data received into a json payload")
                                print(f"Fab: data received = {buffered_data}")
                                print(traceback.format_exc())
                            break
            print("Fab: Stopped listening, this should not happen")
        except Exception as e:
            print(f"Fab: Error listening to incoming data on port {self.__port}")
            print(traceback.format_exc())

    def __check_mainthread_alive(self):
        while not self.__should_stop.is_set():
            if self.__should_stop.wait(1):
                break
            for thread in threading.enumerate():
                if(thread.getName() == "MainThread" and thread.is_alive() == False):
                    self.__should_stop.set()

    def __add_payload_to_queue(self, payload):
        self.__buffered_payloads.put(payload)

    def __check_for_data_in_thread(self, callback, interval_seconds):
        while not self.__should_stop.is_set():
            if self.__should_stop.wait(interval_seconds):
                break
            callback()

    def check_for_new_data_at_interval(self, callback, interval_seconds):
        self.__data_checker_thread = threading.Thread(target = self.__check_for_data_in_thread, args=(callback, interval_seconds), daemon=True)
        self.__data_checker_thread.start()

    def start(self):
        self.paused = False
        self.__should_stop.clear()
        self.__listener_thread = threading.Thread(target = self.__listen_in_thread, daemon=True)
        self.__checker_thread = threading.Thread(target = self.__check_mainthread_alive, daemon=True)
        self.__listener_thread.start()
        self.__checker_thread.start()
        self.__data_checker_thread = None

    def pause(self):
        print("Fab: pausing the listener")
        self.paused = True
        self.__should_stop.set()
        if not self.__should_stop.wait(0.1):
            self.__listener_thread.join()
            self.__checker_thread.join()
            if self.__data_checker_thread and self.__data_checker_thread.is_alive():
                self.__data_checker_thread.join()

    def payload(self):
        return None if self.__buffered_payloads.empty() else self.__buffered_payloads.get()

class CallbackLogger:

    def __init__(self, name:str, version:str, port:int = 24563, callback = print):
        self.app_name = name
        self.app_version = version
        self.host = "localhost"
        self.callback = callback

        # Options set according to received payloads
        self.port = 24563
        self.id = "unknown"
        self.path = "unknown"
        self.plugin_version = "unknown"
        self.renderer = "unknown"

    def set_options(self, id:str|None = None, path:str|None = None, port:int|None = None, plugin_version:str|None = None, renderer:str|None = None):
        if id: self.id = id
        if path: self.path = path
        if port: self.port = port
        if plugin_version: self.plugin_version = plugin_version
        if renderer: self.renderer = renderer

    def send_data(self, data, timeout=0.1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.settimeout(timeout)
                s.connect((self.host, self.port))
                # Null terminate the string we'll send
                string_data = json.dumps(data) + "\0"
                s.sendall(string_data.encode())
                print(f"Sent data '{string_data}'")
                return True
            except Exception as e:
                # TODO: we could handle the exception better here
                print("An error occured while sending data back to launcher")
                print(traceback.format_exc())
                return False
        return False

    def log(self, status="success", message=""):
        if status not in ["success", "warning", "error", "critical"]:
            print("Fab: log status should be one of success, warning or error")
            return
        # TODO: this is just to cover a previous mismatch, we'd need to update in DCCs
        if status == "error": status = "critical"
        if not self.send_data({
            "status": status,
            "message": message,
            "id": self.id,
            "path": self.path,
            "app_name": self.app_name,
            "app_version": self.app_version,
            "plugin_version": self.plugin_version,
            "renderer": self.renderer
        }):
            print(f"Fab: Did not send log message back to main app at {self.host}:{self.port}")
            print("This should only happen in debugging environments")
        else:
            try:
                self.callback(status, message)
            except Exception as e:
                print(f"{status}: {message}")
