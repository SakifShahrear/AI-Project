import mimetypes
import os
import requests
from datetime import datetime
from dotenv import load_dotenv

# .env ফাইল থেকে ভেরিয়েবল লোড করা
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# URL এবং KEY চেক করা
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables are required in .env file")

def save_to_supabase(data: dict) -> bool:
    """সরাসরি REST API ব্যবহার করে ডেটাবেজে ডেটা সেভ করা"""
    url = f"{SUPABASE_URL}/rest/v1/certificates"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    
    try:
        # created_at ফিল্ডটি ডেটাবেজের ফরম্যাটে যুক্ত করা
        if "created_at" not in data:
            data["created_at"] = datetime.now().isoformat()
            
        response = requests.post(url, json=data, headers=headers)
        if response.status_code in [200, 201]:
            print("✓ Data saved successfully to Supabase!")
            return True
        else:
            print(f"✗ Supabase Error: {response.text}")
            return False
    except Exception as e:
        print(f"✗ Connection Error: {str(e)}")
        return False

def upload_certificate_image(file_path: str, bucket_name: str = "cert-uploads") -> str:
    """সরাসরি Storage API ব্যবহার করে ছবি আপলোড করা"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    file_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.path.basename(file_path)}"
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket_name}/{file_name}"
    
    with open(file_path, "rb") as f:
        file_data = f.read()
    
    content_type, _ = mimetypes.guess_type(file_path)
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": content_type or "application/octet-stream"
    }
    
    try:
        response = requests.post(url, data=file_data, headers=headers)
        if response.status_code == 200:
            public_url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket_name}/{file_name}"
            print(f"✓ Image uploaded successfully: {public_url}")
            return public_url
        else:
            print(f"✗ Upload Error: {response.text}")
            raise Exception("Failed to upload image to Supabase Storage")
    except Exception as e:
        print(f"✗ Storage Connection Error: {str(e)}")
        raise

def save_verification_result(file_url: str, competition_name: str, organizer: str, accuracy_score: float, status: str) -> dict:
    """অ্যাপের সাথে সামঞ্জস্যপূর্ণ সহজ সেভ ফাংশন"""
    record = {
        "competition_name": competition_name,
        "organizer": organizer,
        "accuracy_score": accuracy_score,
        "image_url": file_url,
        "status": status
    }
    
    if save_to_supabase(record):
        return record
    return {}

def get_all_verification_results(limit: int = 100) -> list:
    """ডেটাবেজ থেকে আগের সব রেজাল্ট নিয়ে আসা"""
    url = f"{SUPABASE_URL}/rest/v1/certificates?select=*&order=created_at.desc&limit={limit}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"✗ Error fetching history: {e}")
        return []

# নিচের ফাংশনগুলো আগের কোডের সাথে মিল রাখার জন্য রাখা হয়েছে
def insert_certificate_record(competition_name, organizer, accuracy_score, image_url=None, status="Pending"):
    return save_verification_result(image_url, competition_name, organizer, accuracy_score, status)

def upload_and_record_certificate(file_path, competition_name, organizer, accuracy_score, status="Verified"):
    img_url = upload_certificate_image(file_path)
    return save_verification_result(img_url, competition_name, organizer, accuracy_score, status)