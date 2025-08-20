import json
from datetime import datetime
from pathlib import Path
from aiohttp import web, ClientSession
import asyncio
import pytz

EVENTS_FILE=Path(__file__).parent / "github_events.json"

async def notify_manager(event):
    async with ClientSession() as session:
        try:
            async with session.post("http://localhost:8001/notify",json=event, timeout=5) as rep:
                if rep.status !=200:
                    print(f"Notify failed with status {rep.status}")
        except Exception as notify_error:
            print(F"Failed to notify manager agent:{notify_error}")





async def handle_webhook(request):
    try:
        data=await request.json()
        event_type=request.headers.get("X-GitHub-Event","unknown")
        repo = data.get("repository", {})
        repo_full_name = repo.get("full_name")
        pr_number=data.get("pull_request",{}).get("number")
        title=''
        description=''
        sender=data.get("sender",{}).get("login")
        branch_name = None
        base_branch = None
        compare_branch = None
        if event_type == "pull_request":
            pr = data.get("pull_request")
            if pr:
                base_branch = pr.get("base", {}).get("ref")
                print("base_brach: ",base_branch)
                compare_branch = pr.get("head", {}).get("ref")
                print("compare_branch: ",compare_branch)
                branch_name = base_branch
        elif event_type == "push":
            ref = data.get("ref", "")
            if ref:
                branch_name = ref.split("/")[-1]
        elif event_type == "create" or event_type == "delete":
            branch_name = data.get("ref", None)

        if branch_name and branch_name.lower() != "main":
            print(f"Skipping event for non-main branch: {branch_name}")
            return web.json_response({"status": "ignored"})

        if event_type == 'pull_request':
            action=data.get("action")
            pr = data.get("pull_request")
            if pr:
                title = pr.get("title", "")
                description = pr.get("body", "")
                pr_number = pr.get("number")
            else:
                print("pull_request key not found in payload")

            repo = data.get("repository")
            if repo:
                repo_full_name = repo.get("full_name")
                # print("Extracted repo_full_name:", repo_full_name)
            else:
                print("repository key not found in payload")
            if action=="closed":
                message=f"Pull Request #{pr_number} '{title}' was closed by {sender} in repository {repo_full_name}."
                print("Detected PR closed event: ",message)
            elif action=="opened":
                message=f"Pull Request #{pr_number} '{title}' was opened by {sender} in repository {repo_full_name}."
            else:
                message=f"Pull Request #{pr_number} '{title}' received action '{action}' by {sender}."
            


        elif event_type=='issues':
            issue=data.get("issue",{})
            title=issue.get("title",'')
            description=issue.get("body",'')
        elif event_type=='push':
            commits=data.get('commits',[])
            if commits:
                title=f"{len(commits)} commits pushed"
                description="\n".join(commit.get("message",'') for commit in commits)
                print(f"Received push event :{title} on branch {branch_name} by {sender}")
        elif event_type=='release':
            release=data.get("release",{})
            title=release.get("name",release.get("tag_name",""))
            description=release.get("body",'')
        elif event_type=="create":
            ref_type=data.get("ref_type","")
            ref=data.get("ref","")
            title=f"Created {ref_type}: {ref}"
            description=""
        elif event_type=="delete":
            ref_type=data.get("ref_type","")
            ref=data.get("ref","")
            title=f"Deleted {ref_type}: {ref}"
            description=""
        else:
            title=data.get("title","")
            description=data.get("body","")


        ist_now=datetime.now(pytz.timezone("Asia/Kolkata")).isoformat()
        event={
            "timestamp":ist_now,
            "event_type":event_type,
            "action":data.get("action"),
            "repository": data.get("repository", {}),
            "pr_number":pr_number,
            "title":title,
            "description":description,
            "sender":data.get("sender",{}).get("login"),
            "base_branch":base_branch,
            "compare_branch":compare_branch
        }
        events=[]
        if EVENTS_FILE.exists():
            with open(EVENTS_FILE) as f:
                events=json.load(f)
        events.append(event)
        events=events[-100:]
        with open(EVENTS_FILE,"w") as f:
            json.dump(events,f,indent=2)
        
        asyncio.create_task(notify_manager(event))

        return web.json_response({"status":"received"})
    except Exception as e:
        return web.json_response({"error":str(e)},status=400)
    except Exception as e:
        print("Error parsing payload:", e)
        return web.Response(status=500, text="Payload parsing failed")
    
app=web.Application()
app.router.add_post("/webhook/github",handle_webhook)


if __name__ =="__main__":
    print("✅ Starting webhook server on http://localhost:8080")
    web.run_app(app,host='localhost',port=8080)