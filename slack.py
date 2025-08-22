import asyncio
from agents import (Agent,Runner,
                    GuardrailFunctionOutput,
                    RunContextWrapper,TResponseInputItem,input_guardrail)
from agents.tool import function_tool
from typing import Optional
from pydantic import BaseModel
from pathlib import Path
import json
import os
import requests
from dotenv import load_dotenv
load_dotenv()

SLACK_BOT_TOKEN=os.environ.get("SLACK_API_KEY")
SLACK_WEBHOOK_URL=os.environ.get("SLACK_WEBHOOK_URL")
SLACK_CHANNEL_ID=os.environ.get("SLACK_Channel_ID")
# --------------------------Guardrail-------------------------------------------------

class SlackSecurityCheckup(BaseModel):
    is_unsafe:bool
    reasoning:str


guardrail_agent=Agent(
    name="Slack Guardrail Checker",
    instructions="You are a slack guardrail agent.",
    output_type=SlackSecurityCheckup,
    model="gpt-5-nano"
)

@input_guardrail
async def slack_guardrail(
    ctx:RunContextWrapper[None],
    agent:Agent,
    input:str|list[TResponseInputItem])->GuardrailFunctionOutput:
    result= await Runner.run(guardrail_agent,input,context=ctx.context)
    return GuardrailFunctionOutput(output_info=result.final_output, tripwire_triggered=result.final_output.is_unsafe)


@function_tool
def send_slack_notification(message:str,repo:str,channel:str,pr_number:int=None,event_type:str="unknown")->str:
    """Send a formatted notification to the team slack channel."""
    webhook_url=os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return "Error: SLACK_WEBHOOK_URL environment  variable not set"
    blocks=[
        {"type":"section","text":{"type":"mrkdwn","text":message}}]
    # if event_type and event_type.lower()=="pull_request" and  pr_number and str(pr_number).isdigit():
        
    #     value_payload = json.dumps({"repo": repo, "pr_number": pr_number})

        # blocks.append({
        #     "type":"actions",
        #     "elements":[
        #         {
        #             "type":"button",
        #             "text":{"type":"plain_text","text":"✅ Merge"},
        #             "style":"primary",
        #             "value":value_payload,
        #             "action_id":"merge_action"
        #         },
        #         {
        #             "type":"button",
        #             "text":{"type":"plain_text","text":"❌ Cancel"},
        #             "style":"danger",
        #             "value":value_payload,
        #             "action_id":"cancel_action"
        #         }
        #     ]
        # }
        # )

    payload={
            "channel":channel if channel else SLACK_CHANNEL_ID,
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
    model="gpt-5-nano",
    input_guardrails=[slack_guardrail]
)
