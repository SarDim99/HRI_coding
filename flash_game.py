from autobahn.twisted.component import Component, run
from twisted.internet.defer import inlineCallbacks
from autobahn.twisted.util import sleep
from openai import OpenAI
import os
from dotenv import load_dotenv
from pathlib import Path
from object_detect import object_detect
import json
import random
import spacy

# Env = Path(__file__).resolve().parent / '.env'
# load_dotenv(dotenv_path=Env)

# MODEL_NAME = "gpt-4o-mini"

class flash_card_game():
    def __init__(self, chatbot, model_name):
        print('is gemaakt')
        self.nlp = spacy.load("en_core_web_lg")
        self.chatbot = chatbot
        self.model_name = model_name
        self.game_dict = {
        "returned_animal": None,
        "target": None,
        "is_true": False
        }   
        self.object_det = object_detect()
        self.get_animal= False
        self.answer_child = False
        self.new_game = False
        self.last_responses = []
        self.threshold_sentence_sim = 0.8

    def get_target(self):
        animal_list = ["dog", "cat", "elephant", "cow", "horse", "sheep", "zebra", "giraffe", "bear"]
        target = random.choice(animal_list)
        return target
    
    def get_threshold(self):
        return self.threshold_sentence_sim
    
    def get_last_responses(self):
        return self.last_responses
    
    def get_answer_child(self):
        return self.answer_child
    
    def set_answer_child(self, answer_child):
        self.answer_child = answer_child

    def get_new_game(self):
        return self.new_game
    
    def set_new_game(self, new_game):
        self.new_game = new_game

    def listen_if_child_want_to_play(self, user_text: str, answer_child) -> str:
        new_game = False
        leave_game = False
        reply = ""

        if answer_child:
            answer_child = False
            if self.wants_replay(user_text):
                reply = "Nice, lets have another round"
                new_game = True
            else:
                leave_game = True
                reply = "Okay! That was so much fun. Bye!"
        return reply, answer_child, new_game, leave_game

    def wants_replay(self, child_text):

        REPLAY_PROMPT = (
        "A child was asked if they want to play again.\n"
        'Classify their reply as exactly one of: "yes", "no".\n'
        'Reply with ONE JSON object: {"answer": "yes|no"}'
        )


        r = self.chatbot.chat.completions.create(
            model=self.MODEL_NAME,
            messages=[{"role": "system", "content": REPLAY_PROMPT},
                    {"role": "user", "content": child_text}],
            response_format={"type": "json_object"},
        )
        return json.loads(r.choices[0].message.content).get("answer", "no") == "yes"

    def check_if_sim(self, query, last_responses, threshold_sentence_sim):
        sentence1 = self.nlp(query)
        for response in last_responses:
            sentence2 = self.nlp(response)
            print("last response:", response)
            print("quary: ", query)
            print("sim: ", sentence1.similarity(sentence2))
            if sentence1.similarity(sentence2) > threshold_sentence_sim:
                return True
        return False

    def queue_response(self, text):
        if len(self.last_responses) > 1:
            self.last_responses.pop()
        self.last_responses.append(text)
        return text

    def explaing_game(self, session):
        print('ebgin')
        yield session.call("rie.dialogue.say", 
                           text="The game works as follows: I ask you to show me an animal and you show my the card that Illustrates that animal")


    def play_game(self, session, new_game, answer_child):
        if new_game:
            self.game_dict["is_true"] = False
            self.game_dict['returned_animal'] = None
            self.game_dict['target'] = None
            self.object_det = object_detect()
            self.new_game = False
            self.answer_child = False

        if answer_child == False:
            if self.game_dict['target'] == None:
                self.game_dict['target'] = self.get_target()
                get_animal = True
            yield session.call("rie.dialogue.say", text=f"Can you show me a {self.game_dict["target"]}")

            if self.game_dict["returned_animal"] == None and get_animal == True:
                self.object_det.reset_name()
                self.object_det.run_camera()
                get_animal = False

            if self.object_det.get_name() != "" and self.game_dict['returned_animal'] == None:
                self.game_dict["returned_animal"] = self.object_det.get_name()
                if self.game_dict['returned_animal'] == self.game_dict['target']:
                    self.game_dict["is_true"] = True

            if self.game_dict["is_true"] == True and self.game_dict['returned_animal'] != None:
                text, last_responses = self.queue_response(text="That's correct, good job!", last_responses=last_responses)
                yield session.call("rie.dialogue.say", text=text)
                
            if self.game_dict["is_true"] == False and self.game_dict['returned_animal'] != None:
                text, last_responses = self.queue_response(
                    text=f"Good try! But that is a {self.game_dict["returned_animal"]}, I choose {self.game_dict['target']}.",
                    last_responses=last_responses)
                yield session.call("rie.dialogue.say", text=text)

            text, last_responses = self.queue_response(text="Do you want to play another game?", last_responses=last_responses)
            yield session.call("rie.dialogue.say", text= text)
            answer_child = True

        return answer_child, new_game
    # @inlineCallbacks
    # def main(self, session, details):
    #     while True:
    #         yield session.call("rie.dialogue.say", text=f"saysomething")

# @inlineCallbacks
# def main(session, details):
#     global finish_dialogue, query, response_text

#     yield session.call("rie.dialogue.config.language", lang="en")
#     # robot stand up
#     yield session.call("rom.optional.behavior.play", name="BlocklyStand")

#     # Greet prompt
#     yield session.call("rie.dialogue.say", text="Hello there! I'm Alpha Mini. It's nice to see you!")
#     yield session.call("rom.optional.behavior.play", name="BlocklyWaveRightArm")
    

#     # Speech recognition
#     yield session.subscribe(asr, "rie.dialogue.stt.stream")
#     yield session.call("rie.dialogue.stt.stream")

    # loop until the user says exit or quit
    # dialogue = True
    # object_det = object_detect()
    # get_animal= False
    # answer_child = False
    # new_game = False
    # response_text = ""
    # last_responses = []
    # threshold_sentence_sim = 0.8

#     while dialogue:        
#         session.call("rie.vision.face.track")
        
#         play_game(session, new_game, answer_child)

#         if "Bye" in response_text:
#             dialogue = False
#         if finish_dialogue:
#             yield session.call("rie.dialogue.stt.close")
#             yield sleep(1)
#             if query in exit_conditions:
#                 dialogue = False
#                 yield session.call("rie.dialogue.say", text="Goodbye! It was nice talking with you. See you again next time.")
#                 yield session.call("rom.optional.behavior.play", name="BlocklyWaveRightArm")
#                 break
#             elif query != "":
#                 #check if it lisnt do itself
#                 if check_if_sim(query, last_responses, threshold_sentence_sim):
#                     yield session.call("rie.dialogue.stt.stream")
#                     query = ""
#                     yield sleep(0.5)
#                     continue

#                 response_text, answer_child, new_game, leave_game = listen_if_child_want_to_play(query, answer_child)
#                 if leave_game:
#                     dialogue = False
#                     yield session.call("rie.dialogue.say", text="Goodbye! It was nice talking with you. See you again next time.")
#                     yield session.call("rom.optional.behavior.play", name="BlocklyWaveRightArm")
#                     break
#                 text, last_responses = queue_response(text=response_text, last_responses=last_responses)
#                 yield session.call("rie.dialogue.say", text=text)
#             else:
#                 text, last_responses = queue_response(text="sorry, I couldn't hear you", last_responses=last_responses)
#                 yield session.call("rie.dialogue.say", text=text)
#             finish_dialogue = False
#             query = ""
#             yield session.call("rie.dialogue.stt.stream")
#         yield sleep(0.5)

#     yield session.call("rie.dialogue.stt.close")
#     yield session.call("rom.optional.behavior.play", name="BlocklyCrouch")
#     session.leave()

# wamp = Component(
#     transports=[{
#         "url": "ws://wamp.robotsindeklas.nl",
#         "serializers": ["msgpack"],
#         "max_retries": 0
#     }],
#     realm="rie.6a2c15248a2cba4f82b88a8e"",  # !!!!!!! Check this in case of failure to connect!!!!!!
# )

# wamp.on_join(main)