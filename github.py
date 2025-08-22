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

class Event(BaseModel):
    type:str
    action:Optional[str]=None
    repository:Optional[str]=None
    title:Optional[str]=None
    description:Optional[str]=None
    sender:Optional[str]=None
    pr_number:Optional[int]=None
    timestamp:Optional[str]=None
    base_branch:Optional[str]=None
    compare_branch:Optional[str]=None

class EventList(BaseModel):
    events:List[Event]

def _get_recent_events() -> EventList:
    if not EVENTS_FILE.exists():
        return EventList(events=[])
    with open(EVENTS_FILE) as f:
        raw_events = json.load(f)

    events = []
    for e in raw_events:
        events.append(Event(
            type=e.get("event_type", ""),
            action=e.get("action"),
            repository=e.get("repository", {}).get("full_name"),
            title=e.get("title") or e.get("head_commit", {}).get("message"),
            description=e.get("description") or (
                e.get("commits", [{}])[0].get("message") if "commits" in e else None
            ),
            sender=e.get("sender", {}).get("login"),
            pr_number=e.get("number"),
            timestamp=e.get("head_commit", {}).get("timestamp") if "head_commit" in e else e.get("created_at"),
            base_branch=e.get("repository", {}).get("default_branch"),
            compare_branch=e.get("ref")
        ))

    return EventList(events=events)


get_recent_events = function_tool(_get_recent_events)


def _summarize_latest_event(input: EventList) -> str:
    events = input.events
    if not events:
        return "No GitHub events received yet."
    
    latest = events[-1]
    return (
        f"🔔 New GitHub event: {latest.type or 'N/A'} on repository: {latest.repository or 'N/A'}\n"
        f"- Title: {latest.title or 'N/A'}\n"
        f"- Description: {latest.description or 'N/A'}\n"
        f"- Timestamp: {latest.timestamp or 'N/A'}\n"
        f"- User: {latest.sender or 'N/A'}\n"
        f"- Base Branch: {latest.base_branch or 'N/A'}\n"
        f"- Compare Branch: {latest.compare_branch or 'N/A'}"
    )
summarize_latest_event = function_tool(_summarize_latest_event)

# ---------------- gtihub Agent------------------------------------------------

github_agent=Agent(
    name="github Agent",
    instructions="You are github agent to response to github events and actions",
    model="gpt-5-nano",
    input_guardrails=[security_guardrail],
    tools=[get_recent_events,summarize_latest_event]
)


