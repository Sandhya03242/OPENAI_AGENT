from agents import (Agent, Runner, GuardrailFunctionOutput, 
                    InputGuardrailTripwireTriggered, RunContextWrapper,
                    TResponseInputItem, input_guardrail, SQLiteSession)
from github import github_agent, get_recent_events, summarize_latest_event
from slack import slack_agent
from pydantic import BaseModel
import asyncio
from aiohttp import web, ClientSession
import json
from github import _get_recent_events, _summarize_latest_event
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
    event_type = request.headers.get("X-GitHub-Event", "unknown")

    print(f"📢 Received GitHub event: {event_type}")

    event = {
        "event_type": event_type,
        "payload": data
    }

    import os
    events = []
    if os.path.exists("github_events.json"):
        with open("github_events.json") as f:
            try:
                events = json.load(f)
            except Exception:
                events = []
    events.append(event)
    events = events[-100:] 
    with open("github_events.json", "w") as f:
        json.dump(events, f, indent=2)
    # ---------------------------------------

    asyncio.create_task(handle_event(event_type, data))
    return web.json_response({"status": "ok"})



async def handle_event(event_type, data):
    summary = f"New GitHub event: {event_type}\n{json.dumps(data, indent=2)}"

    try:
        result = await Runner.run(main_agent, summary, session=session)
        print("🤖 Assistant: ", result.final_output)
    except InputGuardrailTripwireTriggered:
        print("❌ Guardrail blocked unsafe event")


    





# -----------------------------------------------------------------------------
async def repo_loop(agent:Agent,session:SQLiteSession):
    while True:
        user_input=input("You:")
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
    await Runner.run(main_agent,"Get latest Github event and send to slack",session=session, max_turns=50)
    await repo_loop(main_agent,session)

if __name__=="__main__":
    asyncio.run(main())

