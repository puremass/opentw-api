from typing import Dict
from . import _get_timestamp
from aiohttp import ClientSession
from models.ttypes import EventType
from contextlib import asynccontextmanager

__all__ = ["session_manager"]

class _SessionManager:
    def __init__(self):
        self.sessions: Dict[int, ClientSession] = {}
    
    async def cleanup(self):
        print("CLEANING UP SESSIONS")
        for session in self.sessions.values():
            if not session.closed:
                await session.close()
        self.sessions.clear()
    
    @asynccontextmanager
    async def get_session(self, tournament_id: int = None, event_type: EventType = EventType.PREDEFINED):
        try:
            if tournament_id is None:
                async with ClientSession() as session:
                    yield session
            else:
                if tournament_id not in self.sessions:
                    self.sessions[tournament_id] = ClientSession()
                    await self.sessions[tournament_id].get(
                        f"https://www.trackwrestling.com/{event_type.tournament_type}/VerifyPassword.jsp",
                        params={
                            "TIM": _get_timestamp(),
                            "twSessionId": "zyxwvutsrq",
                            "tournamentId": tournament_id,
                            "userType": "viewer",
                            "userName": "",
                            "password": "",
                        }
                    )
                yield self.sessions[tournament_id]
        except Exception as e:
            if tournament_id in self.sessions:
                await self.sessions[tournament_id].close()
                del self.sessions[tournament_id]
            raise e

session_manager = _SessionManager()