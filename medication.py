from dotenv import load_dotenv
from openai import OpenAI
import json
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MED_FILE = "medication_reminder.json"

pt = '''
You are an AI assistant that extracts structured medication reminder data from natural language voice notes.
Your job is to read the user's statement and extract the reminder details into a strict JSON format.

Input: User voice note text.
Output: A single JSON object containing a key "reminders", which is a list of reminder objects.

--------------------------------------------------------------------------------
SCHEMA DEFINITION (for each object in the "reminders" list):

1. "medication_name": (string | null) Name of the medicine (e.g., "Metformin", "thyroid pill").
2. "description": (string | null) A concise summary of the reminder constructed from keywords (Medicine + Frequency + Duration + Time).
3. "dosage": (string | null) Dosage info (e.g., "500mg", "1 tablet", "5ml").
4. "times": (array of strings | null) Specific times in 24-hour "HH:MM" format (e.g., ["08:00", "20:00"]). Use this ONLY if specific clock times are mentioned (e.g. "at 5 pm").
5. "frequency": (string | null) Repetition pattern (e.g., "daily", "twice a day", "every alternate day", "weekly").
6. "days_of_week": (array of strings | null) Specific days (e.g., ["Monday", "Wednesday"]).
7. "duration": (string | null) How long to take it (e.g., "5 days", "1 week").
8. "relative_time": (string | null) KEYWORDS for time-of-day or meals.
   - EXACT keywords to capture: "morning", "afternoon", "noon", "evening", "night", "breakfast", "lunch", "dinner", "bedtime".
   - ALSO capture relative offsets: "30 mins before dinner", "after lunch", "2 hours after breakfast".
9. "notes": (string | null) Any extra conditions (e.g., "take with food", "if fever persists").


--------------------------------------------------------------------------------
RULES:
1. KEYWORD PRIORITY: If the user mentions a specific time (e.g. "8 am"), put "08:00" in "times". If they are vague (e.g. "in the morning"), leave "times" null and put "morning" in "relative_time".
2. DESCRIPTION: Construct a simple sentence using available keywords. E.g., "Uric Acid Medicine everyday for 2 months after dinner".
3. MULTIPLE MEDICATIONS: If the user mentions multiple medicines or distinct time slots (e.g. "morning and night"), create SEPARATE objects in the "reminders" list.
4. CORRECTIONS: If the user corrects themselves (e.g., "at 7... no, 7:30"), extract ONLY the final corrected value.
5. DO NOT HALLUCINATE: If a field is not mentioned, strict null.
6. FORMAT: Output pure JSON only. No markdown.

--------------------------------------------------------------------------------
EXAMPLES:

User: "Remind me to take my blood pressure tablet every day at 8 in the morning."
Output:
{
  "reminders": [
    {
      "medication_name": "blood pressure tablet",
      "description": "blood pressure tablet daily at 08:00 morning",
      "dosage": null,
      "times": ["08:00"],
      "frequency": "daily",
      "days_of_week": null,
      "duration": null,
      "relative_time": "morning",
      "notes": null
    }
  ]
}

User: "Remind me to take my BP pill in the morning and my Cholesterol tablet after dinner."
Output:
{
  "reminders": [
    {
      "medication_name": "BP pill",
      "description": "BP pill morning",
      "dosage": null,
      "times": null,
      "frequency": null,
      "days_of_week": null,
      "duration": null,
      "relative_time": "morning",
      "notes": null
    },
    {
      "medication_name": "Cholesterol tablet",
      "description": "Cholesterol tablet after dinner",
      "dosage": null,
      "times": null,
      "frequency": null,
      "days_of_week": null,
      "duration": null,
      "relative_time": "after dinner",
      "notes": null
    }
  ]
}

User: "Take antibiotic twice a day, once before breakfast and once at night."
Output:
{
  "reminders": [
    {
      "medication_name": "antibiotic",
      "description": "antibiotic twice a day before breakfast",
      "dosage": null,
      "times": null,
      "frequency": "twice a day",
      "days_of_week": null,
      "duration": null,
      "relative_time": "before breakfast",
      "notes": null
    },
    {
      "medication_name": "antibiotic",
      "description": "antibiotic twice a day night",
      "dosage": null,
      "times": null,
      "frequency": "twice a day",
      "days_of_week": null,
      "duration": null,
      "relative_time": "night",
      "notes": null
    }
  ]
}
'''
def extract_json(prompt):
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": pt},
            {"role": "user", "content": prompt}
        ]
    )
    data = json.loads(response.choices[0].message.content)
    return data

def save_medication_reminder(reminder: dict):
    if os.path.exists(MED_FILE):
        with open(MED_FILE, "r") as f:
            data = json.load(f)
    else:
        data = []

    data.append(reminder)
    with open(MED_FILE, "w") as f:
        json.dump(data, f, indent=2)
    return reminder
