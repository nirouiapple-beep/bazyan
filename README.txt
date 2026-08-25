BAZYAN AI FINAL ALL-IN-ONE

Includes:
- automatic recurring research
- SQLite database
- historical report comparison
- local dashboard at http://127.0.0.1:8787
- email alerts
- optional WhatsApp alerts
- saved reports
- alert levels and score threshold

Your existing Gmail App Password stays in the Windows environment
variable BAZYAN_EMAIL_APP_PASSWORD.

WhatsApp is intentionally optional. It requires your own Meta/WhatsApp
Cloud API credentials:
BAZYAN_WHATSAPP_TOKEN
BAZYAN_WHATSAPP_PHONE_NUMBER_ID
BAZYAN_WHATSAPP_TO
BAZYAN_WHATSAPP_GRAPH_VERSION

Run:
    pip install -r requirements.txt
    python agent.py

The program runs immediately and then repeats every 24 hours while
the computer/process is running.
