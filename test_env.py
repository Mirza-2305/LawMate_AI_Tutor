# test_env.py
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

print(f"Key found: {api_key is not None}")
print(f"Key starts with 'AIza': {api_key.startswith('AIza') if api_key else False}")
print(f"Key preview: {api_key[:15]}..." if api_key else "No key")