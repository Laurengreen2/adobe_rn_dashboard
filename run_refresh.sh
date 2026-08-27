#!/bin/bash
# Silent background runner for refresh_dashboard.py
# Launched by launchd — no Claude Code involvement.
# Reads ANTHROPIC_API_KEY from ~/.anthropic_api_key (one-time setup).

KEY_FILE="$HOME/.anthropic_api_key"
if [ ! -f "$KEY_FILE" ]; then
    echo "$(date): ERROR — $KEY_FILE not found. Create it with your API key." >&2
    exit 1
fi

export ANTHROPIC_API_KEY
ANTHROPIC_API_KEY=$(cat "$KEY_FILE")

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "$(date): ERROR — $KEY_FILE is empty." >&2
    exit 1
fi

REPO="/Users/lauren.m.pellegrini/Library/CloudStorage/OneDrive-Accenture/Desktop/Claude Dashboard Files/Adobe RN Dashboard"

echo "$(date): Starting dashboard refresh..."
cd "$REPO" || exit 1

/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 refresh_dashboard.py
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "$(date): Refresh completed successfully."
else
    echo "$(date): Refresh FAILED with exit code $EXIT_CODE." >&2
fi

exit $EXIT_CODE
