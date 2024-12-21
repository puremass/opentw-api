import asyncio
from sanic_ext import Extend
from vonage import Vonage, Auth
from vonage_sms import SmsMessage
from sanic import Sanic, Request
from models.response import Response
from models.ttypes import EventType, Match
from datetime import datetime
from typing import Dict, List
from parsers.tournaments import search_tournaments, get_tournament_info, get_mat_assignment, get_brackets, get_bracket_data_html


app = Sanic("trackwrestling-parser")
app.config.CORS_ORIGINS = "*"
Extend(app)

auth = Auth(api_key="1a15c1b8", api_secret="FbD2xK1r8OkWQtQp")
vonage = Vonage(auth=auth)


# Store the last known state of matches for each tournament
match_states: Dict[str, List[Match]] = {}

def detect_match_changes(old_matches: List[Match], new_matches: List[Match]) -> List[str]:
    """
    Compare old and new match states to detect changes.
    Returns a list of change messages.
    """
    changes = []
    
    # Create dictionary of old matches for easy lookup
    old_match_dict = {(m.bout, m.weight_class): m for m in old_matches}
    
    # Check each new match against old state
    for new_match in new_matches:
        key = (new_match.bout, new_match.weight_class)
        old_match = old_match_dict.get(key)
        
        if not old_match:
            # New match added
            changes.append(
                f"[New Match] {new_match.wrestler1.name} vs {new_match.wrestler2.name} on Mat {new_match.mat}"
            )
            # changes.append(
            #     f"New match: {new_match.weight_class} - {new_match.wrestler1.name} vs {new_match.wrestler2.name} "
            #     f"on Mat {new_match.mat}"
            # )
            continue
            
        # Check for status changes
        if old_match.status != new_match.status:
            changes.append(
                f"[Status] {new_match.wrestler1.name} vs {new_match.wrestler2.name} (Mat {new_match.mat}) is now {new_match.status.upper()}"
            )
            # changes.append(
            #     f"Status change for {new_match.weight_class} match {new_match.bout}: "
            #     f"{old_match.status} → {new_match.status} "
            #     f"({new_match.wrestler1.name} vs {new_match.wrestler2.name})"
            # )
            
        # Check for mat changes
        if old_match.mat != new_match.mat:
            changes.append(
                f"Mat change for {new_match.weight_class} match {new_match.bout}: "
                f"Mat {old_match.mat} → Mat {new_match.mat} "
                f"({new_match.wrestler1.name} vs {new_match.wrestler2.name})"
            )

    return changes

async def check_match_updates():
    """Background task to check for match updates every 30 seconds"""
    while False:
        try:
            # Get all active tournaments (you'll need to implement this based on your needs)
            active_tournaments = [
                # Example structure: (tournament_type, tournament_id)
                ("predefined", 1227848138),
                # Add more tournaments as needed
            ]

            for tourney_type, tourney_id in active_tournaments:
                event_type = EventType.from_alias(tourney_type)
                if not event_type:
                    continue

                # Get current matches state
                current_matches = await get_mat_assignment(event_type, tourney_id)

                # Create a unique key for this tournament
                tournament_key = f"{tourney_type}_{tourney_id}"

                # Compare with previous state if exists
                if tournament_key in match_states:
                    changes = detect_match_changes(match_states[tournament_key], current_matches)
                    
                    # Print any detected changes
                    for change in changes:
                        responseData = vonage.sms.send(
                            SmsMessage(
                                from_="19075312879",
                                to="14018680051",
                                text=f"{change}"
                            )
                        )

                        print("Response data: ", responseData.model_dump_json(exclude_unset=True))

                        # if responseData["messages"][0]["status"] == "0":
                        #     print("Message sent successfully.")
                        # else:
                        #     print(f"Message failed with error: {responseData['messages'][0]['error-text']}")
                        print(f"[{datetime.now()}] {change}")
                
                # Update stored state
                match_states[tournament_key] = current_matches

        except Exception as e:
            print(f"Error in background task: {e}")

        await asyncio.sleep(15)

@app.before_server_start
async def setup_background_tasks(app, loop):
    """Start the background task when the server starts"""
    app.add_task(check_match_updates())

@app.get("/")
async def index(_: Request) -> Response:
    return Response(ok=True)

@app.get("/tournaments")
async def tournaments(request: Request) -> Response:
    parsed = await search_tournaments(request.args.get("query"))
    return Response(ok=True, data=[t.as_dict() for t in parsed])

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>")
async def tournament(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type: EventType = EventType.from_alias(tournament_type)
    if not tourney_type:
        return Response(ok=False, error="Invalid tournament type")
    parsed = await get_tournament_info(tourney_type, tournament_id)
    return Response(ok=True, data=parsed.as_dict())

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/matches")
async def matches(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type: EventType = EventType.from_alias(tournament_type)
    if not tourney_type:
        return Response(ok=False, error="Invalid tournament type")
    parsed = await get_mat_assignment(tourney_type, tournament_id)
    return Response(ok=True, data=[m.as_dict() for m in parsed])

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/brackets")
async def brackets(request: Request, tournament_type: str, tournament_id: int) -> Response:
    tourney_type: EventType = EventType.from_alias(tournament_type)
    if not tourney_type:
        return Response(ok=False, error="Invalid tournament type")
    parsed = await get_brackets(tourney_type, tournament_id)
    return Response(ok=True, data=parsed.as_dict())

@app.get("/tournaments/<tournament_type:str>/<tournament_id:int>/brackets/<weight_class_id:int>")
async def bracket(request: Request, tournament_type: str, tournament_id: int, weight_class_id: str) -> Response:
    tourney_type: EventType = EventType.from_alias(tournament_type)
    if not tourney_type:
        return Response(ok=False, error="Invalid tournament type")
    _pages: str | None = request.args.get("pages", None)
    pages = (int(i) for i in _pages.split(",")) if _pages else None
    parsed = await get_bracket_data_html(tourney_type, tournament_id, weight_class_id, pages)
    return Response(ok=True, data=parsed)

if __name__ == "__main__":
    app.run(host="localhost", port=8000, debug=True, dev=True)