#!/bin/bash
# Opens iTerm2, Ghostty, and WezTerm each in a row on screen,
# cd to ~/dev/dirplot and runs: uv run dirplot --inline --log src

CMD='cd ~/dev/dirplot && uv run dirplot --inline --log src'

# Get usable screen bounds from Finder (excludes Dock)
BOUNDS=$(osascript -e '
tell application "Finder"
    set b to bounds of window of desktop
    set x1 to item 1 of b
    set y1 to item 2 of b
    set x2 to item 3 of b
    set y2 to item 4 of b
    return (x1 as string) & "," & (y1 as string) & "," & (x2 as string) & "," & (y2 as string)
end tell')

IFS=',' read -r SX SY SR SB <<< "$BOUNDS"
MENU_BAR=38
SY=$((SY + MENU_BAR))
SCREEN_W=$((SR - SX))
SCREEN_H=$((SB - SY))
COL_W=$((SCREEN_W / 3))

X0=$SX;          R0=$((X0 + COL_W))
X1=$((SX+COL_W)); R1=$((X1 + COL_W))
X2=$((SX+COL_W*2)); R2=$((X2 + COL_W))
Y=$SY
BOT=$((Y + SCREEN_H))

# --- iTerm2 (left) ---
osascript <<EOF
tell application "iTerm2"
    activate
    set w to (create window with default profile)
    tell current session of w
        set columns to 80
        set rows to 25
        write text "$CMD"
    end tell
    set bounds of w to {$X0, $Y, $R0, $BOT}
end tell
EOF

# --- Ghostty (middle) ---
/Applications/Ghostty.app/Contents/MacOS/ghostty -e bash -ic "$CMD; exec bash" &
osascript <<EOF
tell application "System Events"
    tell process "Ghostty"
        repeat while (count of windows) is 0
            delay 0.3
        end repeat
        set bounds of window 1 to {$X1, $Y, $R1, $BOT}
    end tell
end tell
EOF

# --- WezTerm (right) ---
wezterm start -- bash -ic "$CMD; exec bash" &
osascript <<EOF
tell application "WezTerm" to activate
tell application "System Events"
    tell process "wezterm-gui"
        repeat while (count of windows) is 0
            delay 0.3
        end repeat
        set position of window 1 to {$X2, $Y}
        set size of window 1 to {$COL_W, $SCREEN_H}
    end tell
end tell
EOF
