import asyncio
from agents import (Agent,Runner,
                    GuardrailFunctionOutput,
                    RunContextWrapper,TResponseInputItem,input_guardrail)
from agents.tool import function_tool
from typing import List, Optional
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
    model="gpt-5-mini"
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


@function_tool
def get_recent_events() -> EventList:
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

@function_tool
def get_repository_status()->str:
    if not EVENTS_FILE.exists():
        return "No events recorded yet for this repository.."
    with open(EVENTS_FILE) as f:
        events=json.load(f)
    if not events:
        return "No events recorded yet for this repository."
    pr_events=[e for e in events if e.get("event_type")=="pull_request"]
    push_events=[e for e in events if e.get("event_type")=="push"]
    issue_events=[e for e in events if e.get("event_type")=="issues"]
    summary=[]
    summary.append(f"Repository: {events[-1].get('repository',{}).get('full_name','unknown')}")
    summary.append(f"Open PRs: {len(pr_events)}")
    summary.append(f"Pushes: {len(push_events)}")
    summary.append(f"Issues: {len(issue_events)}")
    summary.append(f"Latest activity: {events[-1].get('event_type')}({events[-1].get('action')}) at {events[-1].get('timestamp')}")
    return "\n".join(summary)



@function_tool
def summarize_latest_event(input: EventList) -> str:
    events = input.events
    if not events:
        return "No GitHub events received yet."
    
    latest = events[-1]
    return (
        f"🔔 New GitHub event: {latest.type or 'N/A'}({latest.action}) on repository: {latest.repository or 'N/A'}\n"
        f"- Title: {latest.title or 'N/A'}\n"
        f"- Description: {latest.description or 'N/A'}\n"
        f"- Timestamp: {latest.timestamp or 'N/A'}\n"
        f"- User: {latest.sender or 'N/A'}\n"
        f"- Base Branch: {latest.base_branch or 'N/A'}\n"
        f"- Compare Branch: {latest.compare_branch or 'N/A'}"
    )

# ---------------- gtihub Agent------------------------------------------------

github_agent=Agent(
    name="github Agent",
    instructions="You are github agent to response to github events and actions",
    model="gpt-5-nano",
    input_guardrails=[security_guardrail],
    tools=[get_recent_events,summarize_latest_event,get_repository_status]
)





