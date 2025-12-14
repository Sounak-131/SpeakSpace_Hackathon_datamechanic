from datetime import datetime, timedelta
import datetime
import os
import json
import re
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def json_extractor(FILE_NAME):
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(BASE_DIR, FILE_NAME)

    with open(json_path, "r", encoding="utf-8") as f:
        reminders = json.load(f)

    return reminders

TIME_MAP = {
    "morning": "08:00:00",
    "afternoon": "14:00:00",
    "noon": "12:00:00",
    "evening": "19:00:00",
    "night": "21:00:00",
    "bedtime": "23:00:00",
    "breakfast": "08:30:00",
    "lunch": "13:30:00",
    "dinner": "20:30:00",
    "before breakfast": "08:00:00",
    "after breakfast": "09:00:00",
    "before lunch": "12:30:00",
    "after lunch": "13:30:00",
    "before dinner": "19:30:00",
    "after dinner": "21:00:00"
}

def get_start_datetime(reminder_json):
    """
    Determines start time by checking:
    1. Explicit 'times' (e.g. "08:00")
    2. Dynamic math (e.g. "after 6 hours", "in 30 mins") -> NOW + offset
    3. Keyword map (e.g. "morning")
    """
    current_time = datetime.datetime.now()
    today_str = current_time.strftime("%Y-%m-%d")
    
    # CASE 1: Explicit Time (Priority)
    if reminder_json.get('times') and len(reminder_json['times']) > 0:
        time_str = reminder_json['times'][0]
        if len(time_str) == 5: 
            time_str += ":00"
        return f"{today_str}T{time_str}"

    # Get the relative time string
    rel_time = reminder_json.get('relative_time', '').lower() if reminder_json.get('relative_time') else ""
    
    # CASE 2: Dynamic Math 
    # Looks for patterns like "6 hours", "2 hrs", "30 minutes", "10 mins"
    match = re.search(r'(\d+)\s*(hour|hr|minute|min)', rel_time)
    
    if match:
        amount = int(match.group(1)) # Extract the number (e.g. 6)
        unit = match.group(2)        # Extract the unit (e.g. "hour")
        
        future_time = current_time
        
        if 'hour' in unit or 'hr' in unit:
            future_time = current_time + timedelta(hours=amount)
        elif 'minute' in unit or 'min' in unit:
            future_time = current_time + timedelta(minutes=amount)
            
        # Return the calculated time formatted for Google
        return future_time.strftime("%Y-%m-%dT%H:%M:%S")

    # CASE 3: Static Keyword Map
    if rel_time in TIME_MAP:
        return f"{today_str}T{TIME_MAP[rel_time]}"
        
    # CASE 4: Soft Fallbacks (for "before dinner" logic etc)
    if "before dinner" in rel_time:
         return f"{today_str}T{TIME_MAP['before dinner']}"
    if "after dinner" in rel_time:
         return f"{today_str}T{TIME_MAP['after dinner']}"
    if "before lunch" in rel_time:
         return f"{today_str}T{TIME_MAP['before lunch']}"
    if "after lunch" in rel_time:
         return f"{today_str}T{TIME_MAP['after lunch']}"
    if "before breakfast" in rel_time:
         return f"{today_str}T{TIME_MAP['before breakfast']}"
    if "after breakfast" in rel_time:
         return f"{today_str}T{TIME_MAP['after breakfast']}"
    if "dinner" in rel_time:
        return f"{today_str}T{TIME_MAP['dinner']}" 
    if "lunch" in rel_time:
        return f"{today_str}T{TIME_MAP['lunch']}"
    if "breakfast" in rel_time:
        return f"{today_str}T{TIME_MAP['breakfast']}"
    if "morning" in rel_time:
        return f"{today_str}T{TIME_MAP['morning']}"
    if "night" in rel_time:
        return f"{today_str}T{TIME_MAP['night']}"
    if "bedtime" in rel_time:
        return f"{today_str}T{TIME_MAP['bedtime']}"
    # DEFAULT FALLBACK (If absolutely nothing matches, default to 9 AM tomorrow)
    return f"{today_str}T09:00:00"

def build_google_event(reminder_json):
    """
    Converts NLP JSON into a SINGLE Google Calendar Event.
    
    Features:
    1. Handles "Twice/Thrice a day" using BYHOUR in RRULE (Single event, multiple alerts).
    2. Converts "Months/Weeks" into total days to calculate correct recurrence COUNT.
    3. Supports Specific Days (Mon, Wed) and Intervals (Alternate days).
    """
    
    # --- 1. PARSE BASIC INPUTS --- #
    freq = reminder_json.get('frequency', '').lower() if reminder_json.get('frequency') else ""
    duration_str = reminder_json.get('duration', '').lower() if reminder_json.get('duration') else ""
    
    # Default Multiplier (Standard is 1 times a day)
    # This is used to multiply the total days. (e.g. 5 days * 2 times/day = 10 events)
    count_multiplier = 1 
    
    # Get the initial start time from your existing helper function
    start_iso = get_start_datetime(reminder_json)
    
    
    # --- 2. HANDLE "TWICE/THRICE" (The Multi-Dose Logic) --- #
    rrule_extras = []
    
    if "twice" in freq or "two times" in freq or "2 times" in freq:
        # Force start time to Morning (08:00) so the pattern starts correctly
        start_iso = start_iso.split('T')[0] + "T08:00:00"
        # Add 8 AM and 8 PM slots using BYHOUR
        rrule_extras.append("BYHOUR=8,20")
        rrule_extras.append("BYMINUTE=0")
        count_multiplier = 2

    elif "thrice" in freq or "three times" in freq or "3 times" in freq:
        # Force start time to Morning (08:00)
        start_iso = start_iso.split('T')[0] + "T08:00:00"
        # Add 8 AM, 1 PM, 8 PM slots
        rrule_extras.append("BYHOUR=8,13,20") 
        rrule_extras.append("BYMINUTE=0")
        count_multiplier = 3


    # --- 3. CALCULATE START & END TIMES --- #
    start_dt = datetime.datetime.fromisoformat(start_iso)
    # End time is just 15 mins after start (Standard for reminders)
    end_dt = start_dt + timedelta(minutes=15)
    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%S")


    # --- 4. BUILD RECURRENCE RULE (RRULE) --- #
    recurrence = []
    rrule_parts = []
    
    # A. Base Frequency
    if "weekly" in freq:
        rrule_parts.append("FREQ=WEEKLY")
    elif "alternate" in freq:
        rrule_parts.append("FREQ=DAILY;INTERVAL=2")
    else:
        # Default to DAILY for "twice a day", "every day", or if unspecified
        rrule_parts.append("FREQ=DAILY")
        
    # B. Add the BYHOUR magic (if we found twice/thrice logic earlier)
    if rrule_extras:
        rrule_parts.extend(rrule_extras)

    # C. Days of Week Mapping
    days = reminder_json.get('days_of_week')
    if days:
        day_map = {
            "Monday": "MO", "Tuesday": "TU", "Wednesday": "WE", 
            "Thursday": "TH", "Friday": "FR", "Saturday": "SA", "Sunday": "SU"
        }
        short_days = [day_map[d] for d in days if d in day_map]
        if short_days:
            rrule_parts.append(f"BYDAY={','.join(short_days)}")

    # D. DURATION CONVERTER (Months/Weeks -> Days -> Count)
    if duration_str:
        total_days = 0
        try:
            # Extract the numeric part (e.g. '2' from "2 months")
            num_match = re.search(r'(\d+)', duration_str)
            if num_match:
                number = int(num_match.group(1))
                
                # Convert units to days
                if "month" in duration_str:
                    total_days = number * 30  # Approx 30 days per month
                elif "week" in duration_str:
                    total_days = number * 7
                elif "day" in duration_str:
                    total_days = number
                    
                # Calculate final COUNT for Google
                # Formula: Total Days * Events Per Day
                if total_days > 0:
                    final_count = total_days * count_multiplier
                    rrule_parts.append(f"COUNT={final_count}")
        except:
            pass # Fail silently if string is unparsable

    # Assemble the final RRULE string
    if rrule_parts:
        recurrence.append("RRULE:" + ";".join(rrule_parts))


    # --- 5. CONSTRUCT FINAL EVENT OBJECT --- #
    event = {
        'summary': reminder_json.get('medication_name') or "Medication Reminder",
        'location': 'Home',
        'description': reminder_json.get('description') or "Take your medicine",
        'start': {
            'dateTime': start_iso,
            'timeZone': 'Asia/Kolkata',
        },
        'end': {
            'dateTime': end_iso,
            'timeZone': 'Asia/Kolkata',
        },
        'reminders': {
            'useDefault': False,
            'overrides': [{'method': 'popup', 'minutes': 10}],
        },
        'attendees': [
            {"email": "sounaksengupta9@gmail.com"},
        ]
    }
    
    if recurrence:
        event['recurrence'] = recurrence
        
    return event
