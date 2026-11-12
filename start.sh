#!/bin/sh
# Start the presenter from any working directory; forward app.py options.
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'Python 3.10 or newer is required. Install Python and run this script again.' >&2
    exit 1
fi

cd "$project_dir"
exec python3 app.py "$@"
