import asyncio
from agents import (Agent,Runner, SQLiteSession,
                    GuardrailFunctionOutput,InputGuardrailTripwireTriggered,
                    RunContextWrapper,TResponseInputItem,input_guardrail)
from agents.tool import HostedMCPTool, function_tool
from dataclasses import dataclass
from typing import List, Dict,TypedDict, Optional
from pydantic import BaseModel
from pathlib import Path
import json
from dotenv import load_dotenv
load_dotenv()

EVENTS_FILE=Path(__file__).parent / "github_events.json"

# --------------------------Guardrail-------------------------------------------------

class GithubSecurityCheckup(BaseModel):
    is_unsafe:bool
    reasoning:str


guardrail_agent=Agent(
    name="Github Guardrail Checker",
    instructions="You are a github guardrail agent.",
    output_type=GithubSecurityCheckup,
    model="gpt-5-nano"
)

@input_guardrail
async def security_guardrail(
    ctx:RunContextWrapper[None],
    agent:Agent,
    input:str|list[TResponseInputItem])->GuardrailFunctionOutput:
    result= await Runner.run(guardrail_agent,input,context=ctx.context)
    return GuardrailFunctionOutput(output_info=result.final_output, tripwire_triggered=result.final_output.is_unsafe)


# --------------------HostTool--------------------------------------------------

# @dataclass
# class Mcp:
#     server_url:str
#     """MCP server URL."""
#     timeout:int=30
#     """Request timeout in seconds"""


# github_mcp_tool = HostedMCPTool(
#     tool_config={
#         # "type": "mcp",                  
#         "server_url": "http://localhost:8080",  
#         "server_label": "local_github_server",
#         "timeout": 30
#     }
# )
class Event(BaseModel):
    type:str
    action:Optional[str]=None
    repository:Optional[str]=None
    title:Optional[str]=None
    description:Optional[str]=None
    sender:Optional[str]=None

class EventList(BaseModel):
    events:List[Event]

@function_tool
def get_recent_events()->EventList:
    """Github events"""
    if not EVENTS_FILE.exists():
        return EventList(events=[])
    with open(EVENTS_FILE) as f:
        raw_events=json.load(f)
    events=[Event(
        type=e.get("event_type",""),
        action=e.get("action"),
        repository=e.get("repository",{}).get("full_name"),
        title=e.get("title"),
        description=e.get("description")
    )for e in raw_events]
    return EventList(events=events)

@function_tool
def summarize_latest_event(input:EventList)->str:
    """Summarize the most recent GitHub event"""
    events=input.events
    if not events:
        return "No GitHub events received yet."
    latest=events[-1]
    repo=latest.repository
    event_type=latest.type
    action=latest.action
    return f"The latest GitHub events is a {event_type} ({action}) in {repo}"

# ---------------- gtihub Agent------------------------------------------------

github_agent=Agent(
    name="github Agent",
    instructions="You are github agent to response to github events and actions",
    model="gpt-5-nano",
    input_guardrails=[security_guardrail],
    tools=[get_recent_events,summarize_latest_event]
)


