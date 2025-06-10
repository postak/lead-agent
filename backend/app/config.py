# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
  model_config = SettingsConfigDict(
      env_file='./app/.env', env_file_encoding='utf-8'
  )
  APP_NAME: str = "Lead Qualification Voice Agent"
  # LLM Provider
  GOOGLE_PROJECT_ID: str
  GOOGLE_LOCATION: str
  GOOGLE_GENAI_USE_VERTEX_AI: str
  GOOGLE_API_KEY: str

  # Telephony Service
  TWILIO_ACCOUNT_SID: str
  TWILIO_AUTH_TOKEN: str
  TWILIO_VIRTUAL_PHONE_NUMBER: str

  # For local testing, this will be your ngrok forwarding URL (e.g., "https://xxxxxxxx.ngrok.io")
  BASE_URL: str = 'https://twilio-agent-682040119888.us-central1.run.app'


settings = Settings()
