from fastapi import FastAPI
from pydantic import BaseModel
from agent import agent
import traceback

app = FastAPI()

class ReviewRequest(BaseModel):
    review: str
    email: str
    name: str

@app.post("/review")
def run_agent(data: ReviewRequest):
    print(f"Received: {data}")
    
    try:
        # Provide ALL required fields that the agent expects
        result = agent.invoke({
            "review": data.review,
            "email": data.email,
            "name": data.name,
            "sentiment": "",        # Add empty sentiment
            "diagnosis": {},         # Add empty diagnosis dict
            "ticket_id": "",         # Add empty ticket_id
            "response": "",          # Add empty response
            "history": [],           # Add empty history list
            "action_plan": {}        # Add empty action_plan (optional but good)
        })
        print(f"Agent result: {result}")
        return result
    except Exception as e:
        print(f"Error in agent: {str(e)}")
        print(traceback.format_exc())
        return {
            "sentiment": "neutral", 
            "response": f"Error processing review: {str(e)}"
        }
