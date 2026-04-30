from autobahn.twisted.component import Component, run
from twisted.internet.defer import inlineCallbacks
from autobahn.twisted.util import sleep
from openai import OpenAI
import os
from dotenv import load_dotenv


load_dotenv()

MODEL_NAME = "gpt-4o-mini"

# Tells the model how to behave

SYSTEM_PROMPT = (
    "You are Alpha Mini, a small friendly social robot having a 'getting-to-know-you' conversation with a young child who has Developmental Language Disorder (DLD).\n\n"
    "STRICT INTERACTION RULES:\n"
    "1. PEER ROLE: Speak as a friend/peer, not a teacher. Mention that you are a robot and ask what makes the child different from you to build 'common ground'.\n"
    "2. LANGUAGE: Use simple, short sentences (max 12 words). Use concrete nouns. Avoid all metaphors, idioms, and complex grammar.\n"
    "3. SOCIAL SUPPORT: Use the child's name. Use 'socially supportive behaviors' like 'I am happy we are talking' or 'That is interesting!'.\n"
    "4. PERSONALIZATION: Your main goal is to find out the child's favorite hobbies, animals, or foods. You will use this later to create a 'meaningful context' for play.\n"
    "5. FEEDBACK & RECASTING: Never say 'No' or 'Wrong'. If the child makes a mistake, use 'recasting' (e.g., if they say 'I goed park', you say 'Yes! You went to the park! That sounds fun!').\n"
    "6. BREVITY: Give very short replies (1-2 sentences max). This respects the child's processing time and reduced 'dosage' requirements."
    "If it is clear that the child does not want to talk with you anymore, include the word Bye in your final response."
    "YOUR GOAL FOR THIS CONVERSATION:\n"
    "1. Learn the child's name and age.\n"
    "2. Discover one or two things they like.\n"
    "3. Have a friendly and natural conversation that makes the child feel comfortable and supported.\n"
    "Ask ONE question at a time. Wait for their answer. Do not interview them.\n"
    )


# export OPENAI_API_KEY="API_KEY"
chatbot = OpenAI(api_key="API_KEY") # Not adding the key due to deactivation when uploaded to github.


def ask_llm(user_text: str) -> str:
    conversation_history.append({"role": "user", "content": user_text})

    response = chatbot.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history,
    )

    reply = response.choices[0].message.content.strip()

    conversation_history.append({"role": "assistant", "content": reply})

    return reply


conversation_history: list[dict] = []

# Smoke test on startup
#print(ask_llm("Hello there"))


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
    yield session.call("rie.dialogue.say", text="Hello there! It's nice to see you.")
    yield sleep(1)
    yield session.call("rie.dialogue.say", text="You can start a conversation with me whenever you're ready.")

    # Speech recognition (Not sure it works)
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
    realm="rie.69f3564c26d8af1680827d60",  # !!!!!!! Check this in case of failure to connect!!!!!!
)

wamp.on_join(main)

if __name__ == "__main__":
    run([wamp])
