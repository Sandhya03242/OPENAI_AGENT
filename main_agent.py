from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse, PlainTextResponse
from github import github_agent,merge_pull_request, close_pull_request, get_pull_request_details
from slack import slack_agent,send_slack_notification
import uvicorn
from multiprocessing import Process
from datetime import datetime
import pytz
import json
from agents import Agent, Runner, function_tool, run_demo_loop


import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

main_agent=Agent(
     name="Main Agent",
     instructions="You are an assistant that helps with github and slack workflows. use Github tools for repo queries and slack tools for team notification.",
     handoffs=[github_agent,slack_agent],
     model="gpt-5-nano"
)

def convert_utc_to_ist(utc_str:str)->str:
    try:
        utc_time=datetime.strptime(utc_str,"%Y-%m-%dT%H:%M:%SZ")
        utc_time=utc_time.replace(tzinfo=pytz.UTC)
        ist_time=utc_time.astimezone(pytz.timezone('Asia/Kolkata'))
        return ist_time.strftime("%Y-%m-%d %H:%M:%S IST")
    except Exception:
        return utc_str


# ----------------------------------------------------------------------------------------------------------------------------------
app=FastAPI()
handled_prs=set()

@app.post("/notify")
async def notify(request: Request):
    payload = await request.json()
    event_type = payload.get('event_type', 'unknown')
    sender = payload.get('sender', 'unknown')
    title = payload.get("title", '')
    description = payload.get("description", "")
    timestamp = payload.get("timestamp")
    compare_branch = payload.get("compare_branch", "unknown")
    base_branch = "main"
    repo_info = payload.get("repository")
    pr_number = payload.get("pr_number")

    # Handle pull request events
    action = payload.get("action") if event_type == "pull_request" else None
    if event_type == "pull_request":
        if action == 'synchronize':
            return {"status": "ignored synchronize event"}
        if action not in ['opened', "reopened", "closed"]:
            return {"status": f"Ignored PR action {action}"}
        if action == "closed":
            return {"status": "ignored closed event to avoid duplicate notification"}

    # Extract repo full name
    if isinstance(repo_info, dict):
        repo = repo_info.get("full_name", "unknown")
    else:
        repo = str(repo_info) if repo_info else "unknown"

    # Ensure PR number
    if not pr_number and event_type == "pull_request":
        pr = payload.get("pull_request", {})
        pr_number = pr.get("number")

    # Convert timestamp
    if timestamp:
        try:
            dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
            timestamp = dt.astimezone(pytz.timezone('Asia/Kolkata')).strftime("%Y-%m-%d %H:%M:%S IST")
        except Exception:
            pass
    else:
        timestamp = datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S IST")

    # Compose Slack message
    message = f"🔔 New GitHub event: {event_type} on repository: {repo}"
    message += f"\n- Title: {title}\n- Description: {description}\n- Timestamp: {timestamp}\n- User: {sender}\n- Base Branch: {base_branch}\n- Compare Branch: {compare_branch}"
    print(message)

    # Send message to Slack
    try:
        slack_response = send_slack_notification(
            message=message,
            event_type=event_type,
            repo=repo,
            pr_number=pr_number
        )
        print("Slack response:", slack_response)
    except Exception as e:
        print(f"❌ Failed to send Slack notification: {e}")
        return {"status": "error", "error": str(e)}

    return {"status": "notified and sent to slack"}

# -------------------------------------------------------------------------------------------------------------------------------

@app.post("/slack/interact")
async def handler_slack_actions(request: Request):
    form_data = await request.form()
    payload = form_data.get("payload")
    if not payload:
        return PlainTextResponse("No payload received", status_code=400)

    try:
        data = json.loads(payload)
        action_id = data['actions'][0]['action_id']
        action_value = data['actions'][0]['value']
        try:
            metadata=json.loads(action_value)
        except json.JSONDecodeError:
            metadata={}
        repo = metadata.get("repo", "unknown")
        pr_number = metadata.get("pr_number", "unknown")
        user = data.get("user", {}).get("username", "unknown")
        
        if action_id=="merge_action":
            try:
                    pr_number = int(pr_number)
            except (ValueError, TypeError):
                    return JSONResponse({"error": "Invalid or missing PR number"}, status_code=400)
            result_text=merge_pull_request(repo=repo,pr_number=pr_number)
            send_slack_notification(message=result_text,repo=repo,pr_number=pr_number)
            # return JSONResponse({"text":f"{result_text}"})

        elif action_id=='cancel_action':
            try:
                    pr_number = int(pr_number)
            except (ValueError, TypeError):
                    return JSONResponse({"error": "Invalid or missing PR number"}, status_code=400)
            pr_details=get_pull_request_details(repo=repo,pr_number=pr_number)
            if isinstance(pr_details,dict) and pr_details.get("merged"):
                 return JSONResponse({"text":f"PR #{pr_number} in {repo} is already merged. Cancel Skipped."})
            
            result_text=close_pull_request(repo=repo,pr_number=pr_number)
            send_slack_notification(message=result_text,repo=repo,pr_number=pr_number)

            return JSONResponse({"text":f"{result_text}"})
    except Exception as e:
        print("❌ Error in /slack/interact:", e)
        return JSONResponse({"error": str(e)}, status_code=500)



# ---------------------------------------------------------------------------------------------------------------------------------
def run_server():
        uvicorn.run(app,host="0.0.0.0",port=8001,log_level='critical')
import asyncio
if __name__=="__main__":
    server_process=Process(target=run_server)
    server_process.start()

    asyncio.run(run_demo_loop(main_agent))

    server_process.terminate()