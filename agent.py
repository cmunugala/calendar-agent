import json
from openai import OpenAI,pydantic_function_tool
import os
from pydantic import BaseModel,Field
from utils.google_calendar_utils import list_events_on_date


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# define pydantic models for responses

class CalendarEventsResponse(BaseModel):
    date:str
    time:str
    events_description:str = Field(description="A natural language response to user's question.")

#define tools and their input models 

class ListEvents(BaseModel):
    target_date_str: str = Field("The date to list events for, in YYYY-MM-DD format.")

tools = [pydantic_function_tool(ListEvents, name="list_events_on_date")]

# logic to actually call function

def call_function(name, args):
    if name == "list_events_on_date":
        return list_events_on_date(**args)


# main agent loop

messages = [
        {"role":"system","content":"You are a helpful assistant."},
        {"role":"user","content":"What events do I have on 2025-06-15?"},
    ]

completion = client.beta.chat.completions.parse(
    model = "gpt-4o-mini",
    messages = messages,
    tools = tools
)


for tool_call in completion.choices[0].message.tool_calls:
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)
    messages.append(completion.choices[0].message)

    result = call_function(name,args)
    messages.append({"role":"tool","tool_call_id":tool_call.id,"content":json.dumps(result)})

completion2 = client.beta.chat.completions.parse(
    model = "gpt-4o-mini",
    messages = messages,
    tools = tools,
    response_format = CalendarEventsResponse
)

final_response = completion2.choices[0].message.parsed


#print(completion.model_dump())
#print(completion2.model_dump())
print(final_response.events_description)


# response = completion.choices[0].message.parsed.time
# print(response)