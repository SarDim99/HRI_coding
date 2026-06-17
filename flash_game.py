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
    """
    A flash card game where the chatbot asks a child to show animal cards.
    
    The game uses object detection to identify animals shown by the child
    and compares them to a randomly selected target animal. The game tracks
    responses, checks sentence similarity for conversation management
    """
    def __init__(self, chatbot, model_name: str):
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
        self.explained = False
        self.last_responses = []
        self.threshold_sentence_sim = 0.8

    def get_explained(self) -> float:
        """Return explained.

        Returns:
            float: The current value of explained.
        """
        return self.explained

    def get_threshold(self) -> float:
        """Return threshold_sentence_sim.

        Returns:
            float: The current value of threshold_sentence_sim.
        """
        return self.threshold_sentence_sim
    
    def get_last_responses(self) -> list[str]:
        """Return last_responses.

        Returns:
            list[str]: The current value of last_responses.
        """
        return self.last_responses
    
    def get_answer_child(self) -> bool:
        """Return answer_child.

        Returns:
            bool: The current value of answer_child.
        """
        return self.answer_child
    
    def set_answer_child(self, answer_child: bool):
        """Set answer_child.

        Args:
        answer_child (bool): The new value to set for answer_child.
        """
        self.answer_child = answer_child

    def get_new_game(self) -> bool:
        """Return new_game.

        Returns:
            bool: The current value of new_game.
        """
        return self.new_game
    
    def set_new_game(self, new_game: bool):
        """Set new_game.

        Args:
        new_game (bool): The new value to set for new_game.
        """
        self.new_game = new_game

    def get_target(self) -> str:
        """Select and return a random animal from the predefined list.

        Returns:
            str: A randomly chosen animal name from the list.
        """
        animal_list = ["dog", "cat", "elephant", "cow", "horse", "zebra", "giraffe", "bear"]
        target = random.choice(animal_list)
        return target

    def listen_if_child_want_to_play(self, user_text: str, answer_child: bool) -> tuple[str,bool,bool,bool]:
        """Process user input and check if the child wants to play another game.

        Args:
            user_text (str): The text input from the user.
            answer_child (bool): Indicating whether the child currently wants to play.

        Returns:
            tuple[str, bool, bool, bool]:
                - reply (str): The response to be spoken by teh LLM.
                - answer_child (bool): Set to False after processing.
                - new_game (bool): True if the user wants to start a new round.
                - leave_game (bool): True if the user wants to end the game.
        """
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

    def wants_replay(self, child_text: str) -> bool:
        """Determine if a child wants to play again by classifying their response via chatbot.

        Args:
            child_text (str): The child's response text to classify for replay intent.

        Returns:
            bool: True if the classified answer is "yes", False otherwise .
        """
        REPLAY_PROMPT = (
        "A child was asked if they want to play again.\n"
        'Classify their reply as exactly one of: "yes", "no".\n'
        'Reply with ONE JSON object: {"answer": "yes|no"}'
        )


        r = self.chatbot.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "system", "content": REPLAY_PROMPT},
                    {"role": "user", "content": child_text}],
            response_format={"type": "json_object"},
        )
        return json.loads(r.choices[0].message.content).get("answer", "no") == "yes"

    def check_if_sim(self, query: str, last_responses: list[str], threshold_sentence_sim: float) -> bool:
        """Check if the query has high sentence similarity with any recent LLM responses.

        Args:
            query (str): The input query text to compare against recent LLM responses.
            last_responses (list[str]): List of recent LLM responses to compare against.
            threshold_sentence_sim (float): Similarity threshold.

        Returns:
            bool: True if any response in last_responses has similarity > threshold_sentence_sim, False otherwise.
        """
        sentence1 = self.nlp(query)
        for response in last_responses:
            sentence2 = self.nlp(response)
            print("last response:", response)
            print("quary: ", query)
            print("sim: ", sentence1.similarity(sentence2))
            if sentence1.similarity(sentence2) > threshold_sentence_sim:
                return True
        return False

    def queue_response(self, text: str) -> str:
        """
        Add a response to the queue, maintaining a maximum of two entries.

        Args:
            text (str): The response text to add to the queue.

        Returns:
            str: The same response text that was added to the queue.
        """
        if len(self.last_responses) > 1:
            self.last_responses.pop()
        self.last_responses.append(text)
        return text

    def explaing_game(self, session):
        """
        Explain the game rules to the player via a spoken dialogue.

        Args:
            session: The active session object.
        """
        self.explained = True
        yield session.call("rie.dialogue.say", 
                           text="The game works as follows: I ask you to show me an animal and you show my the card that Illustrates that animal")


    def play_game(self, session, new_game: bool) -> tuple[bool, bool]:
        """
        Execute a single round of the animal card guessing game.

        Manages the full game loop for one round: initializing a new game state,
        selecting a target animal, capturing the player's card via YOLO
        evaluating the answer, delivering feedback through dialogue and behavior animations.

        Args:
            session: The active session object.
            new_game (bool): If True, resets all game state and initializes a new round.
            answer_child (bool): If True, The system is awaiting the child's response to play again.
        """
        if new_game:
            self.game_dict["is_true"] = False
            self.game_dict['returned_animal'] = None
            self.game_dict['target'] = None
            self.object_det = object_detect()
            self.new_game = False
            self.answer_child = False

        self.game_dict['target'] = self.get_target()
        yield session.call("rie.dialogue.say", text=f"Can you show me a {self.game_dict["target"]}")

        self.object_det.reset_name()
        self.object_det.run_camera()
        
        self.game_dict["returned_animal"] = self.object_det.get_name()
        if self.game_dict['returned_animal'] == self.game_dict['target']:
            self.game_dict["is_true"] = True
        
        if self.game_dict["is_true"]:
            text = self.queue_response(text="That's correct, good job!")
            yield session.call("rie.dialogue.say", text=text)
            yield session.call("rom.optional.behavior.play", name="BlocklyDab")

        if not self.game_dict["is_true"]:
            text = self.queue_response(text=f"Good try! But that is a {self.game_dict["returned_animal"]}, I choose {self.game_dict['target']}.")
            yield session.call("rie.dialogue.say", text=text)
            yield session.call("rom.optional.behavior.play", name="BlocklyApplause")

        text = self.queue_response(text="Do you want to play another game?")
        yield session.call("rie.dialogue.say", text= text)
        self.answer_child = True
  