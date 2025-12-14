from flask import Flask, request, jsonify
from medication import extract_json
from reminder import build_google_event, SCOPES
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

app = Flask(__name__)

# -------------------- GOOGLE CALENDAR AUTHORIZATION -------------------- #
def get_calendar_service():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=5000)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)

# -------------------- MAIN API ENDPOINT -------------------- #
@app.route("/reminder", methods=["POST"])
def create_reminder():
    try:
        data = request.get_json(force=True)
        prompt = data.get("prompt")

        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400

        # 1. Extract structured reminders using LLM
        extracted = extract_json(prompt)
        reminders = extracted.get("reminders", [])

        if not reminders:
            return jsonify({"error": "No reminders found"}), 400

        # 2. Get Google Calendar service
        service = get_calendar_service()

        # 3. Create calendar events
        created_events = []
        for reminder in reminders:
            event_body = build_google_event(reminder)
            event = service.events().insert(
                calendarId="primary",
                body=event_body
            ).execute()
            created_events.append(event.get("htmlLink"))

        # 4. Respond back to client
        return jsonify({
            "status": "success",
            "events_created": created_events
        }), 200

    except HttpError as e:
        return jsonify({
            "error": "Google Calendar API error",
            "details": str(e)
        }), 500

    except Exception as e:
        return jsonify({
            "error": "Internal Server Error",
            "details": str(e)
        }), 500

# -------------------- RUN SERVER -------------------- #
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 6000))
    app.run(host="0.0.0.0", port=port)

