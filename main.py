from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, validator
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import uvicorn
from supabase import create_client, Client
import bcrypt
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime

# --- Configuration ---
# REPLACE THESE WITH YOUR ACTUAL SUPABASE CREDENTIALS
SUPABASE_URL = "https://mdxblkkzyblhiileioxt.supabase.co"
SUPABASE_KEY = "sb_publishable_-y2Gqu0uX-HsUO6v6Zc7ug_RFI1jsnK" 
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Google Calendar Configuration
SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = 'tonal-shore-434209-q7-fe014e05820d.json'
# The ID of the calendar to add events to. 'primary' usually refers to the service account's calendar.
# If you want to add to your personal calendar, you must share that calendar with the service account email
# and use your specific Calendar ID (e.g., your gmail address) here.
CALENDAR_ID = '98696f3692fc8e8139038fc22ecf7e7ac38f0a00dd2ff409002bbbb1865f8d35@group.calendar.google.com' 

app = FastAPI(title="Dentist Website API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # allow all origins
    allow_credentials=True,
    allow_methods=["*"],        # allow all HTTP methods
    allow_headers=["*"],        # allow all headers
)

# --- Helper Functions ---
def verify_password(plain_password, hashed_password):
    # bcrypt.checkpw expects bytes
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password):
    # bcrypt.hashpw expects bytes, returns bytes
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def get_calendar_service():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print("Service account file not found.")
        return None
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)
        return service
    except Exception as e:
        print(f"Error authenticating with Google Calendar: {e}")
        return None

# --- Data Models (Pydantic) ---
class UserRegister(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone_number: str = Field(..., min_length=10)
    password: str = Field(..., min_length=6, max_length=72)
    age: Optional[int] = Field(None, ge=0)
    @validator('phone_number')
    def validate_phone(cls, v):
        if not v.isdigit():
             raise ValueError('Phone number must contain only digits')
        return v
class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=72)

class AppointmentCreate(BaseModel):
    full_name: str
    phone_number: str
    email: EmailStr
    appointment_date: str # Expect 'YYYY-MM-DD'
    appointment_time: str # Expect 'HH:MM'
    service: str

# --- Endpoints ---
@app.get("/")
def read_root():
    return {"message": "Welcome to the Dentist Website API"}

@app.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(user: UserRegister):
    # 1. Check if email exists
    try:
        # Supabase select query
        existing = supabase.table("users").select("email").eq("email", user.email).execute()
        if existing.data:
            raise HTTPException(status_code=400, detail="Email already registered")
            
        # 2. Hash password
        hashed_pwd = get_password_hash(user.password)
        
        # 3. Insert into Supabase
        user_data = {
            "full_name": user.full_name,
            "email": user.email,
            "phone_number": user.phone_number,
            "age": user.age,
            "password_hash": hashed_pwd
        }
        
        response = supabase.table("users").insert(user_data).execute()
        
        # Check for errors in response
        if not response.data:
             raise HTTPException(status_code=500, detail="Failed to register user")
        return {"message": "User registered successfully", "email": user.email}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Catch unexpected errors
        print(f"Error: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
@app.post("/login")
def login_user(user: UserLogin):
    try:
        # 1. Fetch user by email
        response = supabase.table("users").select("*").eq("email", user.email).execute()
        
        if not response.data:
            raise HTTPException(status_code=401, detail="Invalid email or password")
            
        user_record = response.data[0]
        
        # 2. Verify password
        if not verify_password(user.password, user_record["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
            
        return {"message": "Login successful", "user_id": user_record["id"], "email": user_record["email"]}
        
    except Exception as e:
        print(f"Error: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/book-appointment")
def book_appointment(appt: AppointmentCreate):
    try:
        # 1. Validate Date and Time
        try:
            start_dt = datetime.datetime.strptime(f"{appt.appointment_date} {appt.appointment_time}", "%Y-%m-%d %H:%M")
            end_dt = start_dt + datetime.timedelta(hours=1)
            
            # Format explicitly for ISO 8601
            start_iso = start_dt.isoformat()
            end_iso = end_dt.isoformat()
        except ValueError:
             raise HTTPException(status_code=400, detail="Invalid date or time format")
        
        # 2. Check for Conflicts in Database
        # Query for any appointment on the same date and time that is NOT cancelled
        existing_appt = supabase.table("appointments").select("*").eq("appointment_date", appt.appointment_date).eq("appointment_time", appt.appointment_time).neq("status", "cancelled").execute()
        
        if existing_appt.data:
             # Calculate next available slot (1 hour later)
             next_slot = start_dt + datetime.timedelta(hours=1)
             next_slot_str = next_slot.strftime("%H:%M")
             raise HTTPException(
                 status_code=400, 
                 detail=f"Time slot {appt.appointment_time} is already booked. Please try {next_slot_str} or another time."
             )

        # 3. Create Event Body for Google Calendar
        calendar_event_body = {
            'summary': f"Dentist Appt: {appt.service} - {appt.full_name}",
            'location': 'T Nagar Dental Clinic',
            'description': f"Appointment for {appt.service}.\nPatient: {appt.full_name}\nPhone: {appt.phone_number}",
            'start': {
                'dateTime': start_iso,
                'timeZone': 'Asia/Kolkata', # Adjust timezone as needed
            },
            'end': {
                'dateTime': end_iso,
                'timeZone': 'Asia/Kolkata',
            },
            # Note: Removed 'attendees' because Service Accounts cannot invite guests 
            # without Domain-Wide Delegation (Business Account).
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 30},
                ],
            },
        }

        # 2. Call Google Calendar API
        service = get_calendar_service()
        google_event_id = None
        
        if service:
            try:
                event = service.events().insert(calendarId=CALENDAR_ID, body=calendar_event_body).execute()
                google_event_id = event.get('id')
                print(f"Event created: {event.get('htmlLink')}")
            except Exception as google_err:
                print(f"Failed to create Google Calendar event: {google_err}")
                # We continue to save to Database even if Calendar fails, but log it
        
        # 3. Save to Supabase
        appt_data = {
            "full_name": appt.full_name,
            "phone_number": appt.phone_number,
            "appointment_date": appt.appointment_date,
            "appointment_time": appt.appointment_time,
            "service": appt.service,
            "google_event_id": google_event_id,
            "status": "confirmed" if google_event_id else "pending"
        }
        
        response = supabase.table("appointments").insert(appt_data).execute()
        
        if not response.data:
             raise HTTPException(status_code=500, detail="Failed to save appointment to database")
             
        return {"message": "Appointment booked successfully", "google_event_link": f"https://www.google.com/calendar/event?eid={google_event_id}" if google_event_id else None}

    except Exception as e:
        print(f"Error booking appointment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)