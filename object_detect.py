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
    def __init__(self):
        self.model = YOLO("yolov8n.pt") 
        self.cap = cv2.VideoCapture(0)

        self.latest_frame = None
        self.running = False
        self.name = ""
        self.last_infer_time = 0
        self.infer_interval = 0.3

    def reset_name(self):
        # self.latest_frame = None
        self.name = ""
        self.running = True

    def get_name(self):
        return self.name

    def grab_frames(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                self.latest_frame = frame


    def run_camera(self):
        print("nu pas")
        print(self.name)
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
                print(self.name)

            annotated = results[0].plot()
            cv2.imshow("YOLO", annotated)

            if cv2.waitKey(1) & 0xFF == ord("q") or self.name != "":
                print("bye")
                self.running = False
                break

        self.running = False
        self.cap.release()
        cv2.destroyAllWindows()

# object_det = object_detect()
# object_det.run_camera()

# if object_det.get_name() != "":
#     print(object_det.get_name()) 

# exit_conditions = (":q", "quit", "exit")

# finish_dialogue = False
# query = "hello"
# response_text = ""

# def main(session, details):
#     object_det = object_detect()
#     object_det.run_camera()

#     if object_det.get_name() != "":
#         print(object_det.get_name()) 
#     global finish_dialogue, query, response_text

#     yield session.call("rie.dialogue.config.language", lang="en")
#     # robot stand up
#     yield session.call("rom.optional.behavior.play", name="BlocklyStand")

#     # Greet prompt
#     yield session.call("rie.dialogue.say", text="Hello there! I'm Alpha Mini. It's nice to see you!")
#     yield session.call("rom.optional.behavior.play", name="BlocklyWaveRightArm")
#     #yield sleep(1)
#     #yield session.call("rie.dialogue.say", text="You can start a conversation with me whenever you're ready.")

#     # Speech recognition
#     yield session.subscribe(asr, "rie.dialogue.stt.stream")
#     yield session.call("rie.dialogue.stt.stream")

#     # loop until the user says exit or quit
#     dialogue = True
#     # yield session.call("rie.vision.face.find")

#     while dialogue:
        
#         session.call("rie.vision.face.track")

#         if "Bye" in response_text:
#             dialogue = False
#         if finish_dialogue:
#             yield session.call("rie.dialogue.stt.close")
#             yield sleep(1)
#             print("also here ", query)
#             if query in exit_conditions:
#                 dialogue = False
#                 yield session.call("rie.dialogue.say", text="Goodbye! It was nice talking with you. See you again next time.")
#                 yield session.call("rom.optional.behavior.play", name="BlocklyWaveRightArm")
#                 break
#             elif query != "":
#                 response_text = ask_llm(query)
#                 print("response:", response_text)
#                 yield session.call("rie.dialogue.say", text=response_text)
#             else:
#                 yield session.call("rie.dialogue.say", text="sorry, I couldn't hear you")
#             finish_dialogue = False
#             query = ""
#             yield session.call("rie.dialogue.stt.stream")
#         yield sleep(0.5)

#     yield session.call("rie.dialogue.stt.close")
#     yield session.call("rom.optional.behavior.play", name="BlocklyCrouch")
#     session.leave()

# wamp = Component(
#     transports=[
#         {
#             "url": "ws://wamp.robotsindeklas.nl",
#             "serializers": ["json"],
#             "max_retries": 0,
#         }
#     ],
#     realm="rie.6a26b0028a2cba4f82b8706b",
# )

# wamp.on_join(main)

# if __name__ == "__main__":
#     run([wamp])


#play camera of alhpa mini
# @inlineCallbacks
# def behavior(session):
#     yield session.subscribe(show_camera_stream, "rom.sensor.sight.stream")
#     yield session.call("rom.sensor.sight.stream")

#     pass


def main(session, details):
    behavior(session)
    pass


# wamp = Component(
#     transports=[
#         {
#             "url": "ws://wamp.robotsindeklas.nl",
#             "serializers": ["json"],
#             "max_retries": 0,
#         }
#     ],
#     realm="rie.6a26b0028a2cba4f82b8706b",
# )

# wamp.on_join(main)

# if __name__ == "__main__":
#     run([wamp])

