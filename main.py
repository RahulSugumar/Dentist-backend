from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional
import uvicorn
from supabase import create_client, Client
import bcrypt

# --- Configuration ---
# REPLACE THESE WITH YOUR ACTUAL SUPABASE CREDENTIALS
SUPABASE_URL = "https://mdxblkkzyblhiileioxt.supabase.co"
SUPABASE_KEY = "sb_publishable_-y2Gqu0uX-HsUO6v6Zc7ug_RFI1jsnK" 
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)