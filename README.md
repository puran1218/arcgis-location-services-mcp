# ArcGIS Location Services MCP Server

MCP Server for [ArcGIS Location Services](https://developers.arcgis.com/rest/location-based-services/).

## Tools

1. `geocode`
   - Search for an address, place, or point of interest
   - Inputs:
     - `singleLine` (string): Complete address in a single string
     - `address` (string): Place name or partial address
     - `location` (string, optional): Nearby point in "longitude,latitude" format
     - `category` (string, optional): POI category to search for
   - Returns: Matching locations with addresses, coordinates, and match scores

2. `reverse_geocode`
   - Convert geographic coordinates to an address
   - Inputs:
     - `location` (string): Location as "longitude,latitude"
     - `outFields` (string, optional): Fields to include in response
   - Returns: Address information, location type, and address components

3. `find_nearby_places`
   - Find nearby places and points of interest
   - Inputs:
     - `x` (number): Longitude of center point
     - `y` (number): Latitude of center point
     - `pageSize` (number, optional): Number of results to return
     - `categories` (string, optional): Category filter
     - `radius` (number, optional): Search radius in meters
     - `includeDetails` (boolean, optional): Whether to include detailed place information
     - `detailsLimit` (number, optional): Maximum number of places to get details for
   - Returns: List of places with names, addresses, categories, and optional details

4. `get_directions`
   - Get detailed turn-by-turn directions between locations
   - Input:
     - `stops` (string): Semicolon-separated list of "longitude,latitude" pairs
   - Returns: Route summary with distance, time, and turn-by-turn directions

5. `get_elevation`
   - Get elevation data for locations on land or water
   - Inputs:
     - `lon` and `lat` (numbers, optional): Coordinates for a single point
     - `coordinates` (string, optional): JSON array of [lon, lat] pairs for multiple points
     - `relativeTo` (string, optional): Reference point for elevation measurement
   - Returns: Elevation data with reference datum and spatial reference

6. `get_basemap_tile`
   - Access static basemap tiles service with different styles
   - Inputs:
     - `version` (string, optional): API version
     - `style_base` (string, optional): Base style category
     - `style_name` (string, optional): Map style name
     - `row`, `level`, `column` (numbers, optional): Tile coordinates
   - Returns: Basemap tile information and status

## Setup

### API Key
Get an ArcGIS Developer API key by creating an account at [ArcGIS Location Platform](https://location.arcgis.com/) and [generating an API key](https://developers.arcgis.com/documentation/security-and-authentication/api-key-authentication/tutorials/create-an-api-key/).

### Usage with Claude Desktop

Add the following to your `claude_desktop_config.json` in [Claude for Desktop](https://modelcontextprotocol.io/quickstart/user):

```json
{
  "mcpServers": {
    "arcgis-location-services": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\ABSOLUTE\\PATH\\TO\\ArcGIS-Location-Services-MCP-Server",
        "run",
        "main.py"
      ],
      "env": {
        "ARCGIS_LOCATION_SERVICE_API_KEY": "<YOUR_API_KEY>"
      }
    }
  }
}
```

## License

This MCP server is provided as-is. Usage of ArcGIS Location Services is subject to [Esri's terms of service](https://developers.arcgis.com/rest/places/#terms-of-use).
