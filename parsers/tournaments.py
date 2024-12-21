import re
from bs4 import BeautifulSoup
from typing import List, Tuple
from utils import _get_timestamp
from datetime import datetime, date
from models.ttypes import Tournament, Wrestler, Match, Team, EventType, Status, Template, Weight, BracketType, BracketPage, BracketData
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
    return _parse_tournament_matches(open("htmls/mat-schedule.html", "r").read())
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
                else tournament_type
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

async def get_brackets(tournament_type: EventType, tournament_id: int) -> BracketData:
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
            print("Got url " + response.url.__str__())
            return parse_bracket_data(html)    

def parse_bracket_data(html_content: str) -> BracketData:
    """
    Parse bracket data from the HTML content into structured dataclasses.
    
    Args:
        html_content: Raw HTML string containing bracket data
        
    Returns:
        Tuple of (weights, templates, bracket_types) lists
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find the script containing the data
    script_content = None
    for script in soup.find_all('script'):
        if script.string and 'new Pile()' in script.string:
            script_content = script.string
            break
            
    if not script_content:
        raise ValueError("Could not find bracket data in HTML")
        
    if "var weights = new Pile();" in script_content:
        print("Using groupId")
    
    def debug_print(data_str: str, label: str):
        """Helper function to print data for debugging"""
        print(f"\n=== {label} ===")
        print(data_str)
        print("=" * 50)
        
    # Parse templates string (it comes first in the script)
    templates_str = script_content.split('str = "')[1].split('";')[0]
    debug_print(templates_str, "Templates String")
    templates = []
    if templates_str:
        entries = templates_str.split('~')
        for i in range(0, len(entries), 7):
            # Parse pages for this template
            pages_data = entries[i+6].split(',')
            pages = []
            for j in range(0, len(pages_data), 2):
                pages.append(BracketPage(
                    page_index=j//2,
                    page_id=int(pages_data[j]),
                    page_name=pages_data[j+1],
                    show_page=(pages_data[j] in ('1', '2', '4', '6'))
                ))
                
            templates.append(Template(
                template_index=len(templates),
                bracket_id=int(entries[i+0]),
                template_id=int(entries[i+1]),
                template_name=entries[i+2],
                bracket_width=entries[i+3],
                bracket_height=entries[i+4],
                bracket_font=entries[i+5],
                pages=pages
            ))

    # Parse weights string 
    weights_str = script_content.split('str = "')[2].split('";')[0]
    debug_print(weights_str, "Weights String")
    weights = []
    if weights_str:
        entries = weights_str.split('~')
        for i in range(0, len(entries), 3):
            weights.append(Weight(
                weight_index=len(weights),
                weight_id=int(entries[i]),
                weight_name=entries[i+1],
                bracket_id=int(entries[i+2])
            ))

    # Parse bracket types string  
    bracket_types_str = script_content.split('str = "')[3].split('";')[0]
    debug_print(bracket_types_str, "Bracket Types String")
    bracket_types = []
    if bracket_types_str:
        for bracket_id in bracket_types_str.split(','):
            bracket_types.append(BracketType(bracket_id=int(bracket_id)))

    # Parse bracket types string  
    bracket_types_str = script_content.split('str = "')[3].split('";')[0]
    bracket_types = []
    if bracket_types_str:
        for bracket_id in bracket_types_str.split(','):
            bracket_types.append(BracketType(bracket_id=int(bracket_id)))

    # return weights, templates, bracket_types
    return BracketData(weights=weights, templates=templates, bracket_types=bracket_types)

def generate_bracket_url(
        tournament_type: EventType,
        weight_id: int) -> str:
    """
    Generate a URL for viewing a specific bracket based on weight and template settings.
    
    Args:
        weight_id: ID of the weight class
        template: Template object containing bracket layout info
        tw_session_id: TrackWrestling session ID
        base_url: Base URL for the TrackWrestling site
        
    Returns:
        Complete URL for viewing the specified bracket
    """
    # Get timestamp in milliseconds
    from time import time
    current_time_ms = int(time() * 1000)
    
    # Get the pages that are marked as visible
    # visible_pages = [p.page_id for p in template.pages if p.show_page]
    # pages_str = ",".join(map(str, visible_pages))
    
    # Construct URL parameters
    params = {
        "TIM": current_time_ms,
        "twSessionId": "zyxwvutsrq",
        "chartId": weight_id,
        "groupId": weight_id,
        "chartWidth": 670,
        "chartHeight": 870,
        "chartFontSize": 8,
        # "includePages": 3,
        # "bracketWidth": template.bracket_width,
        # "bracketHeight": template.bracket_height,
        # "bracketFontSize": template.bracket_font,
        # "includePages": pages_str,
        # "templateId": template.template_id if template.template_id != 0 else ""
    }
    
    # Build query string
    query = "&".join(f"{k}={v}" for k, v in params.items() if v != "")
    
    # Combine into final URL
    # base_url: str = "https://www.trackwrestling.com/teamtournaments/"
    return f"https://www.trackwrestling.com/{tournament_type.tournament_type}/Bracket.jsp?{query}"


async def get_bracket_data_html(tournament_type: EventType, tournament_id: int, group_id: int, pages: Tuple[int] = None) -> str:
    # https://www.trackwrestling.com/predefinedtournaments/AjaxFunctions.jsp?TIM=1734309820692&twSessionId=nrjemjcrpc&function=getBracket&groupId=1227847138&width=670&height=870&font=8&includePages=4&templateId=0
    async with session_manager.get_session(tournament_id, tournament_type) as session:
        async with session.get(
            f"https://www.trackwrestling.com/{tournament_type.tournament_type}/AjaxFunctions.jsp",
            params={
                "TIM": 1734309820692,
                "twSessionId": "zyxwvutsrq",
                "function": "getBracket",
                "groupId": group_id,
                "chartId": group_id,
                "width": 670,
                "height": 870,
                "font": 8,
                "includePages": ",".join((str(p) for p in pages)) if pages else "",
                # 4 = bottom, 5 = top
                # "includePages": "5",
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
