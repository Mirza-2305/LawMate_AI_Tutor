# check_models.py - Run this to see available models
import os
import google.generativeai as genai

# Configure with your API key
api_key = os.getenv("GEMINI_API_KEY") or "YOUR_API_KEY_HERE"
genai.configure(api_key=api_key)

print("🔍 Checking available models...\n")

try:
    models = genai.list_models()
    
    print("✅ Models you have access to:\n")
    for model in models:
        if 'generateContent' in model.supported_generation_methods:
            print(f"Model: {model.name}")
            print(f"  Description: {model.description}")
            print(f"  Supported methods: {model.supported_generation_methods}")
            print()
    
except Exception as e:
    print(f"❌ Error: {e}")
    print("\n💡 Possible issues:")
    print("1. API key not set correctly")
    print("2. Project not enabled in Google Cloud Console")
    print("3. Region restrictions")