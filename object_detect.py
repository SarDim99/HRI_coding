import base64
import cv2
import numpy as np
from autobahn.twisted.util import sleep
from autobahn.twisted.component import Component, run
from twisted.internet.defer import inlineCallbacks
from ultralytics import YOLO
from alpha_mini_rug import show_camera_stream
import time
from threading import Thread

class object_detect():
    """
    Real-time animal detection using a YOLO model and webcam input.
    """
    def __init__(self):
        self.model = YOLO("yolov8n.pt") 
        self.cap = cv2.VideoCapture(0)

        self.latest_frame = None
        self.running = False
        self.name = ""
        self.last_infer_time = 0
        self.infer_interval = 0.3

    def reset_name(self):
        """
        Reset the detection state to prepare for a new detection round.
        """
        # self.latest_frame = None
        self.name = ""
        self.running = True

    def get_name(self) -> str:
        """
        Retruns name

        Returns:
            str: The current value of name.
        """
        return self.name

    def grab_frames(self):
        """
        Continuously capture frames from the webcam in a background thread.
        """
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                self.latest_frame = frame


    def run_camera(self):
        """
        Start real-time animal detection using the webcam and YOLO model.
        """
        # print("nu pas")
        # print(self.name)
        t = Thread(target=self.grab_frames, daemon=True)
        t.start()

        while True:
            if self.latest_frame is None:
                continue

            now = time.time()

            if now - self.last_infer_time < self.infer_interval:
                continue

            frame = self.latest_frame.copy()
            self.last_infer_time = now

            results = self.model.predict(frame, imgsz=320, conf=0.5, verbose=False, classes = [15, 16, 17, 18, 19, 20, 21, 22, 23, 24])
            for _, cls, _ in zip(results[0].boxes.xyxy, results[0].boxes.cls, results[0].boxes.conf):
                self.name = results[0].names[int(cls)]
                # print(self.name)

            annotated = results[0].plot()
            cv2.imshow("YOLO", annotated)

            if cv2.waitKey(1) & 0xFF == ord("q") or self.name != "":
                # print("bye")
                self.running = False
                break

        self.running = False
        self.cap.release()
        cv2.destroyAllWindows()
