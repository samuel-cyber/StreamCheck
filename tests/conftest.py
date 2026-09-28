"""Keep the suite hermetic: tests must never use a real Gemini key from a local .env."""
import os

os.environ["GEMINI_API_KEY"] = ""
