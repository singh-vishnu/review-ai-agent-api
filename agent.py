

import json
import random
import sqlite3
from datetime import datetime
from typing import TypedDict, Literal, Optional, List, Dict

from langgraph.graph import StateGraph, START, END
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field
import smtplib
from email.mime.text import MIMEText



import os

# Direct set (temporary until we fix dotenv)
os.environ['EMAIL_USER'] = 'vishnusingh602@gmail.com'
os.environ['EMAIL_PASSWORD'] = 'iyvb valn xunq aiau'


model = ChatOllama(model="llama3", temperature=0)


# Create Schemas
class SentimentSchema(BaseModel):
    sentiment: Literal['positive', 'negative'] = Field(description='Sentiment of review')

class DiagnosisSchema(BaseModel):
    issue_type: Literal['ux', 'Performance', 'bug', 'support', 'other'] = Field(description='Issue category')
    tone: Literal['angry', 'frustrated', 'disappointed', 'calm'] = Field(description='Emotional tone')
    urgency: Literal['low', 'medium', 'high'] = Field(description='Urgency level')

# 👇 ADD THIS NEW SCHEMA HERE 👇
class ActionSchema(BaseModel):
    """Schema for agent actions"""
    action_type: Literal['create_ticket', 'escalate', 'respond', 'log_only'] = Field(
        description='Type of action to take'
    )
    assignee_team: Literal['support', 'engineering', 'ux', 'management'] = Field(
        description='Team to handle this issue'
    )
    priority: Literal['P0', 'P1', 'P2', 'P3'] = Field(
        description='Priority level: P0=Critical, P1=High, P2=Medium, P3=Low, P4=Very Low'
    )

# Your existing models
sentiment_model = model.with_structured_output(SentimentSchema)
diagnosis_model = model.with_structured_output(DiagnosisSchema)
# 👇 ADD THIS NEW MODEL 👇
action_model = model.with_structured_output(ActionSchema)


# DATABASE SETUP (SQLite)
conn = sqlite3.connect('reviews.db', check_same_thread=False)
conn.execute('''
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY,
        email TEXT,
        review TEXT,
        sentiment TEXT,
        issue_type TEXT,
        tone TEXT,
        urgency TEXT,
        ticket_id TEXT,
        response TEXT,
        created_at DATETIME
    )
''')
conn.commit()


def save_to_db(email, review, sentiment, diagnosis, ticket_id, response):
    conn.execute('''
        INSERT INTO reviews (email, review, sentiment, issue_type, tone, urgency, ticket_id, response, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (email, review, sentiment, diagnosis.get('issue_type'), diagnosis.get('tone'), 
          diagnosis.get('urgency'), ticket_id, response, datetime.now()))
    conn.commit()

def get_customer_history(email):
    cursor = conn.execute('''
        SELECT sentiment, issue_type, created_at FROM reviews 
        WHERE email = ? ORDER BY created_at DESC LIMIT 5
    ''', (email,))
    return cursor.fetchall()


#  EMAIL TOOL
def send_email(to_email, subject, body):
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = os.getenv('EMAIL_USER')
        msg['To'] = to_email
        
        print(f"📧 Sending email to {to_email}...")  # Debug print
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASSWORD'))
            server.send_message(msg)
        
        print("✅ Email sent successfully!")
        return True
    except Exception as e:
        print(f"❌ Email failed: {e}")
        return False


#  AGENT STATE
class AgentState(TypedDict):
    review: str
    email: str
    name: str
    sentiment: str
    diagnosis: dict
    ticket_id: str
    response: str
    history: list
    action_plan: dict


# Create AGENT NODES Function =
def analyze_sentiment(state: AgentState) -> AgentState:
    result = sentiment_model.invoke(f"Sentiment of: {state['review']}")
    return {"sentiment": result.sentiment}

def diagnose_issue(state: AgentState) -> AgentState:
    result = diagnosis_model.invoke(f"Diagnose this issue: {state['review']}")
    return {"diagnosis": result.model_dump()}


def plan_action(state: AgentState) -> AgentState:
    """Determine which team should handle this issue"""
    
    prompt = f"""
    Based on this review, determine:
    1. What action to take
    2. Which team should handle it
    3. Priority level
    
    Review: {state['review']}
    Issue Type: {state['diagnosis']['issue_type']}
    Tone: {state['diagnosis']['tone']}
    Urgency: {state['diagnosis']['urgency']}
    
    Return:
    - action_type: create_ticket/escalate/respond/log_only
    - assignee_team: support/engineering/ux/management
    - priority: P0(emergency)/P1(high)/P2(medium)/P3(low)
    """
    
    result = action_model.invoke(prompt)
    return {"action_plan": result.model_dump()}

def create_ticket(state: AgentState) -> AgentState:
    ticket_id = f"TICKET-{random.randint(1000, 9999)}"
    
    # Get action plan (default values if not set)
    action_plan = state.get('action_plan', {})
    team = action_plan.get('assignee_team', 'support')
    priority = action_plan.get('priority', 'P2')
    
    # Your email (support person)
    your_email = os.getenv('EMAIL_USER')
    
    # Email to YOU (vishnu) with team assignment
    email_body = f"""
    🎫 NEW TICKET: {ticket_id}
    
    ASSIGNMENT:
    -----------
    Assigned Team: {team.upper()}
    Priority: {priority}
    
    CUSTOMER:
    ---------
    Name: {state['name']}
    Email: {state['email']}
    
    ISSUE:
    ------
    Type: {state['diagnosis']['issue_type']}
    Tone: {state['diagnosis']['tone']}
    Urgency: {state['diagnosis']['urgency']}
    
    REVIEW:
    -------
    "{state['review']}"
    
    Please forward this to the {team} team.
    """
    
    # Send to YOU first
    send_email(
        to_email=your_email,  # Comes to vishnu@gmail.com
        subject=f"[{team.upper()}] New Ticket: {ticket_id}",
        body=email_body
    )
    
    # Also send acknowledgment to customer with their name
    send_email(
        state['email'],  # Customer email
        f"Support Ticket Created: {ticket_id}",
        f"Dear {state['name']},\n\nWe've created ticket {ticket_id} for your issue. Our team will contact you soon.\n\nBest regards,\n\nSupport Team"
    )
    
    return {"ticket_id": ticket_id}

def get_history(state: AgentState) -> AgentState:
    return {"history": get_customer_history(state['email'])}

def generate_response(state: AgentState) -> AgentState:
    customer_name = state.get('name', 'Customer')
    if state['sentiment'] == 'positive':
        prompt = f"""Write a brief thank you reply (max 100 words) to {customer_name} for this review: "{state['review']}"
        Use their name {customer_name} in the response. Sign as "Support Team"."""
    else:
        d = state['diagnosis']
        prompt = f"""Write a brief empathetic reply (max 100 words) to {customer_name} for their {d['issue_type']} issue.
        Tone: {d['tone']}, Urgency: {d['urgency']}. Review: "{state['review']}"
        Use their name {customer_name} in the response. Sign as "Support Team"."""
    
    response = model.invoke(prompt).content
    
    # Save to database
    save_to_db(state['email'], state['review'], state['sentiment'], 
               state['diagnosis'], state.get('ticket_id'), response)
    
    return {"response": response}

def route_sentiment(state: AgentState) -> Literal['positive', 'negative']:
    return 'negative' if state['sentiment'] == 'negative' else 'positive'


#  BUILD GRAPH 
# graph nodes
builder = StateGraph(AgentState)

builder.add_node("sentiment", analyze_sentiment)
builder.add_node("history", get_history)
builder.add_node("diagnose", diagnose_issue)
builder.add_node("plan", plan_action) 
builder.add_node("ticket", create_ticket)
builder.add_node("respond", generate_response)

# edges
builder.add_edge(START, "sentiment")
builder.add_edge("sentiment", "history")
builder.add_conditional_edges("history", route_sentiment, {
    "negative": "diagnose",
    "positive": "respond"
})
builder.add_edge("diagnose", "plan")          # 👈 ADD THIS EDGE
builder.add_edge("plan", "ticket")
builder.add_edge("ticket", "respond")
builder.add_edge("respond", END)

agent = builder.compile()


agent


#  RUN AGENT
def process_review(review_text, customer_email, customer_name):
    result = agent.invoke({
        "review": review_text,
        "email": customer_email,
        "name": customer_name,
        "sentiment": "",
        "diagnosis": {},
        "ticket_id": "",
        "response": "",
        "history": []
    })
    
    print(f"\n📝 Review: {review_text[:200]}...")
    print(f"😊 Sentiment: {result['sentiment']}")
    if result.get('diagnosis'):
        print(f"🔍 Issue: {result['diagnosis']['issue_type']} ({result['diagnosis']['urgency']})")
    if result.get('ticket_id'):
        print(f"🎫 Ticket: {result['ticket_id']}")
    print(f"💬 Response: {result['response'][:320]}...")
    print(f"📊 History: {len(result['history'])} previous interactions")
    
    return result


# ==== 9. TEST ====
if __name__ == "__main__":
    # Test with your email
    CUSTOMER_EMAIL = "shridharkumar2708@gmail.com"  # Replace with your email
    CUSTOMER_NAME = "shridhar kumar"
    
    test_reviews = [
    # UX Team
    "The navigation menu is very confusing, I can't find where to change my password",
    
    # Engineering Team (Bug)
    "App crashes every time I try to upload photos",
    
    # Engineering Team (Performance)
    "The app is extremely slow, takes 30 seconds to load",
    
    # Support Team
    "How do I reset my password? I forgot it",
    
    # 👇 MANAGEMENT TEAM 👇
    "I want to cancel my subscription and request a refund",
    "Your pricing is too high, I'm switching to competitor",
    "I need an enterprise license for my company of 100 people",
    "I have a legal complaint about your terms of service",
    "I want to speak with your manager about poor customer service"
]
    
    for review in test_reviews:
        process_review(review, CUSTOMER_EMAIL, CUSTOMER_NAME)
    
    print("\n✅ All done! Check reviews.db for saved data.")

 
#  





