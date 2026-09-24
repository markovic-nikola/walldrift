#!/usr/bin/env bash
# Links the applet in this checkout into Cinnamon's applet folder and reloads it, so edits take
# effect without copying files. Run it again after each change.
set -euo pipefail

uuid=walldrift@markovic-nikola
src="$(cd "$(dirname "$0")/.." && pwd)/$uuid/files/$uuid"
dest="${XDG_DATA_HOME:-$HOME/.local/share}/cinnamon/applets/$uuid"

if [[ -e "$dest" && ! -L "$dest" ]]; then
    echo "$dest exists and is not a link; move it away first (it may be the Spices install)." >&2
    exit 1
fi
mkdir -p "$(dirname "$dest")"
ln -sfn "$src" "$dest"

dbus-send --session --dest=org.Cinnamon --type=method_call \
    /org/Cinnamon org.Cinnamon.ReloadXlet string:"$uuid" string:APPLET
echo "Linked $dest -> $src and reloaded it."
echo "Not on the panel yet? Right-click the panel > Applets > walldrift > Add to panel."
