from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = 'tonal-shore-434209-q7-fe014e05820d.json'
CALENDAR_ID = '98696f3692fc8e8139038fc22ecf7e7ac38f0a00dd2ff409002bbbb1865f8d35@group.calendar.google.com'

def update_calendar_timezone():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('calendar', 'v3', credentials=creds)

    # 1. Get current settings
    calendar = service.calendars().get(calendarId=CALENDAR_ID).execute()
    print(f"Current Timezone: {calendar.get('timeZone')}")

    # 2. Update to Asia/Kolkata
    if calendar.get('timeZone') != 'Asia/Kolkata':
        print("Updating timezone to Asia/Kolkata...")
        new_calendar = {'timeZone': 'Asia/Kolkata'}
        updated_calendar = service.calendars().patch(calendarId=CALENDAR_ID, body=new_calendar).execute()
        print(f"New Timezone: {updated_calendar.get('timeZone')}")
    else:
        print("Timezone is already Asia/Kolkata.")

if __name__ == '__main__':
    update_calendar_timezone()
