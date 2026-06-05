from autobahn.twisted.component import Component, run
from twisted.internet.defer import inlineCallbacks
from alpha_mini_rug import perform_movement
from autobahn.twisted.util import sleep
from openai import OpenAI
import os
import json
from dotenv import load_dotenv

load_dotenv()

MODEL_NAME = "gpt-4o-mini"

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
    "6. ENGAGEMENT: Perform a fitting body movement with each response. The available "
    "movements and the required output format are described under OUTPUT FORMAT.\n"
    "7. ONE QUESTION AT A TIME: Ask one question, wait for the answer. Do not interview.\n"
    "8. ENDING: If it is clear the child does not want to talk anymore, include the word "
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
    "playing a guessing game (e.g., 'I know a fun game we can play! Want to try?'). "
    "If the child agrees to play, append the marker [GAME_START] at the very end "
    "of the \"text\" field. The marker will be hidden from the child.\n"
    "Do NOT include [GAME_START] before the child has agreed to play."
)


ANIMATION_PROMPT = (
    "OUTPUT FORMAT (ALWAYS):\n"
    "Reply with ONE JSON object and nothing else, no markdown:\n"
    '{"text": "the words you say out loud", "animation": "<name>"}\n'
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
    "Never write the animation name or any JSON inside \"text\"; \"text\" is only spoken words."
)

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



# Game start only when kid talks again so we need to fix it 
# Give the first clue right away
# Game explanation??? 



# TODO: Personalization into a json for game and mahybe something else 


# Instructions for the game phase
GAME_PROMPT = (
    "CURRENT PHASE: GUESSING GAME\n"
    "Using a topic the with the [child's interest] and play a simple "
    "guessing game.\n\n"
    "HOW THE GAME WORKS:\n"
    "1. Pick a word related to something the child likes \n"
    "2. Give 3 simple clues, one at a time.\n"
    "3. After each clue, wait for the child to guess.\n"
    "4. If they guess correctly: say 'That's right! You guessed it!' and start a new round.\n"
    "5. If they don't guess after 3 clues: say 'Good try! It was a difficult one really! "
    "Do you want to try another one?' and start a new round.\n\n"
    "ROUNDS: Play at least 2 rounds, but no more than 4, to keep the child engaged"
    "without overwhelming them.\n\n"
    "ENDING: If the child loses interest or wants to stop, say 'That was fun! Thanks for "
    "playing with me [child's name]! I had a great time! See you again next time!' and "
    "include 'Bye' in your final response.\n\n"
    "AFTER THE GAME: Try to initiate a short, light conversation about how they liked the game. If the child doen't want to talk, " 
    "end the conversation and include 'Bye' in your final response. \n\n"
)



# export OPENAI_API_KEY="API_KEY"
chatbot = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) # Not adding the key due to deactivation when uploaded to github.


current_phase = "intro"
GAME_START_MARKER = "[GAME_START]"


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


def ask_llm(user_text: str):
    global current_phase

    conversation_history.append({"role": "user", "content": user_text})

    if current_phase == "intro":
        system_message = ROLE_PROMPT + "\n\n" + INTRO_PROMPT + "\n\n" + ANIMATION_PROMPT
    else:
        system_message = ROLE_PROMPT + "\n\n" + GAME_PROMPT + "\n\n" + ANIMATION_PROMPT

    response = chatbot.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": system_message}] + conversation_history,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content

    # The model returns {"text": ..., "animation": ...}
    try:
        data = json.loads(raw)
        reply = (data.get("text") or "").strip()
        anim = (data.get("animation") or "none").strip().lower()
    except (json.JSONDecodeError, TypeError):
        reply = (raw or "").strip()
        anim = "none"

    # Detect phase transition and strip the marker before the robot speaks it
    if current_phase == "intro" and GAME_START_MARKER in reply:
        reply = reply.replace(GAME_START_MARKER, "").strip()
        current_phase = "game"
        print("[Phase changed: intro -> game]")

    conversation_history.append({"role": "assistant", "content": reply})
    return reply, anim


conversation_history: list[dict] = []

# Smoke test on startup
# print(ask_llm("Hello there"))


exit_conditions = (":q", "quit", "exit")

finish_dialogue = False
query = "hello"
response_text = ""


def asr(frames):
    global finish_dialogue
    global query
    if frames["data"]["body"]["final"]:
        query = str(frames["data"]["body"]["text"]).strip()
        print("ASR response: ", query)
        finish_dialogue = True
    print("finish: ", finish_dialogue)


@inlineCallbacks
def main(session, details):
    global finish_dialogue, query, response_text

    yield session.call("rie.dialogue.config.language", lang="en")
    # robot stand up
    yield session.call("rom.optional.behavior.play", name="BlocklyStand")

    yield session.call("rie.vision.face.find", timeout=10000)

    # Greet prompt
    session.call("rom.optional.behavior.play", name="BlocklyHello")
    yield session.call("rie.dialogue.say", text="Hello there! I'm Alpha Mini. It's nice to see you!")
    
    # Speech recognition
    yield session.subscribe(asr, "rie.dialogue.stt.stream")
    yield session.call("rie.dialogue.stt.stream")

    # loop until the user says exit or quit
    dialogue = True
    while dialogue:
        if "Bye" in response_text:
            dialogue = False
        if finish_dialogue:
            yield session.call("rie.dialogue.stt.close")
            yield sleep(1)
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
            else:
                yield session.call("rie.dialogue.say", text="Sorry, I couldn't hear you")
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
    realm="rie.6a22750a8a2cba4f82b85cf7",  # !!!!!!! Check this in case of failure to connect!!!!!!
)

wamp.on_join(main)

if __name__ == "__main__":
    run([wamp])