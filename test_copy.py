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

Env = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=Env)

nlp = spacy.load("en_core_web_lg")

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

def get_target():
    animal_list = ["dog", "cat", "elephant", "cow", "horse", "sheep", "zebra", "giraffe", "bear"]
    target = random.choice(animal_list)
    return target

# Movements performed by the robot and picked by the LLM (NEED TO ADD THIS)
MOVEMENTS = {
    "Hello": "BlocklyWaveRightArm",
    "Bye": "BlocklyWaveRightArm",
    "Think": "BlocklyTouchHead",
}

# export OPENAI_API_KEY="API_KEY"
test = os.getenv("OPENAI_API_KEY")
chatbot = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) # Not adding the key due to deactivation when uploaded to github.

current_phase = "intro"
GAME_START_MARKER = "[GAME_START]"

def ask_llm(user_text: str, answer_child) -> str:
    global current_phase
    conversation_history.append({"role": "user", "content": user_text})
    new_game = False
    leave_game = False

    if answer_child:
        answer_child = False
        if wants_replay(user_text):
            reply = "Nice, lets have another round"
            new_game = True
        else:
            leave_game = True
            reply = "Okay! That was so much fun. Bye!"\
    #TODO check if I can remove this for my game
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
    return reply, answer_child, new_game, leave_game


conversation_history: list[dict] = []

# Smoke test on startup
# print(ask_llm("Hello there"))


exit_conditions = (":q", "quit", "exit")

finish_dialogue = False
query = "hello"

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

def wants_replay(child_text):
    r = chatbot.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": REPLAY_PROMPT},
                {"role": "user", "content": child_text}],
        response_format={"type": "json_object"},
    )
    return json.loads(r.choices[0].message.content).get("answer", "no") == "yes"

def check_if_sim(query, last_responses, threshold_sentence_sim):
    sentence1 = nlp(query)
    for response in last_responses:
        sentence2 = nlp(response)
        print("last response:", response)
        print("quary: ", query)
        print("sim: ", sentence1.similarity(sentence2))
        if sentence1.similarity(sentence2) > threshold_sentence_sim:
            print('ja hoger')
            return True
    return False

def queue_response(text, last_responses):
    if len(last_responses) > 1:
        last_responses.pop()
    last_responses.append(text)
    return text, last_responses

@inlineCallbacks
def main(session, details):
    global finish_dialogue, query, response_text

    yield session.call("rie.dialogue.config.language", lang="en")
    # robot stand up
    yield session.call("rom.optional.behavior.play", name="BlocklyStand")

    # Greet prompt
    yield session.call("rie.dialogue.say", text="Hello there! I'm Alpha Mini. It's nice to see you!")
    yield session.call("rom.optional.behavior.play", name="BlocklyWaveRightArm")
    
    #TODO place this somewhere else
    yield session.call("rie.dialogue.say", text="The game works as follows: I ask you to show me an animal and you show my the card that Illustrates that animal")

    # Speech recognition
    yield session.subscribe(asr, "rie.dialogue.stt.stream")
    yield session.call("rie.dialogue.stt.stream")

    # loop until the user says exit or quit
    dialogue = True
    object_det = object_detect()
    get_animal= False
    answer_child = False
    new_game = False
    response_text = ""
    last_responses = []
    threshold_sentence_sim = 0.8

    while dialogue:        
        session.call("rie.vision.face.track")
        if new_game:
            game_dict["is_true"] = False
            game_dict['returned_animal'] = None
            game_dict['target'] = None
            object_det = object_detect()
            new_game = False
            answer_child = False

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
                text, last_responses = queue_response(text="That's correct, good job!", last_responses=last_responses)
                yield session.call("rie.dialogue.say", text=text)
                
            if game_dict["is_true"] == False and game_dict['returned_animal'] != None:
                text, last_responses = queue_response(
                    text=f"Good try! But that is a {game_dict["returned_animal"]}, I choose {game_dict['target']}.",
                    last_responses=last_responses)
                yield session.call("rie.dialogue.say", text=text)

            text, last_responses = queue_response(text="Do you want to play another game?", last_responses=last_responses)
            yield session.call("rie.dialogue.say", text= text)
            answer_child = True

        if "Bye" in response_text:
            dialogue = False
        if finish_dialogue:
            yield session.call("rie.dialogue.stt.close")
            yield sleep(1)
            if query in exit_conditions:
                dialogue = False
                yield session.call("rie.dialogue.say", text="Goodbye! It was nice talking with you. See you again next time.")
                yield session.call("rom.optional.behavior.play", name="BlocklyWaveRightArm")
                break
            elif query != "":
                #check if it lisnt do itself
                if check_if_sim(query, last_responses, threshold_sentence_sim):
                    yield session.call("rie.dialogue.stt.stream")
                    continue

                response_text, answer_child, new_game, leave_game = ask_llm(query, answer_child)
                if leave_game:
                    dialogue = False
                    yield session.call("rie.dialogue.say", text="Goodbye! It was nice talking with you. See you again next time.")
                    yield session.call("rom.optional.behavior.play", name="BlocklyWaveRightArm")
                    break
                text, last_responses = queue_response(text=response_text, last_responses=last_responses)
                yield session.call("rie.dialogue.say", text=text)
            else:
                text, last_responses = queue_response(text="sorry, I couldn't hear you", last_responses=last_responses)
                yield session.call("rie.dialogue.say", text=text)
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
    realm="rie.6a2a9f1b8a2cba4f82b88415",  # !!!!!!! Check this in case of failure to connect!!!!!!
)

wamp.on_join(main)

if __name__ == "__main__":
    run([wamp])

    
