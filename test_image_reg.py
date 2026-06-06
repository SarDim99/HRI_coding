import base64
import cv2
import numpy as np
from autobahn.twisted.util import sleep
from autobahn.twisted.component import Component, run
from twisted.internet.defer import inlineCallbacks
from ultralytics import YOLO

import cv2
import time
from ultralytics import YOLO
from threading import Thread

class object_detect():
    def __init__(self):
        self.model = YOLO("yolov8n.pt") 
        self.cap = cv2.VideoCapture(0)

        self.latest_frame = None
        self.running = True
        self.name = ""
        self.last_infer_time = 0
        self.infer_interval = 0.3

    def reset_name(self):
        self.name = ""

    def get_name(self):
        return self.name

    def grab_frames(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                self.latest_frame = frame


    def run_camera(self):

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
            for box, cls, conf in zip(results[0].boxes.xyxy, results[0].boxes.cls, results[0].boxes.conf):
                self.name = results[0].names[int(cls)]

            annotated = results[0].plot()
            cv2.imshow("YOLO", annotated)

            if cv2.waitKey(1) & 0xFF == ord("q") or self.name != "":
                break

        self.running = False
        self.cap.release()
        cv2.destroyAllWindows()

object_det = object_detect()
object_det.run_camera()

if object_det.get_name() != "":
    print(object_det.get_name())


# def show_camera(frame):
#     if frame is None:
#         raise ValueError("The frame is empty")

#     if not isinstance(frame, dict):
#         raise TypeError("The frame is not a dictionary")

#     frame_single = frame["data"]["body.head.eyes"]
#     frame_single = bytes(frame_single, "utf-8")
#     image_data = base64.b64decode(frame_single)
#     nparr = np.frombuffer(image_data, np.uint8)
#     image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

#     cv2.imshow("Camera Stream", image)
#     cv2.waitKey(100)
#     pass

# def main(session, details):
#     print("test4")
#     yield session.subscribe(show_camera, "rom.sensor.sight.stream")
#     yield session.call("rom.sensor.sight.stream")
#     pass

# wamp = Component(
#     transports=[{
#         "url": "ws://wamp.robotsindeklas.nl",
#         "serializers": ["msgpack"],
#         "max_retries": 0
#     }],
#     realm="rie.6a22750a8a2cba4f82b85cf7",  # !!!!!!! Check this in case of failure to connect!!!!!!
# )

# wamp.on_join(main)

# if __name__ == "__main__":
#     run([wamp])

