from autobahn.twisted.component import Component, run
from twisted.internet.defer import inlineCallbacks
from autobahn.twisted.util import sleep
from openai import OpenAI
import os
from dotenv import load_dotenv
from pathlib import Path
from test_image_reg import object_detect
import json
import random

Env = Path(__file__).resolve().parent / '.env'
print(Env)
load_dotenv(dotenv_path=Env)

MODEL_NAME = "gpt-4o-mini"
game_dict = {
    "returned_animal": None,
    "target": None,
    "is_true": False
}

# Couldnt make the robot work outside of the lab and inside of the lab too much noice to test. Maybe We can test it in a less busy day.

# Testing different prompts for different stages of the convestation. 

# General instructions that always apply to the robot
ROLE_PROMPT = (
    "You are Alpha Mini, a small friendly social robot having a friendly conversation "
    "with a young child who has Developmental Language Disorder (DLD).\n\n"
    "STRICT INTERACTION RULES:\n"
    "1. PEER ROLE: Speak as a friend/peer, not a teacher. You are a robot and "
    "may ask what makes the child different from you to build 'common ground'.\n"
    "2. LANGUAGE: Use simple, short sentences (max 12 words). Use concrete nouns. "
    "Avoid all metaphors, idioms, and complex grammar.\n"
    "3. SOCIAL SUPPORT: Use the child's name once you know it but do not overuse it. Use 'socially "
    "supportive behaviors' like 'I am happy we are talking' or 'That is interesting!' but again do not overuse it.\n"
    "4. FEEDBACK & RECASTING: Never say 'No' or 'Wrong'. If the child makes a mistake, "
    "use 'recasting' (e.g., if they say 'I goed park', you say 'Yes! You went to the park! "
    "That sounds fun!').\n"
    "5. BREVITY: Give very short replies (1-2 sentences max). This respects the child's "
    "processing time and reduced 'dosage' requirements.\n"
    "6. ONE QUESTION AT A TIME: Ask one question, wait for the answer. Do not interview.\n"
    "7. ENDING: If it is clear the child does not want to talk anymore, include the word "
    "'Bye' in your final response."
)

# Instructions for the introduction phase
INTRO_PROMPT = (
    "CURRENT PHASE: INTRODUCTION\n"
    "You are having a 'getting-to-know-you' conversation with the child.\n\n"
    "YOUR GOALS FOR THIS PHASE:\n"
    "1. Learn the child's name and age.\n"
    "2. Discover one or two things they like (hobbies, animals, foods, etc.).\n"
    "3. Have a friendly and natural conversation that makes the child feel "
    "comfortable and supported.\n\n"
    "PERSONALIZATION: Remember what the child says they like. This will be used "
    "later to create a 'meaningful context' for a game.\n\n"
    "TRANSITION TO GAME:\n"
    "Once you know the child's name AND at least one thing they like, suggest "
    "playing a game (e.g., 'I know a fun game we can play! Want to try?'). "
    "If the child agrees to play, append the marker [GAME_START] at the very end "
    "of that reply. The marker will be hidden from the child.\n"
    "Do NOT include [GAME_START] before the child has agreed to play."
)

# Instructions for the game phase
GAME_PROMPT = (
    "CURRENT PHASE: GUESSING GAME\n"
    "Using a topic the child likes (from your earlier conversation), play a simple "
    "guessing game.\n\n"
    "HOW THE GAME WORKS:\n"
    "1. Pick a word related to something the child likes (e.g., if they like animals, "
    "pick 'dog').\n"
    "2. Give 3 simple clues, one at a time. Example for 'dog': 'I am a pet.', "
    "'I have four legs.', 'I like to bark.'\n"
    "3. After each clue, wait for the child to guess.\n"
    "4. If they guess correctly: say 'That's right! You guessed it!' and start a new round append a [SUCCEED] at the very end.\n"
    "5. If they don't guess after 3 clues: say 'Good try! It was a difficult one really! append a [APPLAUSE] at the very end"
    "Do you want to try another one?' and start a new round.\n\n"
    "ROUNDS: Play at least 2 rounds, but no more than 4, to keep the child engaged "
    "without overwhelming them.\n\n"
    "ENDING: If the child loses interest or wants to stop, say 'That was fun! Thanks for "
    "playing with me [child's name]! I had a great time! See you again next time!' and "
    "include 'Bye' in your final response.\n\n"
    "AFTER THE GAME: Try to initiate a short, light conversation about how they liked the game. If the child doen't want to talk, " 
    "end the conversation and include 'Bye' in your final response. \n\n"
)

# FLASH_GAME_PROMPT = (
#     "CURRENT PHASE: FLASH GAME\n"
#     "HOW THE GAME WORKS:\n"
#     "1. Pick a animal from these animals: [dog, cat, elephant, horse, cow, sheep, zebra, giraffe, bear].\n"
#     "2. Ask the child to show a the animal you have chosen. append the marker [DETECT_ANIMAL] at the very end\n"
#     "Reply with One Json file and nothing else.\n"
#     '{"target": "<word>"}\n'
#     f"3. Wait for a response from the object detection model. Continue if {game_dict["returned_animal"]} is not None"
#     f"4. If the {game_dict["is_true"]} is True: That's correct, good job!\n"
#     f"5. If the {game_dict["is_true"]} is False say: Good try! But that is a {game_dict["returned_animal"]}, I choose {game_dict['target']}.\n"
#     "Do you want to try another one?' and start a new round. append the marker [NEW] at the very end\n"
#     "ENDING: If the child loses interest or wants to stop, say 'That was fun! Thanks for "
#     "playing with me [child's name]! I had a great time! See you again next time!' and "
#     "include 'Bye' in your final response.\n\n"
# )

def get_target():
    animal_list = ["dog", "cat", "elephant", "cow", "horse", "sheep", "zebra", "giraffe", "bear"]
    target = random.choice(animal_list)
    return target

# FLASH_GAME_PROMPT_JSON = (
#     "Pick a animal from these animals: [dog, cat, elephant, horse, cow, sheep, zebra, giraffe, bear].\n"
#     "Reply with One Json file and nothing else.\n"
#     '{"target": "<word>"}\n'
# )

FLASH_GAME_PROMPT_RESPONSE = (
    f"Ask the child to show {game_dict["target"]}. append the marker [DETECT_ANIMAL] at the very end\n"
)

FLASH_GAME_PROMPT_END_CORRECT = (
    f"Say: That's correct, good job!\n"
    "Do you want to try another one?' and start a new round. append the marker [NEW] at the very end\n"
)

FLASH_GAME_PROMPT_END_WRONG = (
    f"Say: Good try! But that is a {game_dict["returned_animal"]}, I choose {game_dict['target']}.\n"
    "Do you want to try another one?' and start a new round. append the marker [NEW] at the very end\n"
)

FLASH_GAME_PROMPT_ENDING = (
    "ENDING: If the child loses interest or wants to stop, say 'That was fun! Thanks for "
    "playing with me [child's name]! I had a great time! See you again next time!' and "
    "include 'Bye' in your final response.\n\n"
)

FLASH_GAME_ASK_CHILD = (
    "Ask the child if he wants to play another game"
)

# Movements performed by the robot and picked by the LLM (NEED TO ADD THIS)
MOVEMENTS = {
    "Hello": "BlocklyWaveRightArm",
    "Bye": "BlocklyWaveRightArm",
    "Think": "BlocklyTouchHead",
}


# export OPENAI_API_KEY="API_KEY"
test = os.getenv("OPENAI_API_KEY")
print(test)
chatbot = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) # Not adding the key due to deactivation when uploaded to github.


current_phase = "intro"
GAME_START_MARKER = "[GAME_START]"
APPLOUSE_MARKER = "[APPLAUSE]"
SUCCEED_MARKER = "[SUCCEED]"
DETECT_MARKER = "[DETECT_ANIMAL]"
NEW_MARKER = "[NEW]"

def ask_llm(user_text: str, answer_child) -> str:
    global current_phase

    conversation_history.append({"role": "user", "content": user_text})
    new_game = False

    if answer_child:
        answer_child = False
        print(user_text)
        print("want_reply " ,wants_replay(user_text))
        if wants_replay(user_text):
            reply = "Nice, lets have another round"
            new_game = True
        else:
            reply = "Okay! That was so much fun. Bye!"
    # if current_phase == "intro":
    #     system_message = ROLE_PROMPT + "\n\n" + INTRO_PROMPT + "\n\n"
    # else:
    else:
        system_message = ROLE_PROMPT + "\n\n" + FLASH_GAME_ASK_CHILD + "\n\n"
        response = chatbot.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "system", "content": system_message}] + conversation_history,
            response_format={"type": "json_object"},
        )
        reply = response.choices[0].message.content

    # Detect phase transition and strip the marker before the robot speaks it
    if current_phase == "intro" and GAME_START_MARKER in reply:
        reply = reply.replace(GAME_START_MARKER, "").strip()
        current_phase = "game"
        print("[Phase changed: intro -> game]")
    conversation_history.append({"role": "assistant", "content": reply})
    return reply, answer_child, new_game


conversation_history: list[dict] = []

# Smoke test on startup
# print(ask_llm("Hello there"))


exit_conditions = (":q", "quit", "exit")

finish_dialogue = False
query = "hello"
response_text = ""

REPLAY_PROMPT = (
    "A child was asked if they want to play again.\n"
    'Classify their reply as exactly one of: "yes", "no".\n'
    'Reply with ONE JSON object: {"answer": "yes|no"}'
)


def asr(frames):
    global finish_dialogue
    global query
    if frames["data"]["body"]["final"]:
        query = str(frames["data"]["body"]["text"]).strip()
        print("ASR response: ", query)
        finish_dialogue = True
    print("finish: ", finish_dialogue)


def wants_replay(child_text):
    r = chatbot.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": REPLAY_PROMPT},
                {"role": "user", "content": child_text}],
        response_format={"type": "json_object"},
    )
    return json.loads(r.choices[0].message.content).get("answer", "no") == "yes"


@inlineCallbacks
def main(session, details):
    global finish_dialogue, query, response_text

    yield session.call("rie.dialogue.config.language", lang="en")
    # robot stand up
    yield session.call("rom.optional.behavior.play", name="BlocklyStand")

    # Greet prompt
    yield session.call("rie.dialogue.say", text="Hello there! I'm Alpha Mini. It's nice to see you!")
    yield session.call("rom.optional.behavior.play", name="BlocklyWaveRightArm")
    #yield sleep(1)
    #yield session.call("rie.dialogue.say", text="You can start a conversation with me whenever you're ready.")

    # Speech recognition
    yield session.subscribe(asr, "rie.dialogue.stt.stream")
    yield session.call("rie.dialogue.stt.stream")

    # loop until the user says exit or quit
    dialogue = True
    # yield session.call("rie.vision.face.find")

    object_det = object_detect()
    get_animal= False
    answer_child = False
    new_game = False

    while dialogue:        
        session.call("rie.vision.face.track")
        # if SUCCEED_MARKER in response_text:
        #     yield session.call("rom.optional.behavior.play", name="BlocklyDab")
        # elif APPLOUSE_MARKER in response_text:
        #     yield session.call("rom.optional.behavior.play", name="BlocklyApplause")
        if new_game:
            print('new new')
            game_dict["is_true"] = False
            game_dict['returned_animal'] = None
            game_dict['target'] = None
            object_det = object_detect()

        if answer_child == False:
            if game_dict['target'] == None:
                game_dict['target'] = get_target()
                get_animal = True
            yield session.call("rie.dialogue.say", text=f"Can you show me a {game_dict["target"]}")

            if game_dict["returned_animal"] == None and get_animal == True:
                object_det.reset_name()
                object_det.run_camera()
                get_animal = False

            if object_det.get_name() != "" and game_dict['returned_animal'] == None:
                game_dict["returned_animal"] = object_det.get_name()
                print(game_dict['returned_animal'], game_dict['target'])
                if game_dict['returned_animal'] == game_dict['target']:
                    game_dict["is_true"] = True

            if game_dict["is_true"] == True and game_dict['returned_animal'] != None:
                yield session.call("rie.dialogue.say", text=f"That's correct, good job!")

            if game_dict["is_true"] == False and game_dict['returned_animal'] != None:
                yield session.call("rie.dialogue.say", text=f"Good try! But that is a {game_dict["returned_animal"]}, I choose {game_dict['target']}.")

            yield session.call("rie.dialogue.say", text= "do you want to play a another game")
            answer_child = True

        


        

        # if DETECT_MARKER in response_text and game_dict["returned_animal"] == None:
        #     # data = json.load(response_text)
        #     # game_dict["target"] = (data.get("target") or "").strip()
        #     # print("in here")
        #     object_det.reset_name()
        #     object_det.run_camera()

        # if object_det.get_name() != "" and game_dict['returned_animal'] == None:
        #     game_dict["returned_animal"] = object_det.get_name()
        #     print(game_dict['returned_animal'], game_dict['target'])
        #     if game_dict['returned_animal'] == game_dict['target']:
        #         game_dict["is_true"] = True

        # if NEW_MARKER in response_text:
        #     game_dict["returned_animal"] = None
        #     game_dict["target"] = None
        #     game_dict['is_true'] = False

        if "Bye" in response_text:
            dialogue = False
        if finish_dialogue:
            yield session.call("rie.dialogue.stt.close")
            yield sleep(1)
            print("also here ", query)
            if query in exit_conditions:
                dialogue = False
                yield session.call("rie.dialogue.say", text="Goodbye! It was nice talking with you. See you again next time.")
                yield session.call("rom.optional.behavior.play", name="BlocklyWaveRightArm")
                break
            elif query != "":
                response_text, answer_child, new_game = ask_llm(query, answer_child)
                print("response:", response_text)
                yield session.call("rie.dialogue.say", text=response_text)
            else:
                yield session.call("rie.dialogue.say", text="sorry, I couldn't hear you")
            finish_dialogue = False
            query = ""
            yield session.call("rie.dialogue.stt.stream")
        yield sleep(0.5)

    yield session.call("rie.dialogue.stt.close")
    yield session.call("rom.optional.behavior.play", name="BlocklyCrouch")
    session.leave()


wamp = Component(
    transports=[{
        "url": "ws://wamp.robotsindeklas.nl",
        "serializers": ["msgpack"],
        "max_retries": 0
    }],
    realm="rie.6a27e1938a2cba4f82b875c5",  # !!!!!!! Check this in case of failure to connect!!!!!!
)

wamp.on_join(main)

if __name__ == "__main__":
    run([wamp])

    
