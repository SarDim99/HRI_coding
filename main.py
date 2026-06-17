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

import category_game as category_game
from flash_game import flash_card_game as flash_game


load_dotenv()


# ============================ MODELS & API CLIENTS ============================

MODEL_NAME = "gpt-4o-mini"
MISTRAL_MODEL_NAME = "voxtral-mini-tts-2603"  # only for the experimental TTS voice

# Keys are read from .env so they are never committed to git
chatbot = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
voicebot = Mistral(api_key=os.getenv("MISTRAL_TTS_KEY"))  # optional

# A single child profile for now (name, age, likes)
PROFILE_PATH = "patient_profile.json"


# ================================= PROMPTS ===================================

# General persona + DLD-friendly speaking rules. Applied in every phase
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

# Output contract: the model must reply with one JSON object every turn
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

# Designs a single game round: a themed target word + a 3-clue cueing hierarchy
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

# Judges a single guess against the current target word
JUDGE_PROMPT = (
    "You judge a child's guess in a word game. The target is: \"{target}\".\n"
    "Classify the child's message as exacty one of: \n"
    "\"correct\" - they named the target (Allow synonyms or very close approximations)\n"
    "\"incorrect\" - a wrong guess or any unrelated talk \n"
    "\"stop\" - they want to stop or are losing interest \n"
    'Reply with ONE JSON object: {{"verdict": "correct|incorrect|stop"}}'
)

# Interprets the child's yes/no answer to "play again?"
REPLAY_PROMPT = (
    "A child was asked if they want to play again.\n"
    'Classify their reply as exactly one of: "yes", "no".\n'
    'Reply with ONE JSON object: {"answer": "yes|no"}'
)


# ============================= PROFILE HANDLING ==============================

def load_profile():
    if os.path.exists(PROFILE_PATH) and os.path.getsize(PROFILE_PATH) > 0:
        try:
            with open(PROFILE_PATH, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Profile unreadable. Starting fresh...")
    return {}


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

# Pick the right introduction prompt depending if we have saved a profile or not
def build_intro_prompt():
    if patient_profile.get("name"):
        likes = ", ".join(patient_profile.get("likes", [])) or "things from before"
        age = patient_profile.get("age")
        age_str = f"{age} years old" if isinstance(age, int) else "the same age as before"
        return (
            "CURRENT PHASE: WELCOMING BACK\n"
            f"You already know this child. Their name is {patient_profile['name']}, "
            f"they are {age_str}, and they like {likes}.\n"
            "Greet them warmly by name, like an old friend. Do NOT ask their name or age again.\n"
            "You may ask if there is anything NEW they like.\n"
            "Then you should suggest playing the guessing game.\n\n"
            "PROFILE UPDATES:\n"
            "If the child tells you something NEW (a new like, or their age if it was unknown), "
            "report it in the \"profile\" field of your JSON output (see OUTPUT FORMAT). "
            "Otherwise omit the field. Never say the profile out loud.\n\n"
            "Try to find out any missing information about their profile. If none is missing ask the kid what do you want to do today."
            "TRANSITION TO GAME:\n"
            "As soon as the child agrees to play, you MUST append [GAME_START] at the very "
            "end of the \"text\" field. This is required - without it the game cannot start.\n"
            "Do not keep chatting once they agree. Do not ask more profile questions first.\n"
            'Example: {"text": "Yay! Let\'s play! [GAME_START]", "animation": "celebrate"}\n'
            "Do NOT include [GAME_START] before the child has agreed."
        )
    return (
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
        "Once you know the child's name AND at least one thing they like, you MUST immediatly suggest "
        "playing a guessing game (e.g., 'I know a fun game we can play! Want to try?'). "
        "YOU MUST ALWAYS END your answer WITH A QUESTION: Every reply MUST end with one simple "
        "question or invitation, so the child always has something to say back."
        "TRANSITION TO GAME:\n"
        "As soon as the child agrees to play, you MUST append [GAME_START] at the very "
        "end of the \"text\" field. This is required - without it the game cannot start.\n"
        "Do not keep chatting once they agree. Do not ask more profile questions first.\n"
        'Example: {"text": "Yay! Let\'s play! [CATEGORY_GAME_START]", "animation": "celebrate"}\n'
        "Do NOT include [CATEGORY_GAME_START] before the child has agreed."
    )


# Load the profile and build the matching intro prompt at startup
patient_profile = load_profile()
if patient_profile:
    print("Loaded patient profile:", patient_profile)
INTRO_PROMPT = build_intro_prompt()


# ================================ ANIMATIONS =================================

# Maps an animation keyword to a pre-built Blockly behavior
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


# ============================ GAME: STATE & CONFIG ===========================

MAX_ROUNDS = 4  # how many words before the robot wraps the game up

# Mutable game state for the current session.
game_state = {
    "active": False,
    "round": 0,
    "target": None,
    "clues": [],
    "clue_index": 0,
    "used": [],  # target words already played so we don't repeat them
}

# Phase + transition globals.
current_phase = "intro"            # intro -> game
GAME_START_MARKER = "[GAME_START]"  # appended by the model when the child agrees to play
awaiting_replay = False            # True while we wait for a yes/no play again answer


# =============================== GAME: LOGIC =================================

def generate_round():
    likes_list = patient_profile.get("likes", [])
    likes = ", ".join(likes_list) or "none recorded yet"
    avoid = ", ".join(game_state["used"] + likes_list) or "none"
    system_message = (
        ROLE_PROMPT + "\n\n" + ROUND_SETUP_PROMPT
        + "\n\nThings THIS child likes (base the target on these): " + likes
        + "\n\n Already used, do not reuse: " + avoid
    )
    response = chatbot.chat.completions.create(
        model=MODEL_NAME,
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


def judge_answer(child_text, target):
    response = chatbot.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": JUDGE_PROMPT.format(target=target)},
            {"role": "user", "content": child_text},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content).get("verdict", "incorrect")


def wants_replay(child_text):
    r = chatbot.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": REPLAY_PROMPT},
                  {"role": "user", "content": child_text}],
        response_format={"type": "json_object"},
    )
    return json.loads(r.choices[0].message.content).get("answer", "no") == "yes"


def start_round(lead_in=""):
    target, clues = generate_round()
    print(f"[GAME] Target word: {target}")
    game_state["active"] = True
    game_state["round"] += 1
    game_state["target"] = target
    game_state["clues"] = clues
    game_state["clue_index"] = 1  # clue 0 is delivered now so the next one is index 1
    game_state["used"].append(target)
    return (lead_in + " " + clues[0]).strip(), "think"


def ask_replay(lead_in, anim="think"):
    global awaiting_replay
    game_state["active"] = False
    awaiting_replay = True
    return (lead_in + " Do you want to try another word?").strip(), anim


def end_game(text, anim):
    game_state["active"] = False
    return text + "Bye!", anim


# Judge the guess, then either reveal the next clue, celebrate a correct answer or end.
def handling_game(user_text):
    if not game_state["active"]:
        return start_round("Okay, let's play the game! Here is your first clue:")

    verdict = judge_answer(user_text, game_state["target"])
    print(f"[GAME] verdict={verdict}, clue_index={game_state['clue_index']}, clues={len(game_state['clues'])}")

    if verdict == "stop":
        return end_game("WOW that was really fun! Thanks for playing with me!", "bow")

    if verdict == "correct":
        if game_state["round"] >= MAX_ROUNDS:
            return end_game(
                "That's right! You guessed the correct word! You are really good at this game! "
                "Thanks for playing with me!", "celebrate")
        return ask_replay("That's right! You guessed it!", "celebrate")

    # Wrong guess: give the next clue if one is left
    if game_state["clue_index"] < len(game_state["clues"]):
        clue = game_state["clues"][game_state["clue_index"]]
        game_state["clue_index"] += 1
        return "Good guess, but not quite right! Here's another clue: " + clue, "think"

    # Otherwise the clues are exhausted -> reveal the answer and ask to play again.
    return ask_replay(f"That was tricky! The word was {game_state['target']}.", "shrug")


# =============================== INTRO PHASE =================================

# Saves new profile info + switches to game phase
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

    if GUESSING_GAME_START_MARKER in reply:
        print("[GAME] [GUESSING_GAME_START] marker detected -> entering guessing game phase")
        global current_phase
        reply = reply.replace(GUESSING_GAME_START_MARKER, "").strip()
        current_phase = "game"
        clue_text, clue_anim = start_round("Okay, let's start the game then! Here is your first clue.")
        return (reply + " " + clue_text).strip(), clue_anim
    elif CATEGORY_GAME_START_MARKER in reply:
        print("[GAME] [CATEGORY_GAME_START] marker detected -> entering category game phase")
        reply = reply.replace(CATEGORY_GAME_START_MARKER, "").strip()
        current_phase = "category_game"
        return reply, anim
    elif FLASH_GAME_START_MARKER in reply:
        print("[GAME] [FLASH_GAME_START] marker detected -> entering flash game phase")
        reply = reply.replace(FLASH_GAME_START_MARKER, "").strip()
        current_phase = "flash_game"
        return reply, anim

    return reply, anim


# =============================== TURN ROUTER =================================

conversation_history: list[dict] = []


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
    elif current_phase == "category_game":
        text, anim = category_game.ask_category_llm(user_text)
    elif current_phase == "flash_game":
        text, anim = flash_game.play_game(user_text)
    else:
        text, anim = handle_intro()

    conversation_history.append({"role": "assistant", "content": text})
    return text, anim


# ===================== EXPERIMENTAL VOICE (Mistral TTS) ======================

# Disabled by default. The robot uses its built-in rie.dialogue.say voice.
# These would swap in a custom Mistral TTS voice, but decided we won't use
# this as the voice sounds too human for a robot.
# We left the code in case we want to experiment about this. 
def changed_voice(text):
    response = voicebot.audio.speech.complete(
        model=MISTRAL_MODEL_NAME,
        input=text,
        voice_id="gb_oliver_excited",
        response_format="mp3",
    )
    Path("audio/output.mp3").write_bytes(base64.b64decode(response.audio_data))


def say(session, text):
    changed_voice(text)
    yield session.call(
        "rom.actuator.audio.stream",
        url="audio/output.mp3",
        sync=True,
    )


# ============================ SPEECH I/O & LOOP ==============================

exit_conditions = (":q", "quit", "exit")  # typed-only shortcuts kept as a safety net

finish_dialogue = False
query = "hello"
response_text = ""
listening = False


# Estimate how long the robot will be speaking so we keep the mic muted for that long. Doesnt work that well
def estimate_speech_time(text):
    return len(text.split()) / 2.5 + 0.7


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
    # Robot stands up
    yield session.call("rom.optional.behavior.play", name="BlocklyStand")

    # Greet the child
    session.call("rom.optional.behavior.play", name="BlocklyWaveLeftArm")
    greeting = "Hello there! I'm Alpha Mini. It's nice to see you! How are you doing today?"
    yield session.call("rie.dialogue.say", text=greeting)
    yield sleep(1)

    # Open the speech-recognition stream
    yield session.subscribe(asr, "rie.dialogue.stt.stream")
    yield session.call("rie.dialogue.stt.stream")
    print('end')
    listening = True

    # One pass per recognised utterance, until Bye or an exit word
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
            listening = False
            yield session.call("rie.dialogue.stt.close")
            print("also here ", query)
            if query in exit_conditions:
                dialogue = False
                yield session.call("rie.dialogue.say", text="Goodbye! It was nice talking with you. See you again next time.")
                break
            elif query != "":
                response_text, anim = ask_llm(query)
                start_animation(session, anim=anim)
                print("response:", response_text, "| anim:", anim)
                yield session.call("rie.dialogue.say", text=response_text)
                yield sleep(estimate_speech_time(response_text))   # wait out the audio
            else:
                fallback = "Sorry, I couldn't hear you"
                yield session.call("rie.dialogue.say", text=fallback)
                yield sleep(estimate_speech_time(fallback))
            # Reset AFTER speaking so any stray frames captured mid-speech are dropped.
            finish_dialogue = False
            query = ""
            listening = True
            yield session.call("rie.dialogue.stt.stream")
        yield sleep(0.5)

    yield session.call("rie.dialogue.stt.close")
    yield session.call("rom.optional.behavior.play", name="BlocklyCrouch")
    session.leave()


# ============================== WAMP / STARTUP ===============================

wamp = Component(
    transports=[{
        "url": "ws://wamp.robotsindeklas.nl",
        "serializers": ["msgpack"],
        "max_retries": 0
    }],
    realm="rie.6a2fdf048a2cba4f82b89b1f",  # !!! Replace with your robots realm if connection fails !!!
)

wamp.on_join(main)

if __name__ == "__main__":
    run([wamp])
