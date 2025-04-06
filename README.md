# OpenTW API

OpenTW API is a service that parses data from TrackWrestling's website and returns it in a simplified, structured format. This API makes it easier for developers to access and utilize wrestling tournament data.

## Overview

The OpenTW API serves as a middleware between applications and TrackWrestling's website, providing a cleaner interface to access tournament information, match details, brackets, and more. It handles the scraping and parsing of data, allowing developers to focus on building features rather than dealing with data extraction.

## Features

- Search for tournaments
- Get detailed tournament information
- Retrieve live match assignments and status
- Access bracket information
- Monitor match status changes
- RESTful API with JSON responses

## API Endpoints

### Search Tournaments
```
GET /tournaments?query={search_term}
```
Returns a list of tournaments matching the search term.

### Tournament Information
```
GET /tournaments/{tournament_type}/{tournament_id}
```
Returns detailed information about a specific tournament.

### Match Assignments
```
GET /tournaments/{tournament_type}/{tournament_id}/matches
```
Returns current match assignments and statuses for a tournament.

### Brackets
```
GET /tournaments/{tournament_type}/{tournament_id}/brackets
```
Returns bracket information for all weight classes in a tournament.

### Specific Bracket
```
GET /tournaments/{tournament_type}/{tournament_id}/brackets/{weight_class_id}
```
Returns detailed bracket information for a specific weight class.

## Installation

### Prerequisites
- Python 3.8+
- pip
- asyncio support

### Setup
1. Clone the repository:
   ```
   git clone https://github.com/vehbiu/opentw-api.git
   cd opentw-api
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Run the server:
   ```
   python app.py
   ```

The server will start on `localhost:8000` by default.

## Development

The API is built using:
- Sanic - Async Python web server
- aiohttp - Async HTTP client for fetching data
- Custom parsers for extracting data from TrackWrestling HTML

### Project Structure
- `app.py` - Main application entry point
- `models/` - Data models and types
- `parsers/` - HTML parsing logic for different TrackWrestling views

## Live Demo

A live version of the API is available at: https://opentw-api.vehbi.me

## Related Projects

- [OpenTW](https://github.com/vehbiu/opentw) - Frontend interface for this API

## License

[MIT License](LICENSE)

## Contact

For issues and contributions, please visit the [GitHub repository](https://github.com/vehbiu/opentw-api).