# comprehensive_test.py - Run this to verify everything
import os
from dotenv import load_dotenv
import google.generativeai as genai

print("="*60)
print("🔍 COMPREHENSIVE GEMINI API TEST")
print("="*60)

# Step 1: Load .env
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

print(f"\n1. Key loaded from .env: {'✅ YES' if api_key else '❌ NO'}")
if api_key:
    print(f"   Key preview: {api_key[:15]}...")
    print(f"   Starts with 'AIza': {'✅ YES' if api_key.startswith('AIza') else '❌ NO'}")

# Step 2: Test API connectivity
if api_key:
    print("\n2. Testing Gemini API connectivity...")
    try:
        genai.configure(api_key=api_key)
        models = genai.list_models()
        print("   ✅ API KEY IS VALID!")
        
        # Show available models
        print("\n3. Available models:")
        for model in models:
            if 'generateContent' in model.supported_generation_methods:
                print(f"   - {model.name}")
        
        print("\n" + "="*60)
        print("🎉 SUCCESS! Your key is working correctly.")
        print("You can now run: streamlit run app.py")
        print("="*60)
        
    except Exception as e:
        print(f"   ❌ API ERROR: {str(e)}")
        print("\n" + "="*60)
        print("🔴 PROBLEM: Key is loaded but API access is denied")
        print("\n💡 SOLUTION:")
        print("1. Go to https://aistudio.google.com/app/apikey")
        print("2. Create a NEW API key")
        print("3. Replace it in your .env file")
        print("   (must be: GEMINI_API_KEY=AIzaSy... with NO spaces)")
        print("="*60)
else:
    print("\n❌ No API key found in .env file")