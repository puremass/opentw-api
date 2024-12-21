import re
from typing import List
from bs4 import BeautifulSoup
from utils import _get_timestamp
from datetime import datetime, date
from models.ttypes import Tournament, Wrestler, Match, Team, EventType, Status, BracketData, Weight, Division
from utils.session_manager import session_manager


def _parse_date_range(date_str: str) -> tuple[date, date | None]:
    parts = date_str.split(" - ")
    start_str = parts[0].strip()

    if len(parts) == 1:
        end_date = None
    else:
        end_str = parts[1].strip()
        if "/" in start_str and len(start_str.split("/")) == 2:
            year = end_str.split("/")[-1]
            start_str = f"{start_str}/{year}"
        end_date = datetime.strptime(end_str, "%m/%d/%Y").date()

    start_date = datetime.strptime(start_str, "%m/%d/%Y").date()
    return start_date, end_date


def _parse_venue_address(address_text: str) -> tuple[str, str, str, str, str]:
    lines = [line.strip() for line in address_text.split("\n") if line.strip()]

    venue_name = lines[0] if len(lines) > 0 else None
    street = lines[1] if len(lines) > 1 else None

    city = state = zip_code = None
    if len(lines) > 2:
        city_state_zip = lines[2].split(",")
        if len(city_state_zip) == 2:
            city = city_state_zip[0].strip()
            state_zip = city_state_zip[1].strip().split()
            if len(state_zip) >= 2:
                state = state_zip[0]
                zip_code = state_zip[1]

    return venue_name, street, city, state, zip_code


def _parse_tournaments(html_content: str) -> List[Tournament]:
    soup = BeautifulSoup(html_content, "html.parser")
    tournaments = []

    tournament_items = soup.select(".tournament-ul > li")

    for item in tournament_items:
        try:
            anchor = item.select_one('a[href*="eventSelected"]')
            onclick = anchor.get("href", "")
            event_info = re.search(r"eventSelected\((.*?)\)", onclick)
            if not event_info:
                continue

            params = event_info.group(1).split(",")
            tournament_id = int(params[0])
            name = params[1].strip("'")
            event_type = EventType.from_id(int(params[2]))
            logo_url = params[3].strip(" '")

            date_span = item.select_one("div:nth-child(2) span:nth-child(2)")
            if not date_span:
                continue
            start_date, end_date = _parse_date_range(date_span.text.strip())

            venue_div = item.select_one("div:nth-child(3) span")
            venue_name = _ = city = state = zip_code = None
            if venue_div:
                venue_name, _, city, state, zip_code = _parse_venue_address(
                    venue_div.text
                )

            links_div = item.select_one("div:nth-child(4)")
            event_flyer_url = website_url = None
            if links_div:
                flyer_link = links_div.select_one('a[href*="uploads"]')
                website_link = links_div.select_one('a[href*="Website"]')
                if flyer_link:
                    event_flyer_url = flyer_link["href"]
                if website_link:
                    website_url = website_link["href"]

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
                logo_url=logo_url if logo_url != "null" else None,
                event_flyer_url=event_flyer_url,
                website_url=website_url,
            )
            tournaments.append(tournament)

        except Exception:
            continue

    return tournaments


def _parse_wrestler_data(wrestler_element) -> Wrestler:
    wrestler_id = wrestler_element.get("data-wrestler-id", "")
    team_id = wrestler_element.get("data-team-id", "")
    spans = wrestler_element.find_all("span")

    first_name_span = next(
        (
            span
            for span in spans
            if span.get("data-short-title") and len(span.get("data-short-title")) == 2
        ),
        None,
    )
    last_name_span = next(
        (
            span
            for span in spans
            if span.get("data-short-title") and len(span.get("data-short-title")) > 2
        ),
        None,
    )

    team_span = next(
        (
            span
            for span in spans
            if "(" in span.text or (span.parent and "(" in span.parent.text)
        ),
        None,
    )

    full_text = wrestler_element.text
    record = None
    year = None

    record_match = re.search(r"(\d+-\d+)", full_text)
    if record_match:
        record = record_match.group(1)

    year_match = re.search(r"(Sr|Jr|So|Fr)", full_text)
    if year_match:
        year = year_match.group(1)

    team_match = re.search(r"\((.*?)\)", full_text)
    team_full_name = team_match.group(1).strip() if team_match else ""
    team_short_name = team_span.get("data-short-title", "") if team_span else ""

    return Wrestler(
        id=wrestler_id,
        first_name=first_name_span.text.strip() if first_name_span else "",
        last_name=last_name_span.text.strip() if last_name_span else "",
        record=record,
        year=year,
        team=Team(id=team_id, name=team_full_name, shortName=team_short_name),
    )


def _parse_match_data(match_row) -> Match:
    tds = match_row.find_all("td")
    status_td, mat_td, details_td = tds

    mat_text = mat_td.text
    mat_number = (
        int(re.search(r"Mat (\d+)", mat_text).group(1))
        if re.search(r"Mat (\d+)", mat_text)
        else 0
    )
    bout_number = (
        int(re.findall(r"(\d+)", mat_text)[1])
        if len(re.findall(r"(\d+)", mat_text)) > 1
        else 0
    )

    weight_class_div = details_td.find("div", attrs={"data-short-title": True})
    weight_class = weight_class_div.text.strip() if weight_class_div else ""

    # Find the div containing both weight and round info
    info_div = details_td.find("div", {"style": "display: table; width: 100%;"})
    if info_div:
        # Get the right-aligned div which contains only the round information
        round_div = info_div.find(
            "div", {"style": "display: table-cell; text-align: right;"}
        )
        round_text = round_div.text.strip() if round_div else ""
    else:
        round_text = ""

    wrestler_fonts = details_td.find_all("font")
    wrestler1 = (
        _parse_wrestler_data(wrestler_fonts[0]) if len(wrestler_fonts) > 0 else None
    )
    wrestler2 = (
        _parse_wrestler_data(wrestler_fonts[1]) if len(wrestler_fonts) > 1 else None
    )

    status_color = status_td.get("style", "").lower()
    status: Status = "in_hole"

    if "00ff66" in status_color:
        status = "in_progress"
    elif any(
        color in status_color for color in ["yellow", "ffff00", "rgb(255, 255, 0)"]
    ):
        status = "on_deck"

    return Match(
        mat=mat_number,
        bout=bout_number,
        status=status,
        weight_class=weight_class,
        round=round_text,
        wrestler1=wrestler1,
        wrestler2=wrestler2,
    )


def _parse_tournament_matches(html: str) -> List[Match]:
    soup = BeautifulSoup(html, "html.parser")
    match_rows = [
        tr
        for tr in soup.find_all("tr")
        if len(tr.find_all("td")) == 3 and tr.find("td")
    ]
    return [_parse_match_data(row) for row in match_rows]


async def search_tournaments(query: str = None) -> List[Tournament]:
    """Search for tournaments by query

    Args:
        query (str, optional): Search query. Defaults to None.

    Returns:
        List[Tournament]: A list of Tournament objects representing the search results
    """
    async with session_manager.get_session() as session:
        async with session.get(
            "https://www.trackwrestling.com/Login.jsp",
            params={
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
            },
        ) as response:
            html_content = await response.text()
            return _parse_tournaments(html_content)


async def get_mat_assignment(
    tournament_type: EventType, tournament_id: int
) -> List[Match]:
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
            },
        ) as response:
            html = await response.text()
            return _parse_tournament_matches(html)


async def get_tournament_info(
    tournament_type: EventType, tournament_id: int
) -> Tournament:
    async with session_manager.get_session(tournament_id, tournament_type) as session:
        async with session.get(
            f"https://www.trackwrestling.com/{tournament_type.tournament_type}/TournamentHub.jsp",
            params={
                "TIM": _get_timestamp(),
                "twSessionId": "zyxwvutsrq",
                "tournamentId": str(tournament_id),
            },
        ) as response:
            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")

            # Find the info content section
            content_div = soup.select_one(".hub-nav > ul > li:first-child .content")
            # print(html)
            if not content_div:
                return None

            # Get tournament name
            name_elem = content_div.select_one("h3")
            name = name_elem.text.strip() if name_elem else ""

            # Get logo URL
            logo_img = content_div.select_one(".logo-icon img")
            logo_url = logo_img["src"] if logo_img else None

            # Parse date information
            date_p = content_div.select("p")[0]
            date_text = date_p.text.strip()
            dates = date_text.split(" - ") if " - " in date_text else [date_text]

            start_date = parse_date(dates[0])
            end_date = parse_date(dates[1]) if len(dates) > 1 else None

            # Parse venue information
            address_p = (
                content_div.select("p")[1] if len(content_div.select("p")) > 1 else None
            )
            venue_info = parse_venue_info(address_p.text) if address_p else {}

            # Look for URLs in the nav sections
            flyer_link = soup.select_one('a[href*="event_flyer"]')
            event_flyer_url = flyer_link["href"] if flyer_link else None

            website_link = soup.select_one('a[href*="website"]')
            website_url = website_link["href"] if website_link else None

            # Determine event type from the badge/class
            event_type_elem = soup.select_one(
                '[class*="bg-purple-"], [class*="bg-green-"], [class*="bg-blue-"], [class*="bg-orange-"], [class*="bg-pink-"]'
            )
            event_type = (
                EventType.from_id(determine_event_type(event_type_elem))
                if event_type_elem
                else EventType.PREDEFINED
            )  # Default to Predefined

            return Tournament(
                id=tournament_id,
                name=name,
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
                venue_name=venue_info.get("name"),
                venue_city=venue_info.get("city"),
                venue_state=venue_info.get("state"),
                venue_zip=venue_info.get("zip"),
                logo_url=logo_url,
                event_flyer_url=event_flyer_url,
                website_url=website_url,
            )


def parse_date(date_str: str) -> datetime:
    """Parse date string into datetime object"""
    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y")
    except ValueError:
        return None


def parse_venue_info(address_text: str) -> dict:
    """Parse venue information from address text block"""
    lines = [line.strip() for line in address_text.split("\n") if line.strip()]
    venue_info = {
        "name": lines[0] if lines else None,
        "city": None,
        "state": None,
        "zip": None,
    }

    if len(lines) > 1:
        # Last line typically contains City, State ZIP
        location_parts = lines[-1].split(",")
        if len(location_parts) == 2:
            venue_info["city"] = location_parts[0].strip()
            # Split state and ZIP
            state_zip = location_parts[1].strip().split()
            if len(state_zip) == 2:
                venue_info["state"] = state_zip[0]
                venue_info["zip"] = state_zip[1]

    return venue_info

def _parse_bracket_data(html_content: str) -> BracketData:
    """Parse bracket data from HTML content"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find the relevant script containing tournament data
    scripts = soup.find_all('script')
    division_data = None
    weight_data = None
    
    for script in scripts:
        if not script.string:
            continue
            
        # Look for the script containing the tournament data initialization
        if "str = " in script.string:
            # Extract division template data
            template_match = re.search(r'str = "([^"]*)"', script.string)
            if template_match:
                print(template_match.group(1))
                division_data = template_match.group(1)
            
            # Extract weight data - it appears right after the division data
            weight_match = re.search(r'str = "([^"]*)";[\s\n]*ndx = 0;', script.string)
            if weight_match:
                print(weight_match.group(1))
                weight_data = weight_match.group(1)
                break

    if not division_data or not weight_data:
        return BracketData(divisions=[], weights=[])
    
    print("OKWE have both")

    # Parse divisions
    division_map = {}
    div_template_data = division_data.split("~")
    
    # Process division templates in groups of 7 items
    for i in range(0, len(div_template_data), 7):
        if i + 6 >= len(div_template_data):
            break
            
        bracket_id = int(div_template_data[i])
        division_name = div_template_data[i + 2]
        template_id = int(div_template_data[i + 1])
        
        if bracket_id not in division_map:
            division_map[bracket_id] = Division(division_id=bracket_id, division_name=division_name, weights=[])

    # Parse weights
    weights = []
    weight_items = weight_data.split("~")
    
    # Process weights in groups of 3 items
    for i in range(0, len(weight_items), 3):
        if i + 2 >= len(weight_items):
            break
            
        try:
            weight_id = int(weight_items[i])
            weight_class = weight_items[i + 1]
            division_id = int(weight_items[i + 2])
            participants = int(weight_items[i + 2])
            
            weight = Weight(
                id=weight_id,
                division_id=division_id,
                bracket_id=division_id,  # Using division_id as bracket_id
                weight_class=weight_class,
                participants=participants  # This value isn't in the source data
            )
            
            weights.append(weight)
            if division_id in division_map:
                division_map[division_id].weights.append(weight)
                
        except (IndexError, ValueError) as e:
            print(f"Error parsing weight data: {e}")
            continue

    return BracketData(
        divisions=list(division_map.values()),
        weights=weights
    )

async def get_brackets(tournament_type: EventType, tournament_id: int) -> List[BracketData]:
    async with session_manager.get_session(tournament_id, tournament_type) as session:
        async with session.get(
            f"https://www.trackwrestling.com/{tournament_type.tournament_type}/BracketViewer.jsp",
            params={
                "TIM": _get_timestamp(),
                "twSessionId": "zyxwvutsrq",
                "tournamentId": tournament_id,
            },
        ) as response:
            html = await response.text()
            open("yeah.html", "w").write(html)
            return _parse_bracket_data(html)    

async def get_bracket_data_html(tournament_type: EventType, tournament_id: int, group_id: int) -> str:
    # https://www.trackwrestling.com/predefinedtournaments/AjaxFunctions.jsp?TIM=1734309820692&twSessionId=nrjemjcrpc&function=getBracket&groupId=1227847138&width=670&height=870&font=8&includePages=4&templateId=0
    async with session_manager.get_session(tournament_id, tournament_type) as session:
        async with session.get(
            f"https://www.trackwrestling.com/{tournament_type.tournament_type}/AjaxFunctions.jsp",
            params={
                "TIM": 1734309820692,
                "twSessionId": "zyxwvutsrq",
                "function": "getBracket",
                "groupId": group_id,
                "width": 670,
                "height": 870,
                "font": 8,
                # 4 = bottom, 5 = top
                "includePages": 3,
                "templateId": 0,
            },
        ) as response:
            print("got url " + response.url.__str__())
            return await response.text()
    # https://www.trackwrestling.com/predefinedtournaments/Bracket.jsp?TIM=1734310516096&twSessionId=nrjemjcrpc&groupId=1227847138&bracketWidth=670&bracketHeight=870&bracketFontSize=8&includePages=4&templateId=
    # async with session_manager.get_session(tournament_id, tournament_type) as session:
    #     async with session.get(
    #         f"https://www.trackwrestling.com/{tournament_type.tournament_type}/Bracket.jsp",
    #         params={
    #             "TIM": 1734310516096,
    #             "twSessionId": "zyxwvutsrq",
    #             "groupId": group_id,
    #             # "groupId": tournament_id,
    #             "bracketWidth": 670,
    #             "bracketHeight": 870,
    #             "bracketFontSize": 8,
    #             "includePages": 4,
    #             "templateId": 0,
    #         },
    #     ) as response:
    #         return await response.text()


def determine_event_type(element) -> int:
    """Determine event type based on CSS classes"""
    if "bg-purple" in str(element):
        return 1  # Predefined
    if "bg-green" in str(element):
        return 2  # Open
    if "bg-blue" in str(element):
        return 3  # Team
    if "bg-orange" in str(element):
        return 4  # Freestyle
    if "bg-pink" in str(element):
        return 5  # Season
    return 1  # Default to Predefined


async def cleanup():
    await session_manager.cleanup()
