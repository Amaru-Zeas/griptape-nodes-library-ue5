# GTN LatLong Geo Library

Single-node geo workflow for Griptape Nodes:
- Search by place/street/city
- Search by latitude/longitude
- Switch between Google Earth, Google Maps, and Street View
- Embed the viewer directly inside the node widget

## Included Node

### Geo Explorer
- Inputs:
  - `search_query` (street, city, place name, or `lat,lng`)
  - `latitude`, `longitude` (fallback coordinates)
  - `mode` (`earth`, `map`, `street_view`)
- Outputs:
  - `resolved_latitude`, `resolved_longitude`
  - `formatted_address`
  - `earth_url`, `map_url`, `street_view_url`
  - `current_url`, `viewer`, `status`
  - capture outputs are standardized to `16:9` (`1280x720`) for clean downstream image usage

### Street View Capture
- Strict capture node for Street View only (no map fallback).
- Inputs:
  - `latitude`, `longitude` (connect from `Geo Explorer.resolved_latitude/longitude`)
  - optional camera controls: `heading`, `pitch`, `fov`
- Outputs:
  - `streetview_image` (`ImageArtifact`) for image connectors
  - `captured_image_path`, `captured_image_url`
  - `status`

## API Key / Secrets

The library registers:
- `GOOGLE_MAPS_API_KEY`

Set it in GTN `API Keys & Secrets` once, then leave `api_key` empty in the node.

When a key is present, geocoding uses Google Geocoding API.
If a key is missing, the node falls back to OpenStreetMap Nominatim for text geocoding.

## Add Library in GTN

1. Open GTN Settings -> Libraries.
2. Add:
   - `a:\GriptapeSketchFab\griptape-nodes-library-latlong\latlong_nodes\griptape_nodes_library.json`
3. Refresh libraries.
4. Add `Geo Explorer` node to your graph.

## Notes

- Google pages can change iframe policies at any time. If a specific Earth/Street URL does not render in-iframe, use the corresponding output URL in a browser tab.
- For highest accuracy with addresses and streets, provide `GOOGLE_MAPS_API_KEY`.

