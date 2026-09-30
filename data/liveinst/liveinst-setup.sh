#!/bin/bash
# Set up a launcher on the desktop for the live installer if we're on
# a live CD

if [ ! -b /dev/mapper/live-base ] && [ ! -b /dev/mapper/live-osimg-min ]; then
    exit 0
fi

# Prevents breakage if the hostname is changed before or during the install
# Also lets us run (with the X11 backend) on Wayland
[ -x /usr/bin/xhost ] && xhost +si:localuser:root > /dev/null 2>&1

test -f "${XDG_CONFIG_HOME:-~/.config}"/user-dirs.dirs && source "${XDG_CONFIG_HOME:-~/.config}"/user-dirs.dirs
DESKTOP_FILE="${XDG_DESKTOP_DIR:-$HOME/Desktop}/liveinst.desktop"
cp /usr/share/applications/liveinst.desktop "$DESKTOP_FILE"
# On Plasma the launcher has to be executable, otherwise the user gets
# asked whether the file should really be run.
chmod +x "$DESKTOP_FILE"

# Make the Plasma Welcome Center start in the live environment and point it
# to the installer. The configuration is written to the home directory of the
# live user only, so it never leaks into the installed system.
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"

if [ -x /usr/bin/plasma-welcome ] && [ ! -e "$CONFIG_DIR/plasma-welcomerc" ]; then
    mkdir -p "$CONFIG_DIR"
    cat > "$CONFIG_DIR/plasma-welcomerc" << EOF
[General]
LiveEnvironment=true
LiveInstaller=liveinst
EOF
fi
