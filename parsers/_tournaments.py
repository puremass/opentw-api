import re
from typing import List, Dict
from bs4 import BeautifulSoup
from aiohttp import ClientSession
from datetime import datetime, date
from contextlib import asynccontextmanager
from models.ttypes import Tournament, Wrestler, Match, Team, EventType

class SessionManager:
    def __init__(self):
        self.sessions: Dict[int, ClientSession] = {}
    
    async def cleanup(self):
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

session_manager = SessionManager()

def _get_timestamp() -> str:
    return str(int(datetime.now().timestamp())) + '000'

def _parse_date_range(date_str: str) -> tuple[date, date | None]:
    parts = date_str.split(' - ')
    start_str = parts[0].strip()
    
    if len(parts) == 1:
        end_date = None
    else:
        end_str = parts[1].strip()
        if '/' in start_str and len(start_str.split('/')) == 2:
            year = end_str.split('/')[-1]
            start_str = f"{start_str}/{year}"
        end_date = datetime.strptime(end_str, '%m/%d/%Y').date()
    
    start_date = datetime.strptime(start_str, '%m/%d/%Y').date()
    return start_date, end_date

def _parse_venue_address(address_text: str) -> tuple[str, str, str, str, str]:
    lines = [line.strip() for line in address_text.split('\n') if line.strip()]
    
    venue_name = lines[0] if len(lines) > 0 else None
    street = lines[1] if len(lines) > 1 else None
    
    city = state = zip_code = None
    if len(lines) > 2:
        city_state_zip = lines[2].split(',')
        if len(city_state_zip) == 2:
            city = city_state_zip[0].strip()
            state_zip = city_state_zip[1].strip().split()
            if len(state_zip) >= 2:
                state = state_zip[0]
                zip_code = state_zip[1]
    
    return venue_name, street, city, state, zip_code

def _parse_tournaments(html_content: str) -> List[Tournament]:
    soup = BeautifulSoup(html_content, 'html.parser')
    tournaments = []
    
    tournament_items = soup.select('.tournament-ul > li')
    
    for item in tournament_items:
        try:
            anchor = item.select_one('a[href*="eventSelected"]')
            onclick = anchor.get('href', '')
            event_info = re.search(r'eventSelected\((.*?)\)', onclick)
            if not event_info:
                continue
                
            params = event_info.group(1).split(',')
            tournament_id = int(params[0])
            name = params[1].strip("'")
            event_type = EventType.from_id(int(params[2]))
            logo_url = params[3].strip(" '")
            
            date_span = item.select_one('div:nth-child(2) span:nth-child(2)')
            if not date_span:
                continue
            start_date, end_date = _parse_date_range(date_span.text.strip())
            
            venue_div = item.select_one('div:nth-child(3) span')
            venue_name = _ = city = state = zip_code = None
            if venue_div:
                venue_name, _, city, state, zip_code = _parse_venue_address(venue_div.text)
            
            links_div = item.select_one('div:nth-child(4)')
            event_flyer_url = website_url = None
            if links_div:
                flyer_link = links_div.select_one('a[href*="uploads"]')
                website_link = links_div.select_one('a[href*="Website"]')
                if flyer_link:
                    event_flyer_url = flyer_link['href']
                if website_link:
                    website_url = website_link['href']
            
            tournament = Tournament(
                id=tournament_id,
                name=name,
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
                venue_name=venue_name,
                # venue_address=street,
                venue_city=city,
                venue_state=state,
                venue_zip=zip_code,
                logo_url=logo_url if logo_url != 'null' else None,
                event_flyer_url=event_flyer_url,
                website_url=website_url
            )
            tournaments.append(tournament)
            
        except Exception:
            continue
            
    return tournaments

def _parse_wrestler_data(wrestler_element) -> Wrestler:
    wrestler_id = wrestler_element.get('data-wrestler-id', '')
    team_id = wrestler_element.get('data-team-id', '')
    spans = wrestler_element.find_all('span')

    first_name_span = next((span for span in spans 
        if span.get('data-short-title') and len(span.get('data-short-title')) == 2), None)
    last_name_span = next((span for span in spans 
        if span.get('data-short-title') and len(span.get('data-short-title')) > 2), None)

    team_span = next((span for span in spans 
        if '(' in span.text or (span.parent and '(' in span.parent.text)), None)

    full_text = wrestler_element.text
    record = None
    year = None

    record_match = re.search(r'(\d+-\d+)', full_text)
    if record_match:
        record = record_match.group(1)

    year_match = re.search(r'(Sr|Jr|So|Fr)', full_text)
    if year_match:
        year = year_match.group(1)

    team_match = re.search(r'\((.*?)\)', full_text)
    team_full_name = team_match.group(1).strip() if team_match else ''
    team_short_name = team_span.get('data-short-title', '') if team_span else ''

    return Wrestler(
        id=wrestler_id,
        firstName=first_name_span.text.strip() if first_name_span else '',
        lastName=last_name_span.text.strip() if last_name_span else '',
        record=record,
        year=year,
        team=Team(
            id=team_id,
            name=team_full_name,
            shortName=team_short_name
        )
    )

def _parse_match_data(match_row) -> Match:
    tds = match_row.find_all('td')
    status_td, mat_td, details_td = tds

    mat_text = mat_td.text
    mat_number = int(re.search(r'Mat (\d+)', mat_text).group(1)) if re.search(r'Mat (\d+)', mat_text) else 0
    bout_number = int(re.findall(r'(\d+)', mat_text)[1]) if len(re.findall(r'(\d+)', mat_text)) > 1 else 0

    weight_class_div = details_td.find('div', attrs={'data-short-title': True})
    weight_class = weight_class_div.text.strip() if weight_class_div else ''
    
    round_div = next((div for div in details_td.find_all('div') 
        if 'Round' in div.text or 'Cons.' in div.text), None)
    round_text = round_div.text.strip() if round_div else ''

    wrestler_fonts = details_td.find_all('font')
    wrestler1 = _parse_wrestler_data(wrestler_fonts[0]) if len(wrestler_fonts) > 0 else None
    wrestler2 = _parse_wrestler_data(wrestler_fonts[1]) if len(wrestler_fonts) > 1 else None

    status_color = status_td.get('style', '').lower()
    status = 'inHole'

    if '006600' in status_color:
        status = 'inProgress'
    elif any(color in status_color for color in ['yellow', 'ffff00', 'rgb(255, 255, 0)']):
        status = 'onDeck'

    return Match(
        mat=mat_number,
        bout=bout_number,
        status=status,
        weightClass=weight_class,
        round=round_text,
        wrestler1=wrestler1,
        wrestler2=wrestler2
    )

def parse_tournament_matches(html: str) -> List[Match]:
    soup = BeautifulSoup(html, 'html.parser')
    match_rows = [tr for tr in soup.find_all('tr') 
                 if len(tr.find_all('td')) == 3 and tr.find('td')]
    return [_parse_match_data(row) for row in match_rows]

async def search_tournaments(query: str = None) -> List[Tournament]:
    async with session_manager.get_session() as session:
        async with session.get("https://www.trackwrestling.com/Login.jsp", params={
            "TIM": _get_timestamp(),
            "twSessionId": "zyxwvutsrq",
            "tName": query or "",
            "state": "",
            "sDate": "",
            "eDate": "",
            "lastName": "",
            "firstName": "",
            "teamName": "",
            "sfvString": "",
            "city": "",
            "gbId": "",
            "camps": "false",
        }) as response:
            html_content = await response.text()
            return _parse_tournaments(html_content)


async def get_mat_assignment(tournament_type: EventType, tournament_id: int) -> List[Match]:
    """Get mat assignments for a tournament

    Args:
        tournament_type (EventType): The type of tournament (provided from the event_type field in Tournament)
        tournament_id (int): The ID of the tournament

    Returns:
        List[Match]: A list of Match objects representing the mat assignments
    """
    async with session_manager.get_session(tournament_id) as session:
        async with session.get(
            f"https://www.trackwrestling.com/{tournament_type.tournament_type}/MB_MatAssignmentDisplay.jsp",
            params={
                "TIM": _get_timestamp(),
                "twSessionId": "zyxwvutsrq",
                "tournamentId": tournament_id,
            }
        ) as response:
            html = await response.text()
            return parse_tournament_matches(html)

async def get_tournament_info(tournament_type: EventType, tournament_id: int) -> Tournament:
    url = f'https://www.trackwrestling.com/{tournament_type.tournament_type}/TournamentHub.jsp'
    params = {
        'TIM': str(int(datetime.now().timestamp() * 1000)),
        'twSessionId': 'zyxwvutsrq',
        'tournamentId': str(tournament_id)
    }

    async with session_manager.get_session(tournament_id, tournament_type) as session:
        async with session.get(url, params=params) as response:
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
                        
            # Find the info content section
            content_div = soup.select_one('.hub-nav > ul > li:first-child .content')
            # open("ok.html", "w").write(html)
            # print(html)
            if not content_div:
                return None

            # Get tournament name
            name_elem = content_div.select_one('h3')
            name = name_elem.text.strip() if name_elem else ''

            # Get logo URL
            logo_img = content_div.select_one('.logo-icon img')
            logo_url = logo_img['src'] if logo_img else None

            # Parse date information
            date_p = content_div.select('p')[0]
            date_text = date_p.text.strip()
            dates = date_text.split(' - ') if ' - ' in date_text else [date_text]
            
            start_date = parse_date(dates[0])
            end_date = parse_date(dates[1]) if len(dates) > 1 else None

            # Parse venue information
            address_p = content_div.select('p')[1] if len(content_div.select('p')) > 1 else None
            venue_info = parse_venue_info(address_p.text) if address_p else {}

            # Look for URLs in the nav sections
            flyer_link = soup.select_one('a[href*="event_flyer"]')
            event_flyer_url = flyer_link['href'] if flyer_link else None

            website_link = soup.select_one('a[href*="website"]')
            website_url = website_link['href'] if website_link else None

            # Determine event type from the badge/class
            event_type_elem = soup.select_one('[class*="bg-purple-"], [class*="bg-green-"], [class*="bg-blue-"], [class*="bg-orange-"], [class*="bg-pink-"]')
            event_type = EventType.from_id(determine_event_type(event_type_elem)) if event_type_elem else EventType.PREDEFINED  # Default to Predefined

            return Tournament(
                id=tournament_id,
                name=name,
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
                venue_name=venue_info.get('name'),
                venue_city=venue_info.get('city'),
                venue_state=venue_info.get('state'),
                venue_zip=venue_info.get('zip'),
                logo_url=logo_url,
                event_flyer_url=event_flyer_url,
                website_url=website_url
            )

def parse_date(date_str: str) -> datetime:
    """Parse date string into datetime object"""
    try:
        return datetime.strptime(date_str.strip(), '%m/%d/%Y')
    except ValueError:
        return None

def parse_venue_info(address_text: str) -> dict:
    """Parse venue information from address text block"""
    lines = [line.strip() for line in address_text.split('\n') if line.strip()]
    venue_info = {
        'name': lines[0] if lines else None,
        'city': None,
        'state': None,
        'zip': None
    }
    
    if len(lines) > 1:
        # Last line typically contains City, State ZIP
        location_parts = lines[-1].split(',')
        if len(location_parts) == 2:
            venue_info['city'] = location_parts[0].strip()
            # Split state and ZIP
            state_zip = location_parts[1].strip().split()
            if len(state_zip) == 2:
                venue_info['state'] = state_zip[0]
                venue_info['zip'] = state_zip[1]
    
    return venue_info

def determine_event_type(element) -> int:
    """Determine event type based on CSS classes"""
    if 'bg-purple' in str(element): return 1  # Predefined
    if 'bg-green' in str(element): return 2   # Open
    if 'bg-blue' in str(element): return 3    # Team
    if 'bg-orange' in str(element): return 4  # Freestyle
    if 'bg-pink' in str(element): return 5    # Season
    return 1  # Default to Predefined

async def cleanup():
    await session_manager.cleanup()