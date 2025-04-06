import asyncio
from sanic_ext import Extend
from datetime import datetime
from typing import Dict, List
from sanic import Sanic, Request
from aiohttp import ClientSession
from models.response import Response
from models.ttypes import EventType, Match
from parsers.tournaments import search_tournaments, get_tournament_info, get_mat_assignment, get_brackets, get_bracket_data_html


app = Sanic("trackwrestling-parser")
app.config.CORS_ORIGINS = "*"
Extend(app)


match_states: Dict[str, List[Match]] = {}


@app.before_server_start
async def setup_background_tasks(app, loop):
    """Start the background task when the server starts"""
    # app.add_task(check_match_updates())

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