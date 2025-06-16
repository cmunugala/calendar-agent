from openai import OpenAI
import os
from pydantic import BaseModel

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# define pydantic models for responses

class DateResponse(BaseModel):
    date:str
    time:str

completion = client.beta.chat.completions.parse(
    model = "gpt-4o-mini",
    messages = [
        {"role":"system","content":"You are a helpful assistant."},
        {"role":"user","content":"Give me the date and time."},
    ],
    response_format = DateResponse,
)

response = completion.choices[0].message.parsed.time
print(response)