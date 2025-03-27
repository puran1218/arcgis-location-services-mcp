from typing import Any, Dict
import httpx
import json
import os
from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server
mcp = FastMCP("arcgis-location-services")

# API key from environment variable with fallback to empty string
API_KEY = os.environ.get("ARCGIS_LOCATION_SERVICE_API_KEY", "")

# ArcGIS Location Services base URLs
BASEMAP_URL = "https://static-map-tiles-api.arcgis.com/arcgis/rest/services/static-basemap-tiles-service"
PLACES_URL = (
    "https://places-api.arcgis.com/arcgis/rest/services/places-service/v1/places"
)
GEOCODE_URL = "https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer"
ROUTING_URL = (
    "https://route-api.arcgis.com/arcgis/rest/services/World/Route/NAServer/Route_World"
)
GEOENRICHMENT_URL = "https://geoenrich.arcgis.com/arcgis/rest/services/World/geoenrichmentserver/Geoenrichment"
ELEVATION_URL = "https://elevation-api.arcgis.com/arcgis/rest/services/elevation-service/v1/elevation"

# Common headers and settings
USER_AGENT = "arcgis-location-services-mcp/1.0"

# =============================================================================
# ERROR HANDLING AND UTILITIES
# =============================================================================


class ArcGISError(Exception):
    """Exception raised for ArcGIS API errors."""

    def __init__(self, message: str, status_code: int = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


def format_error(error: Exception) -> str:
    """Format error messages for API responses."""
    if isinstance(error, ArcGISError):
        if error.status_code:
            return f"Error ({error.status_code}): {error.message}"
        return f"Error: {error.message}"
    return f"Error: {str(error)}"


def reference_to_readable(reference: str) -> str:
    """Convert reference datum to readable format."""
    if reference.lower() == "meansealevel":
        return "above sea level"
    elif reference.lower() == "ellipsoid":
        return "above WGS84 ellipsoid"
    else:
        return f"({reference})"


def log_http_request(
    url: str,
    params: Dict[str, Any],
    method: str,
    headers: Dict[str, str],
    body: Dict = None,
):
    """Log HTTP request in a human-readable format with redacted token.

    Args:
        url: The API endpoint URL
        params: Query parameters for the request
        method: HTTP method (GET, POST)
        headers: HTTP headers
        body: Request body for POST requests
    """
    try:
        # Parse the URL to extract the hostname and path
        from urllib.parse import urlparse, urlencode

        parsed_url = urlparse(url)
        hostname = parsed_url.netloc
        path = parsed_url.path

        # Create a copy of params to avoid modifying the original
        safe_params = params.copy() if params else {}

        # Redact the token in query parameters
        if "token" in safe_params:
            safe_params["token"] = "......"

        # Build the query string
        query_string = urlencode(safe_params)

        # Format the request line
        request_line = f"{method} {path}?{query_string} HTTP/1.1"

        # Build the request log
        log_lines = [
            "\n-------- HTTP Request --------",
            request_line,
            f"Host: {hostname}",
        ]

        # Add headers
        for key, value in headers.items():
            log_lines.append(f"{key}: {value}")

        # Add body for POST requests
        if method.upper() == "POST" and body:
            # Create a redacted copy of the body if needed
            safe_body = body.copy()

            # Redact sensitive information in the body
            if "token" in safe_body:
                safe_body["token"] = "......"

            # Format the body nicely
            body_str = json.dumps(safe_body, indent=2)
            log_lines.append("")  # Empty line before body
            log_lines.append(body_str)

        log_lines.append("-----------------------------\n")

        # Print the formatted request
        print("\n".join(log_lines))

    except (TypeError, ValueError, AttributeError) as e:
        # Handle specific expected exceptions that could occur during formatting
        print(f"Error formatting HTTP request: {str(e)}")
    except Exception as e:
        # Catch other unexpected exceptions but don't catch KeyboardInterrupt, etc.
        print(f"Unexpected error logging HTTP request: {str(e)}")


async def make_arcgis_request(
    url: str,
    params: Dict[str, Any] = None,
    method: str = "GET",
    timeout: float = 30.0,
    token: str = None,
) -> Dict[str, Any]:
    """Make a request to the ArcGIS API with proper error handling.

    Args:
        url: The API endpoint URL
        params: Query parameters for the request
        method: HTTP method (GET, POST)
        timeout: Request timeout in seconds
        token: Optional specific token to use (overrides default API_KEY)

    Returns:
        JSON response as dictionary

    Raises:
        ArcGISError: When the API returns an error response
    """
    if params is None:
        params = {}

    # Common parameters for ArcGIS REST API
    if token:
        # Use the specific token provided
        params["token"] = token
    elif API_KEY and "token" not in params:
        # Fall back to default API_KEY
        params["token"] = API_KEY

    # Ensure f=json is added if not present
    if "f" not in params:
        params.update({"f": "json"})

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

    # Log the HTTP request in a human-readable format
    log_http_request(url, params, method, headers)

    async with httpx.AsyncClient() as client:
        try:
            if method.upper() == "GET":
                response = await client.get(
                    url, headers=headers, params=params, timeout=timeout
                )
            elif method.upper() == "POST":
                headers["Content-Type"] = "application/json"
                # For POST requests, only specific parameters go in the URL
                url_params = {"f": params.pop("f", "json")}
                if "token" in params:
                    url_params["token"] = params.pop("token")

                # Log POST request with body
                log_http_request(url, url_params, method, headers, body=params)

                response = await client.post(
                    url,
                    headers=headers,
                    params=url_params,
                    json=params,
                    timeout=timeout,
                )
            else:
                raise ArcGISError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()

            try:
                result = response.json()
            except json.JSONDecodeError:
                raise ArcGISError("Invalid JSON response from ArcGIS API")

            # Check for API-level errors in the response
            if "error" in result:
                error_msg = result["error"].get("message", "Unknown error")
                error_code = result["error"].get("code", 0)
                raise ArcGISError(f"API Error: {error_msg}", error_code)

            return result

        except httpx.HTTPStatusError as e:
            try:
                error_detail = e.response.json()
                error_msg = error_detail.get("error", {}).get("message", str(e))
                error_code = error_detail.get("error", {}).get(
                    "code", e.response.status_code
                )
            except:
                error_msg = str(e)
                error_code = e.response.status_code

            raise ArcGISError(f"HTTP Error: {error_msg}", error_code)

        except httpx.RequestError as e:
            raise ArcGISError(f"Request Error: {str(e)}")

        except json.JSONDecodeError:
            raise ArcGISError("Invalid JSON response from ArcGIS API")


# =============================================================================
# Model Context Protocol (MCP) TOOLS
# =============================================================================


@mcp.tool()
async def get_basemap_tile(
    version: str = "v1",
    style_base: str = "arcgis",
    style_name: str = "navigation",
    row: int = 17,
    level: int = 52333,
    column: int = 22866,
) -> str:
    """Access static basemap tiles service with different styles.

    Args:
        version: API version (default: v1)
        style_base: The base style category (default: arcgis)
        style_name: Map style name (e.g., navigation, streets, satellite)
        row: Tile row coordinate
        level: Zoom level
        column: Tile column coordinate
    """
    url = f"{BASEMAP_URL}/{version}/{style_base}/{style_name}/static/tile/{row}/{level}/{column}"

    try:
        # For tile requests, we might just want to check if the tile exists
        # rather than getting the actual image data
        async with httpx.AsyncClient() as client:
            response = await client.head(
                url,
                headers={"User-Agent": USER_AGENT},
                params={"token": API_KEY} if API_KEY else None,
                timeout=10.0,
            )

            if response.status_code == 200:
                # Return a success message with info about the tile
                result = [
                    "# Basemap Tile Information",
                    f"**Version**: {version}",
                    f"**Style Base**: {style_base}",
                    f"**Style Name**: {style_name}",
                    f"**Coordinates**: Row={row}, Level={level}, Column={column}",
                    "**Status**: Tile available",
                    f"**URL**: {url}",
                ]
                return "\n".join(result)
            else:
                return f"Tile not found or not accessible. Status code: {response.status_code}"

    except Exception as e:
        return format_error(e)


@mcp.tool()
async def find_nearby_places(
    x: float,
    y: float,
    pageSize: int = 10,
    categories: str = "",
    radius: int = 5000,
    includeDetails: bool = False,
    detailsLimit: int = 1,
) -> str:
    """Find nearby places and points of interest with optional detailed information.

    Args:
        x: Longitude of the center point (e.g., -122.4194)
        y: Latitude of the center point (e.g., 37.7749)
        pageSize: Number of results to return (default: 20)
        categories: Optional category filter (e.g., "restaurant", "hotel", "coffee")
        radius: Search radius in meters (default: 5000)
        includeDetails: Whether to include full details for each place (default: False)
        detailsLimit: Maximum number of places to get details for when includeDetails=True (default: 3)
    """
    url = f"{PLACES_URL}/near-point"

    params = {
        "x": x,
        "y": y,
        "pageSize": pageSize,
        "f": "pjson",
    }

    # Add optional parameters
    if categories:
        params["categories"] = categories

    if radius:
        params["radius"] = radius

    try:
        data = await make_arcgis_request(url, params)
        places = data.get("results", [])

        if not places:
            return "No places found matching your criteria."

        # Format the places
        results = [f"# Found {len(places)} nearby places"]

        # Only add this note if we're not including details automatically
        if not includeDetails:
            results.append(
                "*Note: Use find_nearby_places with includeDetails=True to see more information about specific places.*\n"
            )

        detailed_count = 0

        for place in places:
            name = place.get("name", "Unknown Place")

            # Improved address handling
            address = place.get("address", {})
            formatted_address = address.get("formattedAddress", "")
            if not formatted_address and address:
                # Try to construct an address from components if formattedAddress is missing
                addr_parts = []
                for component in [
                    "streetName",
                    "streetNumber",
                    "city",
                    "region",
                    "postalCode",
                ]:
                    if component in address and address[component]:
                        addr_parts.append(str(address[component]))
                if addr_parts:
                    formatted_address = ", ".join(addr_parts)

            if not formatted_address:
                formatted_address = "Address information not available"

            category = place.get("category", {}).get("label", "Uncategorized")

            place_details = [
                f"## {name}",
                f"**Address**: {formatted_address}",
                f"**Category**: {category}",
            ]

            # Add contact info if available
            if "phone" in place and place["phone"]:
                place_details.append(f"**Phone**: {place['phone']}")

            # Add distance if available
            if "distance" in place:
                place_details.append(f"**Distance**: {place['distance']} meters")

            # Get place ID and keep track of it in results
            place_id = place.get("placeId", "")
            if place_id:
                place_details.append(f"**Place ID**: `{place_id}`")

            # Add coordinates if available
            if "location" in place:
                location = place["location"]
                if "x" in location and "y" in location:
                    place_details.append(
                        f"**Coordinates**: {location['y']}, {location['x']}"
                    )

            # If user requested details and we haven't hit the limit
            if includeDetails and place_id and detailed_count < detailsLimit:
                # Get detailed information for this place
                detailed_info = await get_place_details_internal(place_id)
                if detailed_info:
                    # Create a divider between basic and detailed info
                    place_details.append("\n### Detailed Information")
                    place_details.append(detailed_info)
                    detailed_count += 1

            results.append("\n".join(place_details))

        # Add a note about the details limit if applied
        if includeDetails and len(places) > detailsLimit:
            results.append(
                f"\n\n*Note: Detailed information has been limited to {detailsLimit} places. Increase the detailsLimit parameter to see more details.*"
            )

        return "\n\n".join(results)

    except Exception as e:
        return format_error(e)


async def get_place_details_internal(place_id: str) -> str:
    """Internal function to get detailed information about a specific place.
    This isn't exposed as a tool since place_id needs to come from find_nearby_places.

    Args:
        place_id: The unique identifier for a place

    Returns:
        Formatted details as a string, or empty string if error
    """
    if not place_id:
        return ""

    url = f"{PLACES_URL}/{place_id}"
    params = {"f": "pjson"}

    try:
        data = await make_arcgis_request(url, params)

        if not data or "error" in data:
            return ""  # Silently fail in the internal function

        # Format the place details
        result = []

        # Handle address components that weren't in the basic info
        address = data.get("address", {})
        address_components = []
        for component in [
            "streetNumber",
            "streetName",
            "city",
            "region",
            "postalCode",
            "country",
        ]:
            if component in address and address[component]:
                label = component.replace("streetName", "Street").replace(
                    "postalCode", "Postal Code"
                )
                label = label[0].upper() + label[1:]
                address_components.append(f"**{label}**: {address[component]}")

        if address_components:
            result.append("**Address Details**:")
            result.extend(address_components)

        # Contact information
        contact_info = []
        # Only include fields that weren't already in the basic listing
        if "url" in data and data["url"]:
            contact_info.append(f"**Website**: {data['url']}")
        if "email" in data and data["email"]:
            contact_info.append(f"**Email**: {data['email']}")

        if contact_info:
            result.append("\n**Contact Information**:")
            result.extend(contact_info)

        # Opening hours
        hours = data.get("openingHours", {})
        if hours:
            result.append("\n**Opening Hours**:")
            for day, times in hours.items():
                result.append(f"*{day}*: {times}")

        # Additional information
        if "description" in data and data["description"]:
            result.append(f"\n**Description**:\n{data['description']}")

        # Reviews or ratings
        rating = data.get("rating", {})
        if rating:
            result.append(
                f"\n**Rating**: {rating.get('value', 'N/A')}/5 ({rating.get('count', 0)} reviews)"
            )

        return "\n".join(result)

    except Exception:
        return ""  # Silently fail in the internal function - error handling happens in the main tool


# @mcp.tool()
async def get_place_details(place_id: str) -> str:
    """Get detailed information about a specific place using its Place ID.
    You can find place IDs by first using find_nearby_places().

    Args:
        place_id: The unique identifier for a place (obtained from find_nearby_places)
    """
    if not place_id:
        return "Error: place_id is required. First use find_nearby_places() to get a Place ID."

    url = f"{PLACES_URL}/{place_id}"

    params = {"f": "pjson"}

    try:
        data = await make_arcgis_request(url, params)

        if not data or "error" in data:
            error_msg = (
                data.get("error", {}).get("message", "Unknown error")
                if "error" in data
                else "No details found"
            )
            return (
                f"Error retrieving place details: {error_msg} for place ID: {place_id}"
            )

        # Format the place details
        name = data.get("name", "Unknown Place")

        result = [f"# {name}", f"**Place ID**: {place_id}"]

        # Address
        address = data.get("address", {})
        if address:
            formatted_address = address.get("formattedAddress", "No address available")
            result.append(f"**Address**: {formatted_address}")

            # Add address components if available
            address_components = []
            for component in [
                "streetNumber",
                "streetName",
                "city",
                "region",
                "postalCode",
                "country",
            ]:
                if component in address and address[component]:
                    label = component.replace("streetName", "Street").replace(
                        "postalCode", "Postal Code"
                    )
                    label = label[0].upper() + label[1:]
                    address_components.append(f"**{label}**: {address[component]}")

            if address_components:
                result.append("\n## Address Components")
                result.extend(address_components)

        # Category
        category = data.get("category", {})
        if category:
            result.append(f"**Category**: {category.get('label', 'Uncategorized')}")

        # Contact information
        contact_info = []
        if "phone" in data and data["phone"]:
            contact_info.append(f"**Phone**: {data['phone']}")
        if "url" in data and data["url"]:
            contact_info.append(f"**Website**: {data['url']}")
        if "email" in data and data["email"]:
            contact_info.append(f"**Email**: {data['email']}")

        if contact_info:
            result.append("\n## Contact Information")
            result.extend(contact_info)

        # Opening hours
        hours = data.get("openingHours", {})
        if hours:
            result.append("\n## Opening Hours")
            for day, times in hours.items():
                result.append(f"**{day}**: {times}")

        # Location
        location = data.get("location", {})
        if "x" in location and "y" in location:
            result.append(f"\n**Coordinates**: {location['y']}, {location['x']}")

        # Additional information
        if "description" in data and data["description"]:
            result.append(f"\n## Description\n{data['description']}")

        # Reviews or ratings
        rating = data.get("rating", {})
        if rating:
            result.append(
                f"\n**Rating**: {rating.get('value', 'N/A')}/5 ({rating.get('count', 0)} reviews)"
            )

        return "\n".join(result)

    except Exception as e:
        return format_error(e)


@mcp.tool()
async def geocode(
    singleLine: str = "",
    address: str = "",
    location: str = "",
    category: str = "",
    outFields: str = "*",
) -> str:
    """Search for an address, place or point of interest.

    Args:
        singleLine: Complete address in a single string (e.g., "1600 Pennsylvania Ave NW, DC")
        address: Place name or address (e.g., "Starbucks" or "380 New York St")
        location: Optional point to search near, as "longitude,latitude" (e.g., "-122.4194,37.7749")
        category: Optional POI category to search for (e.g., "gas station")
        outFields: Fields to return in the response (default: all fields)
    """
    url = f"{GEOCODE_URL}/findAddressCandidates"

    params = {
        "f": "pjson",
        "outFields": outFields,
        "maxLocations": 5,
        "outSR": 4326,  # WGS84 output spatial reference
    }

    # Add the appropriate search parameters
    if singleLine:
        params["singleLine"] = singleLine
    elif address:
        params["address"] = address
    elif category:
        params["category"] = category

    # Add location parameter if provided
    if location:
        params["location"] = location

    try:
        data = await make_arcgis_request(url, params)
        candidates = data.get("candidates", [])

        if not candidates:
            return "No matches found for the given search."

        # Format the results
        results = ["# Geocoding results"]

        for i, candidate in enumerate(candidates, 1):
            location = candidate.get("location", {})
            attrs = candidate.get("attributes", {})

            match_addr = attrs.get("Match_addr", "Unknown")
            place_name = attrs.get("PlaceName", "")

            candidate_details = [
                f"## Result {i}: {place_name if place_name else match_addr}",
                f"**Address**: {match_addr}",
                f"**Coordinates**: {location.get('y', 'Unknown')}, {location.get('x', 'Unknown')}",
                f"**Match Score**: {candidate.get('score', 'Unknown')}",
            ]

            # Add address components if available
            address_parts = []

            # Map of attribute keys to more readable labels
            component_map = {
                "StAddr": "Street",
                "City": "City",
                "Region": "State/Region",
                "RegionAbbr": "State Abbr.",
                "Postal": "Postal Code",
                "PostalExt": "Postal Extension",
                "Country": "Country",
                "Addr_type": "Address Type",
                "Type": "Location Type",
                "PlaceName": "Place Name",
                "Place_addr": "Place Address",
            }

            # Add all available address components with readable labels
            for key, label in component_map.items():
                if key in attrs and attrs[key]:
                    address_parts.append(f"**{label}**: {attrs[key]}")

            if address_parts:
                candidate_details.append("\n".join(address_parts))

            results.append("\n".join(candidate_details))

        return "\n\n".join(results)

    except Exception as e:
        return format_error(e)


@mcp.tool()
async def reverse_geocode(location: str, outFields: str = "*") -> str:
    """Convert geographic coordinates to an address.

    Args:
        location: Location as "longitude,latitude" (e.g., "-79.3871,43.6426")
        outFields: Fields to include in the response (default: all fields)
    """
    url = f"{GEOCODE_URL}/reverseGeocode"

    # Validate location format
    if not location or "," not in location:
        return "Error: Location must be formatted as 'longitude,latitude'"

    try:
        lon, lat = map(float, location.split(","))
    except ValueError:
        return "Error: Invalid coordinates. Location must contain numeric longitude and latitude values."

    params = {
        "f": "pjson",
        "location": location,
        "outSr": 4326,
        "outFields": outFields,
        "returnIntersection": "false",  # Added parameter
    }

    try:
        data = await make_arcgis_request(url, params)

        if "error" in data:
            return f"Error: {data['error']['message']}"

        if "address" not in data:
            return f"No address found at coordinates {location}."

        address = data["address"]

        # Format the main result
        location_label = location.split(",")
        if len(location_label) >= 2:
            formatted_location = f"{location_label[1]}, {location_label[0]}"
        else:
            formatted_location = location

        result = [
            "# Reverse Geocoding Results",
            f"**Coordinates**: {formatted_location}",
            f"**Full Address**: {address.get('Match_addr', address.get('Address', 'Address not available'))}",
        ]

        # Add location type if available
        if "Addr_type" in address:
            result.append(f"**Location Type**: {address['Addr_type']}")

        # Add match score if available
        if "score" in data:
            result.append(f"**Match Score**: {data['score']}")

        # Format address components
        address_components = []

        # Common address fields to check and display
        field_map = {
            "Address": "Street Address",
            "Street": "Street",
            "City": "City",
            "Neighborhood": "Neighborhood",
            "District": "District",
            "Region": "State/Region",
            "Subregion": "County",
            "Postal": "Postal Code",
            "PostalExt": "Postal Extension",
            "CountryCode": "Country Code",
            "Country": "Country",
            "PlaceName": "Place Name",
            "AddNum": "Street Number",
            "StPreDir": "Street Pre-Direction",
            "StName": "Street Name",
            "StType": "Street Type",
            "StDir": "Street Direction",
        }

        for field, label in field_map.items():
            if field in address and address[field]:
                address_components.append(f"**{label}**: {address[field]}")

        if address_components:
            result.append("\n## Address Components")
            result.extend(address_components)

        # Add any additional metadata
        if "location" in data:
            loc = data["location"]
            if "spatialReference" in loc:
                sr = loc["spatialReference"]
                result.append(
                    f"\n**Spatial Reference**: WKID {sr.get('wkid', 'Unknown')}"
                )

        return "\n".join(result)

    except Exception as e:
        return format_error(e)


@mcp.tool()
async def get_directions(stops: str) -> str:
    """Get detailed turn-by-turn directions between locations.

    Args:
        stops: Two or more locations as a semicolon-separated list of "longitude,latitude" pairs
              (e.g., "-122.68782,45.51238;-122.690176,45.522054")
    """
    url = f"{ROUTING_URL}/solve"

    # Validate that we have at least 2 stops
    stop_points = stops.split(";")
    if len(stop_points) < 2:
        return "Error: At least two stops are required (origin and destination) in format 'lon1,lat1;lon2,lat2'"

    # Construct the request parameters with only required fields
    params = {"f": "json", "stops": stops}

    try:
        data = await make_arcgis_request(url, params)

        if "error" in data:
            return f"Error getting directions: {data['error']['message']}"

        if not data.get("routes") or not data["routes"].get("features"):
            return "No route found between the specified locations."

        # Extract route data
        route = data["routes"]["features"][0]
        attributes = route.get("attributes", {})

        # Get total distance and time
        total_distance = attributes.get(
            "Total_Miles", attributes.get("Total_Kilometers", "Unknown")
        )
        total_time_min = attributes.get("Total_Minutes", "Unknown")

        # Convert minutes to hours and minutes for better readability
        if isinstance(total_time_min, (int, float)):
            hours = int(total_time_min / 60)
            minutes = int(total_time_min % 60)
            total_time = f"{hours} hr {minutes} min" if hours > 0 else f"{minutes} min"
        else:
            total_time = f"{total_time_min}"

        # Format the route summary
        result = [
            "# Route Directions",
            f"**Stops**: {len(stop_points)} locations",
            f"**Total Distance**: {total_distance} miles",
            f"**Estimated Travel Time**: {total_time}",
        ]

        # Add start and end points for clarity
        if len(stop_points) >= 2:
            result.insert(1, f"**From**: {stop_points[0]}")
            result.insert(2, f"**To**: {stop_points[-1]}")

        # If there are intermediate stops, add them
        if len(stop_points) > 2:
            intermediate = "; ".join(stop_points[1:-1])
            result.insert(3, f"**Via**: {intermediate}")

        # Add turn-by-turn directions if available
        if "directions" in data:
            directions_features = data["directions"][0].get("features", [])

            if directions_features:
                result.append("\n## Turn-by-Turn Directions")

                for i, direction in enumerate(directions_features, 1):
                    attrs = direction.get("attributes", {})
                    text = attrs.get("text", "Unknown direction")
                    distance = attrs.get("length", 0)

                    direction_text = f"{i}. {text}"
                    if distance > 0:
                        direction_text += f" ({distance:.1f} miles)"

                    result.append(direction_text)

        return "\n".join(result)

    except Exception as e:
        return format_error(e)


# @mcp.tool()
async def get_geoenrichment(
    x: float = None, y: float = None, studyAreas: str = None
) -> str:
    """Find demographic data and local facts for locations.

    Args:
        x: Longitude of the location (e.g., -117.1956)
        y: Latitude of the location (e.g., 34.0572)
        studyAreas: Optional JSON string defining the areas to analyze. If not provided, x and y will be used.
                    Example: "[{\"geometry\":{\"x\":-117.1956,\"y\":34.0572}}]"
    """
    url = f"{GEOENRICHMENT_URL}/enrich"

    # Build request body based on input
    if x is not None and y is not None:
        # Use coordinates to build study area
        study_areas_json = f'[{{"geometry":{{"x":{x},"y":{y}}}}}]'
    elif studyAreas:
        # Use provided study areas
        study_areas_json = studyAreas
        # Convert single quotes to double quotes if necessary
        if "'" in study_areas_json and '"' not in study_areas_json:
            study_areas_json = study_areas_json.replace("'", '"')
    else:
        return "Error: Either x/y coordinates or studyAreas parameter must be provided"

    # Create request parameters
    params = {
        "f": "pjson",
        "studyAreas": study_areas_json,
        "dataCollections": ["KeyGlobalFacts"],  # Default to KeyGlobalFacts
    }

    try:
        # Make the API request (use url-encoded form data)
        data = await make_arcgis_request(url, params, method="POST")

        if "error" in data:
            error_msg = data.get("error", {}).get("message", "Unknown error")
            error_code = data.get("error", {}).get("code", None)

            if error_code == 403:
                return "Authentication Error: Your account doesn't have permission to use geoenrichment services. This service may require a paid subscription or specific entitlements."
            else:
                return f"Error accessing geoenrichment service: {error_msg}"

        if not data.get("results") or not data["results"][0].get("value"):
            return "No enrichment data available for the specified locations."

        # Extract demographic data
        result_value = data["results"][0]["value"]

        # Check if we have feature sets
        if "FeatureSet" not in result_value or not result_value["FeatureSet"]:
            return "No demographic data was returned for this location."

        # Get the first feature set and its features
        feature_set = result_value["FeatureSet"][0]
        features = feature_set.get("features", [])

        if not features:
            return "No demographic features found for this location."

        # Format and output the results
        results = ["# Demographic Data"]

        # Process each feature (location)
        for i, feature in enumerate(features):
            attributes = feature.get("attributes", {})
            if not attributes:
                continue

            # Try to get location information if available
            geometry = feature.get("geometry", {})
            location_info = ""
            if geometry and "x" in geometry and "y" in geometry:
                location_info = f" ({geometry['y']}, {geometry['x']})"

            # Add header for this location
            if len(features) > 1:
                results.append(f"\n## Location {i + 1}{location_info}")
            else:
                results.append(f"**Location**: {location_info.strip()}")

            # Group data by category for better organization
            categories = {}
            for key, value in attributes.items():
                if (
                    key in ["OBJECTID", "ID", "apportionmentConfidence", "STDGEOID"]
                    or value is None
                ):
                    continue

                # Determine category based on field prefix
                if "_" in key:
                    prefix = key.split("_")[0]
                    category_map = {
                        "POP": "Population",
                        "AGE": "Age",
                        "INC": "Income",
                        "HOUSEHOLDS": "Households",
                        "HOUSING": "Housing",
                        "EDUCATION": "Education",
                        "HEALTH": "Health",
                        "RACE": "Demographics",
                        "EMPLOY": "Employment",
                    }
                    category = category_map.get(prefix, prefix)
                else:
                    category = "General"

                if category not in categories:
                    categories[category] = []

                # Format field name and value
                if "_" in key:
                    field_parts = key.split("_")[1:]
                    field_name = " ".join(field_parts)
                else:
                    field_name = key

                field_name = " ".join(word.capitalize() for word in field_name.split())

                # Format value based on type
                if isinstance(value, float):
                    if "PERCENT" in key or "PCT" in key or key.endswith("_P"):
                        formatted_value = f"{value:.2f}%"
                    else:
                        formatted_value = f"{value:,.2f}"
                elif isinstance(value, int):
                    formatted_value = f"{value:,}"
                else:
                    formatted_value = str(value)

                categories[category].append(f"**{field_name}**: {formatted_value}")

            # Add each category of attributes
            for category_name in sorted(categories.keys()):
                items = categories[category_name]
                if items:
                    if len(features) > 1:
                        results.append(f"\n### {category_name}")
                    else:
                        results.append(f"\n## {category_name}")
                    results.extend(sorted(items))

        return "\n".join(results)

    except Exception as e:
        # Return a more specific error message if possible
        if "JSONDecodeError" in str(e):
            return 'Error: Invalid JSON format for studyAreas parameter. Please use valid JSON with double quotes. Example: "[{\\"geometry\\":{\\"x\\":-117.1956,\\"y\\":34.0572}}]"'
        return format_error(e)


@mcp.tool()
async def get_elevation(
    lon: float = None,
    lat: float = None,
    coordinates: str = None,
    relativeTo: str = None,
) -> str:
    """Get elevation for locations on land or water.

    Args:
        lon: Longitude of a single point (e.g., -117.195)
        lat: Latitude of a single point (e.g., 34.065)
        coordinates: JSON array of [lon, lat] pairs for multiple points (e.g., "[[-117.182, 34.0555],[-117.185, 34.057]]")
        relativeTo: Reference point for elevation measurement (e.g., "meanSeaLevel", "ellipsoid")
    """
    # Single point elevation
    if lon is not None and lat is not None:
        url = f"{ELEVATION_URL}/at-point"
        params = {
            "lon": lon,
            "lat": lat,
            "f": "json",
        }
        if relativeTo:
            params["relativeTo"] = relativeTo

        try:
            data = await make_arcgis_request(url, params)

            if "error" in data:
                return f"Error retrieving elevation data: {data['error']['message']}"

            # Parse the nested result structure
            elevation_info = data.get("elevationInfo", {})
            result = data.get("result", {})
            point = result.get("point", {})

            # Extract elevation (z value)
            elevation = point.get("z")
            if elevation is None:
                return f"No elevation data available for location ({lat}, {lon})"

            # Get the reference datum
            reference = elevation_info.get("relativeTo", "meanSeaLevel")

            # Format the result
            result_lines = [
                "# Elevation Data",
                f"**Location**: {lat}, {lon}",
                f"**Elevation**: {elevation:,} meters {reference_to_readable(reference)}",
                f"**Datum**: {reference}",
            ]

            # Add spatial reference if available
            spatial_ref = point.get("spatialReference", {})
            if spatial_ref and "wkid" in spatial_ref:
                result_lines.append(
                    f"**Spatial Reference**: WKID {spatial_ref.get('wkid')}"
                )

            return "\n".join(result_lines)

        except Exception as e:
            return format_error(e)

    # Multiple points elevation
    elif coordinates:
        url = f"{ELEVATION_URL}/at-many-points"

        # Prepare request body
        body_params = {
            "coordinates": coordinates,
            "f": "json",
        }
        if relativeTo:
            body_params["relativeTo"] = relativeTo

        try:
            data = await make_arcgis_request(url, body_params, method="POST")

            if "error" in data:
                return f"Error retrieving elevation data: {data['error']['message']}"

            # Parse the nested result structure
            elevation_info = data.get("elevationInfo", {})
            result = data.get("result", {})
            points = result.get("points", [])

            # Get the reference datum
            reference = elevation_info.get("relativeTo", "meanSeaLevel")

            if not points:
                return "No elevation data returned for the specified coordinates."

            # Format the results
            result_lines = [
                "# Multiple Elevation Results",
                f"**Reference Datum**: {reference_to_readable(reference)}",
                f"**Points**: {len(points)}",
            ]

            # Add each point's elevation
            result_lines.append("\n## Point Elevations")

            for i, point in enumerate(points, 1):
                x = point.get("x")
                y = point.get("y")
                z = point.get("z")

                if z is None:
                    result_lines.append(
                        f"**Point {i}** ({y}, {x}): No elevation data available"
                    )
                    continue

                result_lines.append(f"**Point {i}** ({y}, {x}): {z:,} meters")

            # Calculate elevation profile stats
            if len(points) > 1:
                elevations = [p.get("z") for p in points if p.get("z") is not None]
                if elevations:
                    min_elev = min(elevations)
                    max_elev = max(elevations)
                    avg_elev = sum(elevations) / len(elevations)

                    result_lines.append("\n## Elevation Profile")
                    result_lines.append(f"**Minimum**: {min_elev:,} meters")
                    result_lines.append(f"**Maximum**: {max_elev:,} meters")
                    result_lines.append(f"**Average**: {avg_elev:,.1f} meters")
                    result_lines.append(
                        f"**Elevation Change**: {max_elev - min_elev:,} meters"
                    )

            return "\n".join(result_lines)

        except Exception as e:
            return format_error(e)
    else:
        return "Error: Either lon/lat or coordinates parameter must be provided."


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport="stdio")
