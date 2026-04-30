from autobahn.twisted.component import Component, run
from twisted.internet.defer import inlineCallbacks
from autobahn.twisted.util import sleep
from openai import OpenAI
import os


MODEL_NAME = "gpt-4o-mini"

# Tells the model how to behave
SYSTEM_PROMPT = (
    "You are a friendly social robot talking (youre name is alphi)to a child with developmental language disorder and talking out loud."
    "Keep replies relatively short and easy to listen to. "
    "Avoid markdown, lists, or emoji."
    "You need to get to know the child, after it has told you his/her name, ask about simple things, such as favourite animal, favourite color"
)


# export OPENAI_API_KEY="API_KEY"
chatbot = OpenAI(api_key="")


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
print(ask_llm("Hello there"))


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
    yield session.call("rie.dialogue.say", text="Hello there, I'm Alphi! It's nice to see you.")
    yield sleep(1)

    # Speech recognition (Not sure it works)
    yield session.subscribe(asr, "rie.dialogue.stt.stream")
    yield session.call("rie.dialogue.stt.stream")

    # loop until the user says exit or quit
    dialogue = True
    while dialogue:
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
    realm="rie.69f209e026d8af16808276fd",  # !!!!!!! Check this in case of failure to connect!!!!!!
)

wamp.on_join(main)

if __name__ == "__main__":
    run([wamp])