from autobahn.twisted.component import Component, run
from twisted.internet.defer import inlineCallbacks
from autobahn.twisted.util import sleep
from google import genai
from google.genai import types
import os


# This demo is a very straightforward implementation of a text-based chatbot using google's
# generative AI, Gemini
# To use Gemini, you need to acquire a (free) key that you submit to your system environment.
# Learn more at https://ai.google.dev/gemini-api

# Setting the API KEY
chatbot = genai.Client(api_key=os.environ["API_KEY"])
# Alternatively, use
# chatbot = genai.Client(api_key="your_API_key_from_google")

response = chatbot.models.generate_content(
    model="gemini-2.5-flash",
    config=types.GenerateContentConfig(
        system_instruction="None"),
    contents="Hello there"
)

print(response.text)

exit_conditions = (":q", "quit", "exit")

finish_dialogue = False
query = "hello"
response = "qqq"

def asr(frames):
    global finish_dialogue
    global query
    if frames["data"]["body"]["final"]:
        query = str(frames["data"]["body"]["text"]).strip()
        print("ASR response: ",query)
        finish_dialogue = True
    print("finish: ",finish_dialogue)

@inlineCallbacks
def main(session, details):
    global finish_dialogue, query, response
    # set language to English (use 'nl' for Dutch)
    yield session.call("rie.dialogue.config.language", lang="en")
    # let the robot stand up
    yield session.call("rom.optional.behavior.play",name="BlocklyStand")

    # prompt from the robot to the user to say something
    yield session.call("rie.dialogue.say", text="You can start a conversation with me.")

    # setting up the automatic speech recognition
    # subscribes the asr function with the input stt stream
    yield session.subscribe(asr, "rie.dialogue.stt.stream")
    # calls the stream. From here, the robot prints each 'final' sentence
    yield session.call("rie.dialogue.stt.stream")

    # loop while user did not say exit or quit
    dialogue = True
    while dialogue:
        if (finish_dialogue):
            yield session.call("rie.dialogue.stt.close")
            yield sleep(1)
            print("also here ", query)
            if query in exit_conditions:
                dialogue = False
                yield session.call("rie.dialogue.say","ok, I will leave you then")
                break
            elif (query != ""):
                response = chatbot.models.generate_content(
                    model="gemini-2.5-flash", contents=query)
                print("response:", response.text)
                yield session.call("rie.dialogue.say", response.text)
            else:
                yield session.call("rie.dialogue.say", text="sorry, I couldn't hear you")
            finish_dialogue = False
            query = ""
            yield session.call("rie.dialogue.stt.stream")
        yield sleep(0.5)

    yield session.call("rie.dialogue.stt.close")

    yield session.call("rom.optional.behavior.play",name="BlocklyCrouch")
    session.leave()

wamp = Component(
    transports=[{
        "url": "ws://wamp.robotsindeklas.nl",
        "serializers": ["msgpack"],
        "max_retries": 0
    }],
    realm="rie.6915b9ab375fb38004f52a7d",
)

wamp.on_join(main)

if __name__ == "__main__":
    run([wamp])