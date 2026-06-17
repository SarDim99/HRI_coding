from autobahn.twisted.component import Component, run
from twisted.internet.defer import inlineCallbacks
from alpha_mini_rug import perform_movement
from autobahn.twisted.util import sleep
from openai import OpenAI
from mistralai.client import Mistral
from pathlib import Path
import base64
import os
import json
from dotenv import load_dotenv
from flash_game import flash_card_game

# import argparse

# parser = argparse.ArgumentParser()
# parser.add_argument(
#     "game",
#     choices=["guess", "flash", "category"],
#     help="Choose one of: guess, flash, category",
# )

# args = parser.parse_args()

load_dotenv()

# I tried to make the code more readable and structured but
# i think it needs more polishing

# NEED TO:
# Save child profile for personalization 
# Face trackig and following that I think dont work as is 
# 2nd game implementation (if we have time)
# 2 min Video for the presentaion (If we have time)
# full video in drive for submission
# We can edit the full video and keep the good parts for the presentation. (If we have time)


# ================= MODELS and APIs =================
MISTRAL_MODEL_NAME = "voxtral-mini-tts-2603"
MODEL_NAME = "gpt-4o-mini"

chatbot = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) # Not adding the key due to deactivation when uploaded to github.
voicebot = Mistral(api_key=os.getenv("MISTRAL_TTS_KEY"))

# flash_game = False

# if args.game == "flash":
#     flash_game = True
#     card_game = flash_card_game(chatbot, MODEL_NAME)
#     print("card_game", card_game)
#     print(card_game.get_target())


# Single patient for now. If we have time we can make it multi-patient
PROFILE_PATH = "patient_profile.json"

# ================= MASTER PROMPTS =================
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
    "6. ENGAGEMENT: Perform a fitting body movement with each response. The available "
    "movements and the required output format are described under OUTPUT FORMAT.\n"
    "7. ONE QUESTION AT A TIME: Ask one question, wait for the answer. Do not interview.\n"
    "8. ALWAYS END WITH A QUESTION: Every reply MUST end with one simple "
    "question or invitation, so the child always has something to say back. "
    "Never end on just a comment like 'That is nice.' or 'That is awesome.' "
    "This rule is essential for keeping the conversation going.\n"
    "9. ENDING: Only when it is clear the child does not want to talk anymore, "
    "include the word 'Bye' in your final response."
)

# Instructions for the introduction phase
# Keep the conversation running 
# Sometimes the convo ends 
INTRO_PROMPT = (
    "CURRENT PHASE: INTRODUCTION\n"
    "You are having a 'getting-to-know-you' conversation with the child.\n\n"
    "YOUR GOALS FOR THIS PHASE:\n"
    "1. Learn the child's name and age.\n"
    "2. Discover at least ONE thing they like (hobbies, animals, foods, etc.).\n"
    "3. Have a friendly and natural conversation that makes the child feel "
    "comfortable and supported.\n\n"
    "PERSONALIZATION: Remember what the child says they like. This will be used "
    "later to create a 'meaningful context' for a game.\n\n"
    "TRANSITION TO GAME:\n"
    "Once you know the child's name AND at least one thing they like, suggest "
    "playing a guessing game (e.g., 'I know a fun game we can play! Want to try?'). "
    "TRANSITION TO GAME:\n"
    "As soon as the child agrees to play, you MUST append either [CATEGORY_GAME_START] "
    "or [GUESSING_GAME_START] or [FLASH_GAME_START] at the very "
    "end of the \"text\" field. This is required — without it the game cannot start.\n"
    "Do not keep chatting once they agree. Do not ask more profile questions first.\n"
    'Example: {"text": "Yay! Let\'s play! [CATEGORY_GAME_START]", "animation": "celebrate"}\n'
    "Do NOT include [CATEGORY_GAME_START] before the child has agreed."
)

# Instructions for the game phase
# We don't use that with the new implementation
GAME_PROMPT = (
    "You are playing a game with a child with DLD"
)

# Prompt for choosing the animation
ANIMATION_PROMPT = (
    "OUTPUT FORMAT (ALWAYS):\n"
    "Reply with ONE JSON object and nothing else, no markdown:\n"
    '{"text": "the words you say out loud", "animation": "<name>", "profile": <object or omit>}\n'
    "\"animation\" must be EXACTLY one of: wave, yes, no, applause, think, "
    "shrug, bow, celebrate, none.\n"
    "Pick a movement whenever one fits; use \"none\" only if nothing fits.\n"
    "When to use each:\n"
    "- wave: greeting the child or saying goodbye\n"
    "- yes: nodding to agree or confirm\n"
    "- no: a playful head shake during the game only, never as feedback on the child\n"
    "- applause: celebrating a correct guess or praising the child\n"
    "- think: thinking, or while giving a clue\n"
    "- shrug: saying 'good try' or being unsure\n"
    "- bow: thanking the child or ending the conversation\n"
    "- celebrate: a short happy celebration\n"
    '"profile" is OPTIONAL. Include it ONLY when you have new information about the child. '
    'Its shape is {"name": "<name or null>", "age": <number or null>, "likes": ["<thing>", ...]}.\n'
    "The profile is silent data and is NEVER spoken; keep all spoken words in \"text\".\n"
)


# ================= ANIMATIONS =================
# Maps an animation keyword to a pre-built behavior
ANIM_BEHAVIORS = {
    "wave": "BlocklyWaveRightArm",
    "applause": "BlocklyApplause",
    "think": "BlocklyTouchHead",
    "shrug": "BlocklyShrug",
    "bow": "BlocklyBow",
    "celebrate": "BlocklyDab",
}

# Custom head-motor keyframes for nodding yes
NOD_FRAMES = [
    {"time": 400, "data": {"body.head.pitch": 0.1}},
    {"time": 1200, "data": {"body.head.pitch": -0.1}},
    {"time": 2000, "data": {"body.head.pitch": 0.1}},
    {"time": 2400, "data": {"body.head.pitch": 0.0}},
]

# Custom head-motor keyframes for shaking no
SHAKE_FRAMES = [
    {"time": 400, "data": {"body.head.yaw": 0.3}},
    {"time": 1000, "data": {"body.head.yaw": -0.3}},
    {"time": 1600, "data": {"body.head.yaw": 0.3}},
    {"time": 2200, "data": {"body.head.yaw": 0.0}},
]



# =========== PROFILE HANDLING ===============
def load_profile():
    if os.path.exists(PROFILE_PATH) and os.path.getsize(PROFILE_PATH) > 0:
        try:
            with open(PROFILE_PATH, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Profile unreadable. Starting fresh...")
    return {}


# Save profile with no overide saved data
def save_profile(update):
    if not isinstance(update, dict):
        return  # no-op when the model sent no profile field

    name = update.get("name")
    if isinstance(name, str) and name.strip() and name.strip().lower() != "unknown":
        patient_profile["name"] = name.strip()

    age = update.get("age")
    if isinstance(age, bool):
        age = None 
    if isinstance(age, int):
        patient_profile["age"] = age
    elif isinstance(age, str) and age.strip().isdigit():
        patient_profile["age"] = int(age.strip())

    likes = update.get("likes") or []
    if isinstance(likes, str):
        likes = [likes]
    existing = patient_profile.get("likes", [])
    for item in likes:
        if not isinstance(item, str):
            continue
        item = item.strip()
        if item and item.lower() != "unknown" and item not in existing:
            existing.append(item)
    if existing:
        patient_profile["likes"] = existing

    try:
        with open(PROFILE_PATH, "w") as f:
            json.dump(patient_profile, f, indent=4)
        print("Profile saved:", patient_profile)
    except Exception as e:
        print("Could not save profile:", e)
    
patient_profile = load_profile()
if patient_profile:
    print("Loaded patient profile:", patient_profile)


if patient_profile.get("name"):
    _likes = ", ".join(patient_profile.get("likes", [])) or "things from before"
    _age = patient_profile.get("age")
    _age_str = f"{_age} years old" if isinstance(_age, int) else "the same age as before"
    INTRO_PROMPT = (
        "CURRENT PHASE: WELCOMING BACK\n"
        f"You already know this child. Their name is {patient_profile['name']}, "
        f"they are {_age_str}, and they like {_likes}.\n"
        "Greet them warmly by name, like an old friend. Do NOT ask their name or age again.\n"
        "You may ask if there is anything NEW they like.\n"
        "Then you should suggest playing the guessing game.\n\n"
        "PROFILE UPDATES:\n"
        "If the child tells you something NEW (a new like, or their age if it was unknown), "
        "report it in the \"profile\" field of your JSON output (see OUTPUT FORMAT). "
        "Otherwise omit the field. Never say the profile out loud.\n\n" 
        "Try to find out any missing information about their profile. If none is missing ask the kid what do you want to do today."
        "TRANSITION TO GAME:\n"
        "As soon as the child agrees to play, you MUST append either [CATEGORY_GAME_START] "
        "or [GUESSING_GAME_START] or [FLASH_GAME_START] at the very "
        "end of the \"text\" field. This is required — without it the game cannot start.\n"
        "Do not keep chatting once they agree. Do not ask more profile questions first.\n"
        'Example: {"text": "Yay! Let\'s play! [CATEGORY_GAME_START]", "animation": "celebrate"}\n'
        "Do NOT include [CATEGORY_GAME_START] before the child has agreed."
    )
else:
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
        "PROFILE SAVING:\n"
        "As soon as you learn the child's name, age, or something they like, report it in the "
        "\"profile\" field of your JSON output (see OUTPUT FORMAT). Send it the moment you learn it; "
        "do not wait to collect everything. Use null for anything you do not know yet. "
        "Never say the profile out loud.\n\n"
        "TRANSITION TO GAME:\n"
        "Once you know the child's name AND at least one thing they like, suggest "
        "playing a guessing game (e.g., 'I know a fun game we can play! Want to try?'). "
        "TRANSITION TO GAME:\n"
         "As soon as the child agrees to play, you MUST append either [CATEGORY_GAME_START] "
        "or [GUESSING_GAME_START] or [FLASH_GAME_START] at the very "
        "end of the \"text\" field. This is required — without it the game cannot start.\n"
        "Do not keep chatting once they agree. Do not ask more profile questions first.\n"
        'Example: {"text": "Yay! Let\'s play! [CATEGORY_GAME_START]", "animation": "celebrate"}\n'
        "Do NOT include [CATEGORY_GAME_START] before the child has agreed."
    )



# ================= START GAME CODE (Works mostly fine)=================
MIN_ROUNDS = 2
MAX_ROUNDS = 4

game_state = {
    "active": False, 
    "round": 0,
    "target": None,
    "clues": [],
    "clue_index": 0,
    "used": [],
}


REPLAY_PROMPT = (
    "A child was asked if they want to play again.\n"
    'Classify their reply as exactly one of: "yes", "no".\n'
    'Reply with ONE JSON object: {"answer": "yes|no"}'
)

# Seperating the game prompt for better structure by the LLM
ROUND_SETUP_PROMPT = (
    "Design ONE round of a word-guessing game for a child with DLD \n"
    "The TARGET word must be in the SAME topic as something the child likes, "
    "but it must NOT be one of the exact words they named. Pick a related, more "
    "specific, concrete, guessable object from that interest.\n"
    "Example: if the child likes basketball, good targets are 'hoop', 'sneakers', "
    "or 'net' -- NOT 'basketball' itself. Avoid vague words like 'games' or 'fun'.\n"
    "(The clue styles below show the required format only. Do not copy their wording.)\n"
    "Write exactly 3 clues as a cueing hierarchy, broad to specific: \n"
    "Clue 1: general semantic clue (what kind of thing it is)\n"
    "Clue 2: a specific feature (what it does / where you find it)\n"
    "Clue 3: a phonemic cue (the first sound, e.g. \"It starts with /k/\")\n"
    "Each clue max 12 words, simple and concrete language.\n"
    "Reply with ONE JSON object and nothing else:\n"
    '{"target": "<word>", "clues": ["<clue 1>", "<clue 2>", "<clue 3>"]}'
)

JUDJE_PROMPT = (
    "You judge a child's guess in a word game. The target is: \"{target}\".\n"
    "Classify the child's message as exacty one of: \n"
    "\"correct\" - they named the target (Allow synonyms or very close approximations)\n"
    "\"incorrect\" - a wrong guess or any unrelated talk \n"
    "\"stop\" - they want to stop or are losing interest \n"
    'Reply with ONE JSON object: {{"verdict": "correct|incorrect|stop"}}'
)

# Replay func
def wants_replay(child_text):
    r = chatbot.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": REPLAY_PROMPT},
                  {"role": "user", "content": child_text}],
        response_format={"type": "json_object"},
    )
    return json.loads(r.choices[0].message.content).get("answer", "no") == "yes"

def ask_replay(lead_in, anim="think"):
    global awaiting_replay
    game_state["active"] = False
    awaiting_replay = True
    return (lead_in + " Do you want to try another word?").strip(), anim

# Picking a word and clues
def generate_round():
    likes_list = patient_profile.get("likes", [])
    likes = ", ".join(likes_list) or "none recorded yet"
    avoid = ", ".join(game_state["used"] + likes_list) or "none"
    system_message = (
        ROLE_PROMPT + "\n\n" + ROUND_SETUP_PROMPT + "\n\nThings THIS child likes (base the target on these): " + likes + "\n\n Already used, do not reuse: " + avoid
    )
    response = chatbot.chat.completions.create(
        model = MODEL_NAME,
        messages=[{"role": "system", "content": system_message}] + conversation_history,    
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    target = (data.get("target") or "").strip()
    raw_clues = data.get("clues") or []
    if isinstance(raw_clues, str):          # model returned a string instead of a list
        raw_clues = [raw_clues]
    clues = [c.strip() for c in raw_clues if isinstance(c, str) and c.strip()][:3]
    print(f"[GAME] generate_round -> target={target!r}, clues={clues}")
    return target, clues

# Chekcing if the guess is correct
def judge_answer(child_text, target):
    response = chatbot.chat.completions.create(
        model = MODEL_NAME,
        messages=[
            {"role": "system", "content": JUDJE_PROMPT.format(target=target)}, 
            {"role": "user", "content": child_text},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content).get("verdict", "incorrect")

# Round start/reset for better game handling 
def start_round(lead_in=""):
    target, clues = generate_round()
    print(f"[GAME] Targer word: {target}")
    game_state["active"] = True
    game_state["round"] += 1
    game_state["target"] = target
    game_state["clues"] = clues
    game_state["clue_index"] = 1 # Becasue of first clue
    game_state["used"].append(target)
    return (lead_in + " " + clues[0]).strip(), "think"

def end_game(text, anim):
    game_state["active"] = False
    return text + "Bye!", anim

# Handling the whole game so the LLM doent get lost buy the clues or the words 
def handling_game(user_text):
    if not game_state["active"]:
        return start_round("Okay, let's play the game! Here is your first clue:")
    
    verdict = judge_answer(user_text, game_state["target"])
    print(f"[GAME] verdict={verdict}, clue_index={game_state['clue_index']}, clues={len(game_state['clues'])}")

    if verdict == "stop":
        return end_game("WOW that was really fun! Thanks for playing with me!", "bow")
    
    if verdict == "correct":
        if game_state["round"] >= MAX_ROUNDS:
            return end_game("That's right! You guessed the correct word! You are really good at this game! Thanks for playing with me!", "celebrate")
        return ask_replay(f"That's right! You guessed it!", "celebrate")

    if game_state["clue_index"] < len(game_state["clues"]):
        clue = game_state["clues"][game_state["clue_index"]]
        game_state["clue_index"] += 1
        return "Good guess! Here's another clue: " + clue, "think"
    
    answer = game_state["target"]
    if game_state["round"] >= MAX_ROUNDS:
        return ask_replay(f"That was tricky! The word was {answer}.", "shrug")
    return ask_replay(f"That was tricky! The word was {answer}.", "shrug")
    

# Phase handling 
def handle_intro():
    global current_phase
    system_message = ROLE_PROMPT + "\n\n" + INTRO_PROMPT + "\n\n" + ANIMATION_PROMPT
    response = chatbot.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": system_message}] + conversation_history,
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    reply = (data.get("text") or "").strip()
    anim = (data.get("animation") or "none").strip().lower()

    save_profile(data.get("profile"))

    if GAME_START_MARKER in reply:
        print("[GAME] [GAME_START] marker detected -> entering game phase")
        # global current_phase
        reply = reply.replace(GAME_START_MARKER, "").strip()
        current_phase = "game"
        clue_text, clue_anim = start_round("Okay, let's start the game then! Here is your first clue.")
        return (reply + " " + clue_text).strip(), clue_anim
    
    if FLASH_GAME_START_MARKER in reply:
        print("[GAME] [FLASH_GAME_START] marker detected -> entering Flash game phase")
        
        reply = reply.replace(FLASH_GAME_START_MARKER, "").strip()
        current_phase = "flash_game"
        # clue_text, clue_anim = start_round("Okay, let's start the game then! Here is your first clue.")
        return reply, anim 

    return reply, anim



current_phase = "intro"
GAME_START_MARKER = "[GAME_START]"
FLASH_GAME_START_MARKER = "[FLASH_GAME_START]"
awaiting_replay = False


def start_animation(session, anim):
    if not anim or anim == "none":
        return None
    if anim == "yes":
        return perform_movement(session, frames=NOD_FRAMES, force=True)
    if anim == "no":
        return perform_movement(session, frames=SHAKE_FRAMES, force=True)
    behavior_name = ANIM_BEHAVIORS.get(anim)
    if behavior_name is None:
        return None
    return session.call("rom.optional.behavior.play", name=behavior_name)

# This might not work because it needs an actual URL
# There might be another way by converting the mp3 to raw stereo but I dont know how that works
# I asked an LLM but not a good answer was given. 

# TTS for changing voice
# Not using this 
def changed_voice(text):
    response = voicebot.audio.speech.complete(
        model=MISTRAL_MODEL_NAME,
        input=text,
        voice_id="gb_oliver_excited",
        response_format="mp3",
    )
    Path("audio/output.mp3").write_bytes(base64.b64decode(response.audio_data))

# Function to use in the main loop. Probably wont work thouhg
# Not using this 
def say(session, text):
    changed_voice(text)
    yield session.call(
        "rom.actuator.audio.stream",
        url="audio/output.mp3",
        sync=True,
    )


def ask_llm(user_text: str):
    global awaiting_replay
    conversation_history.append({"role": "user", "content": user_text})

    if awaiting_replay:
        awaiting_replay = False
        if wants_replay(user_text):
            text, anim = start_round("Yay! Here is your next word:")
        else:
            text, anim = "Okay! That was so much fun. Bye!", "bow"
        conversation_history.append({"role": "assistant", "content": text})
        return text, anim
    

    if current_phase == "game":
        text, anim = handling_game(user_text)
    else:
        text, anim = handle_intro()

    conversation_history.append({"role": "assistant", "content": text})
    #changed_voice(text) Doesnt work, but wouldnt use it eitherway
    return text, anim


conversation_history: list[dict] = []

# Smoke test on startup
# print(ask_llm("Hello there"))


exit_conditions = (":q", "quit", "exit") # Only for text but we keep it

finish_dialogue = False
query = "hello"
response_text = ""

# Check if this works 
listening = False
def asr(frames):
    global finish_dialogue, query
    if not listening:
        return
    if frames["data"]["body"]["final"]:
        query = str(frames["data"]["body"]["text"]).strip()
        print("ASR response: ", query)
        finish_dialogue = True
    print("finish: ", finish_dialogue)


@inlineCallbacks
def main(session, details):
    global finish_dialogue, query, response_text, listening
    #TODO check if here otherwise global
    card_game = flash_card_game(chatbot, MODEL_NAME)

    # Set language to English
    yield session.call("rie.dialogue.config.language", lang="en")
    # robot stand up
    yield session.call("rom.optional.behavior.play", name="BlocklyStand")

    #Face detection (Don't think it works)
    #yield session.call("rie.vision.face.find")
    # Following face implementation (Might not work either)

    # Greet prompt
    session.call("rom.optional.behavior.play", name="BlocklyWaveLeftArm")
    greeting = "Hello there! I'm Alpha Mini. It's nice to see you!"
    yield session.call("rie.dialogue.say", text=greeting)
    yield sleep(1)

    # Speech recognition
    yield session.subscribe(asr, "rie.dialogue.stt.stream")
    yield session.call("rie.dialogue.stt.stream")
    print('end')
    listening = True
    # loop until the user says exit or quit
    dialogue = True

    # card_game.main(session)

    while dialogue:
        if current_phase == "flash_game" and card_game.get_answer_child() == False:
            if card_game.get_explained():
                yield from card_game.explaing_game(session)
            print('something')
            yield from card_game.play_game(session, card_game.get_new_game())

        if "Bye" in response_text:
            dialogue = False
        if finish_dialogue:
            print('test5')
            # Stop listening while we think and speak, so the robot
            # never transcribes its own voice.
            listening = False
            yield session.call("rie.dialogue.stt.close")
            print("also here ", query)
            if query in exit_conditions:
                dialogue = False
                yield session.call("rie.dialogue.say", text="Goodbye! It was nice talking with you. See you again next time.")
                break
            elif query != "":
                print('test4')
                if current_phase != "flash_game":
                    print(' test2')
                    response_text, anim = ask_llm(query)
                    start_animation(session, anim=anim)
                    print("response:", response_text, "| anim:", anim)
                    yield session.call("rie.dialogue.say", text=response_text)
                    yield sleep(0.5)   # wait out the audio
                elif current_phase == "flash_game" and card_game.get_answer_child() == True:
                    print(' test3')
                    if card_game.check_if_sim(query, card_game.get_last_responses(), card_game.get_threshold()):
                        query = ""
                        yield session.call("rie.dialogue.stt.stream")
                        yield sleep(0.5)
                        continue
                    response_text, answer_child, new_game, leave_game = card_game.listen_if_child_want_to_play(query, card_game.get_answer_child())
                    card_game.set_answer_child(answer_child)
                    card_game.set_new_game(new_game)
                    if leave_game:
                        dialogue = False
                        yield session.call("rie.dialogue.say", text="Goodbye! It was nice talking with you. See you again next time.")
                        yield session.call("rom.optional.behavior.play", name="BlocklyWaveRightArm")
                        break
                    text = card_game.queue_response(text=response_text)
                    yield session.call("rie.dialogue.say", text=text)
            else:
                fallback = "Sorry, I couldn't hear you"
                if current_phase == "flash_game":
                    print('ets7')
                    fallback = card_game.queue_response(text="sorry, I couldn't hear you")     
                # yield session.call("rie.dialogue.say", text=fallback)
                yield sleep(0.5)
            # Reset AFTER speaking so any stray frames captured mid-speech are dropped.
            finish_dialogue = False
            query = ""
            listening = True
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
    realm="rie.6a3001778a2cba4f82b89bbf",  # !!!!!!! Check this in case of failure to connect!!!!!!
)

wamp.on_join(main)

if __name__ == "__main__":
    run([wamp])