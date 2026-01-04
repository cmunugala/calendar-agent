from app.agent import run_assistant
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
import os
from openai import OpenAI
from typing import List

load_dotenv()

app = FastAPI()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class ChatRequest(BaseModel):
    message: str
    history: List[dict] = []
    timezone: str = "America/Los_Angeles"

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    messages = request.history + [{"role": "user", "content": request.message}]
    response = run_assistant(
        client=client, 
        messages=messages, 
        user_timezone=request.timezone
    ) 
    return {"response": response}


