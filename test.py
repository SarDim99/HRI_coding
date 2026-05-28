from autobahn.twisted.component import Component, run
from twisted.internet.defer import inlineCallbacks
from autobahn.twisted.util import sleep
from openai import OpenAI
import os
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
    "playing a guessing game (e.g., 'I know a fun game we can play! Want to try?'). "
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
    "4. If they guess correctly: say 'That's right! You guessed it!' and start a new round.\n"
    "5. If they don't guess after 3 clues: say 'Good try! It was a difficult one really! "
    "Do you want to try another one?' and start a new round.\n\n"
    "ROUNDS: Play at least 2 rounds, but no more than 4, to keep the child engaged "
    "without overwhelming them.\n\n"
    "ENDING: If the child loses interest or wants to stop, say 'That was fun! Thanks for "
    "playing with me [child's name]! I had a great time! See you again next time!' and "
    "include 'Bye' in your final response.\n\n"
    "AFTER THE GAME: Try to initiate a short, light conversation about how they liked the game. If the child doen't want to talk, " 
    "end the conversation and include 'Bye' in your final response. \n\n"
)


# Movements performed by the robot and picked by the LLM (NEED TO ADD THIS)
MOVEMENTS = {
    "Hello": "BlocklyWaveRightArm",
    "Bye": "BlocklyWaveRightArm",
    "Think": "BlocklyTouchHead",
}


# export OPENAI_API_KEY="API_KEY"
chatbot = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) # Not adding the key due to deactivation when uploaded to github.


current_phase = "intro"
GAME_START_MARKER = "[GAME_START]"


def ask_llm(user_text: str) -> str:
    global current_phase

    conversation_history.append({"role": "user", "content": user_text})

    if current_phase == "intro":
        system_message = ROLE_PROMPT + "\n\n" + INTRO_PROMPT
    else:
        system_message = ROLE_PROMPT + "\n\n" + GAME_PROMPT

    response = chatbot.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": system_message}] + conversation_history,
    )
    reply = response.choices[0].message.content.strip()

    # Detect phase transition and strip the marker before the robot speaks it
    if current_phase == "intro" and GAME_START_MARKER in reply:
        reply = reply.replace(GAME_START_MARKER, "").strip()
        current_phase = "game"
        print("[Phase changed: intro -> game]")

    conversation_history.append({"role": "assistant", "content": reply})
    return reply


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

    # Greet prompt
    yield session.call("rie.dialogue.say", text="Hello there! I'm Alpha Mini. It's nice to see you!")
    #yield sleep(1)
    #yield session.call("rie.dialogue.say", text="You can start a conversation with me whenever you're ready.")

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
                response_text = ask_llm(query)
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
    realm="rie.6a1820e2f2a08d602afbc30d",  # !!!!!!! Check this in case of failure to connect!!!!!!
)

wamp.on_join(main)

if __name__ == "__main__":
    run([wamp])
