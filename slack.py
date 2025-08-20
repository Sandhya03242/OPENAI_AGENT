from dotenv import load_dotenv
import os
import requests
from fastapi import FastAPI
from agents import Agent, function_tool
import json
from dotenv import load_dotenv
load_dotenv()

app=FastAPI()
SLACK_BOT_TOKEN=os.environ.get("SLACK_API_KEY")


@function_tool
def send_slack_notification(message:str,repo,pr_number,event_type:str="unknown")->str:
    """Send a formatted notification to the team slack channel."""
    webhook_url=os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return "Error: SLACK_WEBHOOK_URL environment  variable not set"
    blocks=[
        {"type":"section","text":{"type":"mrkdwn","text":message}}]
    if event_type and event_type.lower()=="pull_request" and  pr_number and str(pr_number).isdigit():
        
        value_payload = json.dumps({"repo": repo, "pr_number": pr_number})

        blocks.append({
            "type":"actions",
            "elements":[
                {
                    "type":"button",
                    "text":{"type":"plain_text","text":"✅ Merge"},
                    "style":"primary",
                    "value":value_payload,
                    "action_id":"merge_action"
                },
                {
                    "type":"button",
                    "text":{"type":"plain_text","text":"❌ Cancel"},
                    "style":"danger",
                    "value":value_payload,
                    "action_id":"cancel_action"
                }
            ]
        }
        )

    payload={
            "blocks":blocks,
            "text":message,
            "mrkdwn":True
        }
    try:
        response=requests.post(webhook_url,json=payload,timeout=10)
        if response.status_code==200:
            return "✅ Message sent successfully to slack."
        else:
            return f"❌ Failed to send message. Status: {response.status_code}, Response: {response.text}"
    except requests.exceptions.Timeout:
        return "❌ Request timed out. Check your internet connection and try again."
    except requests.exceptions.ConnectionError:
        return "❌ Connection error. Check your  internet connection and webhook URL."
    except Exception as e:
        return f"❌ Error sending message: {str(e)}"


slack_agent=Agent(
    name="slack agent",
    instructions="slack agent that get slack notification",
    tools=[send_slack_notification],
    model="gpt-5-nano"
)
