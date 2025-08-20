from dotenv import load_dotenv
import json
from pathlib import Path
from datetime import datetime
import pytz
import os
import requests
from agents import Agent, function_tool

load_dotenv()


EVENTS_FILE=Path(__file__).parent/"github_events.json"

    
@function_tool
def get_recent_actions_events()->str:
    """Return recent GitHub Actions events from stored webhook payloads"""
    if EVENTS_FILE.exists():
        return json.loads(EVENTS_FILE.read_text())
    return []




@function_tool
def get_repository_detail() -> str:
    """Return basic repository info and summary of recent events"""
    if not EVENTS_FILE.exists():
        return "No repository events available."
    events = json.loads(EVENTS_FILE.read_text())
    if not events:
        return "No events recorded yet."
    
    latest_event = events[-1]
    repo = latest_event.get("repository", {})
    full_name = repo.get("full_name", "Unknown")
    owner = repo.get("owner", {}).get("login", "Unknown")

    counts = {}
    for e in events:
        etype = e.get('event_type', 'unknown')
        counts[etype] = counts.get(etype, 0) + 1

    count_summary = ", ".join(f"{etype}: {count}" for etype, count in counts.items())

    return (
        f"Repository: {full_name} (owner: {owner})\n"
        f"Total events: {len(events)} ({count_summary})\n"
        f"Most recent event: {latest_event.get('event_type')} "
        f"by {latest_event.get('sender')}"
    )

@function_tool
def get_workflow_status(workflow_name:str)->str:
    """Return the latest status of a GitHub Actions workflow by name."""
    if not EVENTS_FILE.exists():
        return "No GitHub Actions events found."
    events=json.loads(EVENTS_FILE.read_text())
    events=[e for e in events if e.get("workflow_job") or e.get("workflow_run")]
    for event in reversed(events):
        job=event.get("workflow_job")
        run=event.get("workflow_run")
        name=""
        status=""
        if job and workflow_name.lower() in job.get("name","").lower():
            name=job['name']
            status=job['conclusion'] or job['status']
        elif run and workflow_name.lower() in run.get("name","").lower():
            name=run['name']
            status=run['conclusion'] or run['status']

        if name:
            return f"workflow '{name}' status: {status}"
    return f"No recent status found for workflow: {workflow_name}"


@function_tool
def summarize_latest_event()->str:
    """Summarize the latest GitHub event (PR,push etc)"""
    if not EVENTS_FILE.exists():
        return "No GitHub events found."
    events=json.loads(EVENTS_FILE.read_text())
    if not events:
        return "No events stored."
    latest=events[-1]
    event_type=latest.get('event_type','unknown')
    repo=latest.get("repository",'unknown')
    sender=latest.get('sender','unknown')
    title=repo.get("title",'')
    description=latest.get("description",'')
    timestamp=latest.get('timestamp')
    if timestamp:
        try:
            dt=datetime.fromisoformat(timestamp)
            if dt.tzinfo is None:
                dt=dt.replace(tzinfo=pytz.UTC)
            dt_ist=dt.astimezone(pytz.timezone("Asia/Kolkata"))
            formatted_time=dt_ist.strftime("%Y-%m-%d %H:%M:%S IST")
        except Exception as e:
            formatted_time=timestamp
    else:
        formatted_time=""


    return (
        f"# Event: {event_type}\nRepository:{repo}\nTitle: {title}\nDescription:{description}\nTimestamp:{formatted_time}\nSource: {sender}"
    )

import requests

@function_tool
def merge_pull_request(repo: str, pr_number: int) -> str:
    """Merge a PR using GitHub API"""
    import logging
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/merge"
    token = os.environ.get("GITHUB_PAT")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }

    response = requests.put(url, headers=headers)
    logging.info(f"Merge Request URL: {url}")
    logging.info(f"Response Code: {response.status_code}")
    logging.info(f"Response Body: {response.text}")

    if response.status_code == 200:
        return f"✅ Successfully merged PR #{pr_number} in {repo}."
    else:
        return f"❌ Failed to merge PR #{pr_number} in {repo}. Reason: {response.json().get('message', 'Unknown error')}"


@function_tool
def close_pull_request(repo: str, pr_number: int) -> str:
    """Close a pull request without merging using GitHub API"""
    import logging
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    token = os.environ.get("GITHUB_PAT")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }
    data={"state": "closed"}
    logging.info(f"Closing PR URL: {url}")
    try:
        response = requests.patch(url, json=data, headers=headers)
        logging.info(f"Response Code: {response.status_code}")
        logging.info(f"Response Body: {response.text}")
        if response.status_code == 200:
            print("closed pull_request")
            return f"✅ Closed pull request #{pr_number} in {repo}"
        else:
            return f"❌ Failed to close PR: {response.status_code} - {response.text}"
    except Exception as e:
        logging.error(f"Exception while closing PR: {e}")
        return f"❌ Exception while closing PR:{str(e)}"
    
@function_tool
def get_pull_request_details(repo:str,pr_number:int)->dict:
    """Get details of a pull request from Github API"""
    url=f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    token=os.environ.get("GITHUB_PAT")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }
    response=requests.get(url,headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        return {"error":f"Failed to get PR detail: {response.status_code}{response.text}"} 



github_agent=Agent(
    name="github agent",
    instructions="Github agent that get event from the repo",
    tools=[get_recent_actions_events,get_workflow_status,get_repository_detail,summarize_latest_event,merge_pull_request,close_pull_request,get_pull_request_details],
    model="gpt-5-nano"
)
