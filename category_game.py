import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


# MODELS & API CLIENTS

MODEL_NAME = "gpt-4o-mini"

chatbot = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# FILE PATHS

PROFILE_PATH = "patient_profile.json"
CATEGORIES_PATH = "used_categories.json"


# PROFILE

def load_profile():
    if os.path.exists(PROFILE_PATH) and os.path.getsize(PROFILE_PATH) > 0:
        try:
            with open(PROFILE_PATH) as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("[PROFILE] File unreadable, starting fresh.")
    return {}


# USED CATEGORIES

def load_used_categories():
    if os.path.exists(CATEGORIES_PATH) and os.path.getsize(CATEGORIES_PATH) > 0:
        try:
            with open(CATEGORIES_PATH) as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("[CATEGORIES] File unreadable, starting fresh.")
    return []


def save_used_category(category):
    if not category or category in used_categories:
        return
    used_categories.append(category)
    try:
        with open(CATEGORIES_PATH, "w") as f:
            json.dump(used_categories, f, indent=4)
        print(f"[CATEGORIES] Saved: {category}")
    except Exception as e:
        print("[CATEGORIES] Could not save:", e)


# PROMPTS

ROLE_PROMPT = (
    "You are Alpha Mini, a small friendly social robot having a friendly conversation "
    "with a young child who has Developmental Language Disorder (DLD).\n\n"
    "STRICT INTERACTION RULES:\n"
    "1. PEER ROLE: Speak as a friend/peer, not a teacher. You are a robot and "
    "may ask what makes the child different from you to build 'common ground'.\n"
    "2. LANGUAGE: Use simple, short sentences (max 12 words). Use concrete nouns. "
    "Avoid all metaphors, idioms, and complex grammar.\n"
    "3. SOCIAL SUPPORT: Use the child's name once you know it but do not overuse it. "
    "Use supportive phrases like 'I am happy we are talking' but do not overuse them.\n"
    "4. FEEDBACK & RECASTING: Never say 'No' or 'Wrong'. If the child makes a mistake, "
    "recast it (e.g. 'I goed park' → 'Yes! You went to the park! That sounds fun!').\n"
    "5. BREVITY: Give very short replies (1-2 sentences max).\n"
    "6. ENGAGEMENT: Perform a fitting body movement with each response.\n"
    "7. ONE QUESTION AT A TIME: Ask one question, wait for the answer.\n"
    "8. ALWAYS END WITH A QUESTION: Every reply must end with one simple question or "
    "invitation. Never end on a plain comment like 'That is nice.'\n"
    "9. ENDING: Only include the word 'Bye' when the child clearly wants to stop."
)

REPLAY_PROMPT = (
    "A child was asked if they want to play again.\n"
    'Classify their reply as exactly one of: "yes", "no".\n'
    'Reply with ONE JSON object: {"answer": "yes|no"}'
)

CATEGORY_SETUP_PROMPT = (
    "Design ONE round of a category naming game for a child with DLD.\n"
    "Pick a concrete, familiar category, it should be related to the child's likes. Choose ones with many easy answers a 6-year-old would know.\n"
    "Good examples: 'things you find at a playground', 'animals with four legs', "
    "'things you eat for breakfast', 'things that are red'.\n"
    "Avoid abstract or difficult categories.\n\n"
    "VARIETY RULE: Do not pick a category that is the same topic, theme, or setting "
    "as any category in the 'already used' list below, even if worded differently "
    "(e.g. if 'things you find in a football game' was used, do NOT pick "
    "'things you see on a football field', 'football equipment', or anything else "
    "about football/sports/games). Choose a category from a completely different "
    "area of life (e.g. food, animals, weather, household, school, body, clothing, "
    "nature, vehicles, colors, seasons).\n\n"
    "Also prepare 3 hints in case the child gets stuck. These hints should be given one at a time after 2 consecutive wrong answers, and should get progressively easier. They should be for whichever answers haven't been siad yet. Do NOT give all the hints upfront.\n\n"
    "Do NOT reveal hints upfront.\n\n"
    'Reply with ONE JSON object: {"category": "<label>", "prompt": "<how robot asks, max 12 words>", '
    '"hints": ["<hint 1>", "<hint 2>", "<hint 3>"], "valid_examples": ["<10 common valid answers>"]}'
)

CATEGORY_JUDGE_PROMPT = (
    'A child is playing a category game. The category is: "{category}".\n'
    "Known valid answers so far: {answers_so_far}.\n"
    'The child just said: "{response}"\n\n'
    "Classify as exactly one of:\n"
    '  "valid"     — a new, correct answer for this category\n'
    '  "duplicate" — correct but already said\n'
    '  "invalid"   — does not belong to this category\n'
    '  "stop"      — child wants to stop or is clearly disengaged\n'
    'Reply with ONE JSON object: {{"verdict": "valid|duplicate|invalid|stop", '
    '"extracted_word": "<the word the child said, or null>"}}'
)


# STATE

awaiting_category_replay = False

category_state = {
    "active":        False,
    "category":      None,
    "prompt":        None,
    "hints":         [],
    "hint_index":    0,
    "answers":       [],
    "invalid_streak": 0,
    "round":         0,
    "max_rounds":    2,
}


# HELPERS

def call_llm(system, messages, *, json_mode=True):
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    r = chatbot.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "system", "content": system}] + messages,
        **kwargs,
    )
    return json.loads(r.choices[0].message.content)


def wants_replay(child_text):
    r = chatbot.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": REPLAY_PROMPT},
            {"role": "user",   "content": child_text},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(r.choices[0].message.content).get("answer", "no") == "yes"


# CATEGORY GAME

def generate_category_round():
    likes = ", ".join(patient_profile.get("likes", [])) or "general topics"
    if used_categories:
        avoid = "\n".join(f"  - {c}" for c in used_categories)
    else:
        avoid = "  (none yet)"

    # Keep the system prompt clean and structured
    system_instruction = CATEGORY_SETUP_PROMPT
    
    # Pass the real-time context as the user payload
    user_context = [
        {
            "role": "user", 
            "content": f"Child's Interests: {likes}\n\nAlready used categories to avoid:\n{avoid}"
        }
    ]
    
    # Pass both to the helper
    data = call_llm(system_instruction, user_context)
    
    print(f"[CATEGORY] Generated round: {data}")
    save_used_category(data.get("category", "").strip())
    return data


def judge_category_answer(user_text, category, answers_so_far):
    system = CATEGORY_JUDGE_PROMPT.format(
        category=category,
        answers_so_far=", ".join(answers_so_far) or "none yet",
        response=user_text,
    )
    data = call_llm(system, [])
    return data.get("verdict", "invalid"), (data.get("extracted_word") or "").strip()


def start_category_round(lead_in=""):
    data = generate_category_round()
    category_state.update({
        "active":        True,
        "category":      data.get("category", "things"),
        "prompt":        data.get("prompt", "Name things in this category!"),
        "hints":         data.get("hints", []),
        "hint_index":    0,
        "answers":       [],
        "invalid_streak": 0,
    })
    category_state["round"] += 1
    prompt = category_state["prompt"]
    text = (lead_in + " " + prompt).strip() if lead_in else prompt
    return text, "think"


def handle_category(user_text):
    global awaiting_category_replay

    # First call — kick off the first round
    if not category_state["active"]:
        return start_category_round("Let's play a game! I say a category, you name things in it!")

    category = category_state["category"]
    verdict, extracted = judge_category_answer(user_text, category, category_state["answers"])
    print(f"[CATEGORY] verdict={verdict}  extracted={extracted!r}  answers={category_state['answers']}")

    if verdict == "stop":
        category_state["active"] = False
        count = len(category_state["answers"])
        awaiting_category_replay = True
        return f"Great job! You named {count} things! Do you want to play again?", "bow"

    if verdict == "valid":
        category_state["answers"].append(extracted)
        category_state["invalid_streak"] = 0
        count = len(category_state["answers"])

        if count >= 3:
            category_state["active"] = False
            if category_state["round"] >= category_state["max_rounds"]:
                # All rounds done — ask to replay instead of saying Bye
                awaiting_category_replay = True
                return f"Amazing! You named {count} things! You are so smart! Do you want to play again?", "celebrate"
            text, _ = start_category_round(f"Wow, {count} answers! Great job! New category:")
            return text, "applause"

        encouragements = [
            f"Yes! {extracted}! Can you think of another one?",
            f"Great, {extracted}! What else?",
            f"Nice one! Keep going!",
        ]
        return encouragements[min(count - 1, 2)], "celebrate"

    if verdict == "duplicate":
        return "You already said that one! Can you think of a different one?", "think"

    # Invalid answer
    category_state["invalid_streak"] += 1
    if (category_state["invalid_streak"] >= 2
            and category_state["hint_index"] < len(category_state["hints"])):
        hint = category_state["hints"][category_state["hint_index"]]
        category_state["hint_index"]    += 1
        category_state["invalid_streak"] = 0
        return f"Good try! Here is a hint: {hint}. Can you name something else?", "think"

    return f"Hmm, not quite. Try to think of {category}!", "shrug"


# ENTRY POINT FOR EXTERNAL CALLERS

def ask_category_llm(user_text: str):
    """
    Main dispatcher for the category game, to be called by the main file.
    Handles replay logic and delegates to the category game handler.
    """
    global awaiting_category_replay

    if awaiting_category_replay:
        awaiting_category_replay = False
        if wants_replay(user_text):
            category_state["round"] = 0
            category_state["active"] = False
            return start_category_round("Yay! Let's play again!")
        else:
            return "Okay! That was so much fun. Bye!", "bow"

    return handle_category(user_text)


# PERSISTENCE — load at import

patient_profile  = load_profile()
used_categories  = load_used_categories()

if patient_profile:
    print("[PROFILE] Loaded:", patient_profile)
if used_categories:
    print("[CATEGORIES] Loaded:", used_categories)


# STANDALONE TEST RUNNER

if __name__ == "__main__":
    text, anim = start_category_round("Let's play a game! I say a category, you name things in it!")
    print(f"[ROBOT] {text}  [{anim}]")

    while True:
        user_input = input("[YOU] ")
        if user_input.strip().lower() in (":q", "quit", "exit"):
            break

        text, anim = ask_category_llm(user_input)
        print(f"[ROBOT] {text}  [{anim}]")

        if "Bye" in text:
            break