# Tool: model_route
Route a model request to the correct engine seat.
## Inputs
- work_class (str): one of the classes in workflows/model-routing.md
- prompt / messages
## Outputs
- model response
## Invoke
- Pick seat from routing table; call via Hermes provider config or scripts/<provider>.py
## Verify
- Response matches expected schema; non-empty; no error markers.
