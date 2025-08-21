from agents import (Agent, Runner, GuardrailFunctionOutput, 
                    InputGuardrailTripwireTriggered, RunContextWrapper,
                    TResponseInputItem, input_guardrail, SQLiteSession)
from github import github_agent
from slack import slack_agent
from pydantic import BaseModel
import asyncio
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



# -------------------- Main Agent---------------------------------------

main_agent=Agent(
    name="Main Agent",
    instructions="Main agent that interact with github and slack agent",
    handoffs=[github_agent,slack_agent],
    model="gpt-5-nano",
    input_guardrails=[security_guardrail]

)

# -------------------Create a session instance-----------------------------

session=SQLiteSession("conversation_123")


async def repo_loop(agent:Agent,session:SQLiteSession):
    while True:
        user_input=input("You:")
        if user_input.lower().strip() in {"exit","quite"}:
            print("Exiting Loop")
            break
        try:
            result=await Runner.run(agent,user_input,session=session)
            print("Assistant: ", result.final_output)

        except InputGuardrailTripwireTriggered:
            print("❌ Guardrail tripped unsafe input blocked")

async def main():
    await Runner.run(main_agent,"Get latest Github event and send to slack",session=session, max_turns=50)
    await repo_loop(main_agent,session)

if __name__=="__main__":
    asyncio.run(main())

