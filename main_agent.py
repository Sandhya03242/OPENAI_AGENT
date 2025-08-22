from agents import (Agent, Runner, GuardrailFunctionOutput, 
                    InputGuardrailTripwireTriggered, RunContextWrapper,
                    TResponseInputItem, input_guardrail, SQLiteSession)
from github import github_agent
from slack import slack_agent
from pydantic import BaseModel
import asyncio
from aiohttp import web
import json
from datetime import datetime
import pytz
import os
from dotenv import load_dotenv
load_dotenv()

# --------------------Guardrail-------------------------------

class SecurityCheckup(BaseModel):
    is_unsafe:bool
    reasoning:str


guardrail_agent=Agent(
    name="Guardrail Checker",
    instructions="You are a guardrail agent.",
    output_type=SecurityCheckup,
    model="gpt-5-nano"
)


@input_guardrail
async def security_guardrail(
    ctx:RunContextWrapper[None],
    agent:Agent,
    input:str|list[TResponseInputItem])->GuardrailFunctionOutput:
    result= await Runner.run(guardrail_agent,input,context=ctx.context)
    return GuardrailFunctionOutput(output_info=result.final_output, tripwire_triggered=result.final_output.is_unsafe)



# -------------------- Main Agent---------------------------------------- 

main_agent=Agent(
    name="Main Agent",
    instructions="You are the orchestrator agent. "
        "Whenever a GitHub event summary is received, "
        "you must automatically send it to Slack (using slack_agent) without asking the user. "
        "Always forward the event summary exactly as received.",
    handoffs=[github_agent,slack_agent],
    model="gpt-5-nano",
    input_guardrails=[security_guardrail]

)


# -------------------Create a session instance-----------------------------

session=SQLiteSession("conversation_123")

# ------------------------- notify----------------------------------------

async def notify(request):
    data = await request.json()
    event_type = data.get("event_type","unknown")
    print(f"Received GitHub event: {event_type}")
    ist_now=datetime.now(pytz.timezone("Asia/Kolkata")).isoformat()
    sender=data.get("sender")
    if isinstance(sender,dict):
        sender_login=sender.get("login")
    else:
        sender_login=str(sender) if sender else None
    event={
        "event_type":event_type,
        "timestamp":ist_now,
        "action":data.get("action"),
        "repository":data.get("repository",{}),
        "pr_number":data.get("pull_request",{}).get("number"),
        "title":data.get("pull_request",{}).get("title"),
        "description":data.get("pull_request",{}).get("body"),
        "sender":sender_login,
        "base_branch":data.get("repository",{}).get("default_branch"),
        "compare_branch":data.get("ref")
    }
    events=[]
    if os.path.exists("github_events.json"):
        with open("github_events.json") as f:
            try:
                events=json.load(f)
            except Exception:
                events=[]
    events.append(event)
    events=events[-100:]
    with open("github_events.json","w") as f:
        json.dump(events,f,indent=2)
    asyncio.create_task(handle_event(event_type,data))
    return web.json_response({"status":"ok"})




async def handle_event(event_type, data):
    summary = (
        f"🔔 New GitHub event: {event_type}({data.get('action')}) on repository: {data.get('repository',{}).get('full_name')}\n"
        f"- Title: {data.get('title')}\n"
        f"- Description: {data.get('description')}\n"
        f"- Timestamp: {data.get('timestamp')}\n"
        f"- User: {data.get('sender')}\n"
        f"- Base Branch: {data.get('base_branch')}\n"
        f"- Compare Branch: {data.get('compare_branch')}"
    )
    print(summary)

    try:
        result = await Runner.run(slack_agent, summary, session=session)
        print("🤖 Assistant: ", result.final_output)
    except InputGuardrailTripwireTriggered:
        print("❌ Guardrail blocked unsafe event")



# -----------------------------------------------------------------------------

async def ainput(prompt:str="")->str:
    return await asyncio.to_thread(input, prompt)
async def repo_loop(agent:Agent,session:SQLiteSession):
    while True:
        user_input=await ainput("You:")
        if user_input.lower().strip() in {"exit","quit"}:
            print("👋 Exiting Loop")
            break
        try:
            result=await Runner.run(agent,user_input,session=session)
            print("🤖 Assistant: ", result.final_output)

        except InputGuardrailTripwireTriggered:
            print("❌ Guardrail tripped unsafe input blocked")

async def start_web_server():
    app=web.Application()
    app.router.add_post("/notify",notify)
    runner=web.AppRunner(app)
    await runner.setup()
    site=web.TCPSite(runner,"localhost",8001)
    await site.start()
    print("✅ Main Agent listening on http://localhost:8001/notify")

async def main():
    await start_web_server()
    # await Runner.run(main_agent,"Get latest Github event and send to slack",session=session,max_turns=50)
    await asyncio.gather(repo_loop(main_agent,session))

if __name__=="__main__":
    asyncio.run(main())

