# Run with bash inside the managed native dual image. Never signal a wrapper.
set -eu
[[ ${TRADING_MODE:-} = both && ${TWS_SETTINGS_PATH:-} = /sessions/settings ]]
launcher="$IBC_PATH/scripts/ibcstart.sh"
ini="${IBC_INI}_paper"
settings="${TWS_SETTINGS_PATH}_paper"

has_arg() {
    grep -Fzxq -- "$2" "/proc/$1/cmdline" 2>/dev/null
}

# Fast local signal only. Recovery still requires independent broker verification.
if [[ $1 = local-status ]]; then
    listeners=$(awk '$4 == "0A" {split($2, a, ":"); print a[length(a)]}' /proc/net/tcp /proc/net/tcp6)
    for mode in live paper; do
        port=0FA1; relay=0FA3
        if [[ $mode = paper ]]; then port=0FA2; relay=0FA4; fi
        java=none
        wrapper=$(cat "/tmp/pid_$mode" 2>/dev/null || true)
        if [[ $wrapper =~ ^[0-9]+$ && -r /proc/$wrapper/task/$wrapper/children ]]; then
            for pid in $(cat "/proc/$wrapper/task/$wrapper/children" 2>/dev/null); do
                if has_arg "$pid" "${IBC_INI}_$mode"; then java=$pid; break; fi
            done
        fi
        ports=closed
        if grep -Fxq "$port" <<< "$listeners" && grep -Fxq "$relay" <<< "$listeners"; then ports=open; fi
        echo "$mode $java $ports"
    done
    exit
fi

# Output only event classes and timestamps. The native per-session logs are private.
login_phase() {
    local log="/sessions/settings_$1/launcher.log"
    if [[ ! -r $log ]]; then
        if [[ ${2:-} = events ]]; then echo 'unknown - -'; else echo unknown; fi
        return
    fi
    LC_ALL=C awk -v events="${2:-}" '
        { stamp = ($1 ~ /^[0-9-]+$/ && $2 ~ /^[0-9:.]+$/) ? $1 "T" $2 : "-" }
        /SPLASH Authenticating|NS_AUTH_START / {phase="auth"; key=0}
        /Soft token=0 received instead of expected permanent|[Ww]eekly reauthentication required/ {phase="reauth"}
        /last used.*\[IB Key\]/ {phase="key"; key=1}
        /authenticated=true/ && key && /tokenProtocol=[1-9][0-9]*/ {key_time=stamp}
        /Authentication completed\.| - Authentication complete$/ {phase="complete"; login_time=stamp}
        END {
            printf "%s", phase ? phase : "unknown"
            if (events == "events") printf " %s %s", login_time ? login_time : "-", key_time ? key_time : "-"
            print ""
        }
    ' "$log"
}

wrapper_pids() {
    local p
    for p in $(pgrep -x ibcstart.sh || true); do
        if has_arg "$p" "$launcher" && has_arg "$p" "--ibc-ini=${IBC_INI}_$1" &&
           has_arg "$p" "--tws-settings-path=${TWS_SETTINGS_PATH}_$1"; then echo "$p"; fi
    done
}

java_pids() {
    local p
    for p in $(pgrep -x java || true); do
        if has_arg "$p" "ibcalpha.ibc.IbcGateway" && has_arg "$p" "${IBC_INI}_$1"; then echo "$p"; fi
    done
}

if [[ $1 = observe || $1 = observe-events ]]; then
    fields=
    if [[ $1 = observe-events ]]; then fields=events; fi
    for mode in live paper; do
        w=$(wrapper_pids "$mode")
        j=$(java_pids "$mode")
        process=ambiguous
        if [[ -z $j && -z $w ]]; then process=absent
        elif [[ $w =~ ^[0-9]+$ && -z $j ]]; then process=starting
        elif [[ $w =~ ^[0-9]+$ && $j =~ ^[0-9]+$ ]] &&
             [[ $(ps -o ppid= -p "$j" | tr -d ' ') = "$w" ]]; then process=running; fi
        echo "$mode $process $(login_phase "$mode" "$fields")"
    done
    exit
fi

[[ $1 = recover || $1 = history ]]
exec 9>/tmp/wheel-recover-paper.lock
flock -n 9
live=$(wrapper_pids live)
[[ $live =~ ^[0-9]+$ && $(cat /tmp/pid_live) = "$live" ]]
[[ $(ps -o ppid= -p "$live" | tr -d ' ') = 1 ]]
[[ $(java_pids live) =~ ^[0-9]+$ ]]
[[ -d $settings && -x $launcher && -r $ini ]]
grep -Eiq '^TradingMode=paper[[:space:]]*$' "$ini"
for key in IbLoginId IbPassword; do grep -Eiq "^$key=[^[:space:]]" "$ini"; done
wrapper=$(wrapper_pids paper)
java=$(java_pids paper)
# The native forwarding loop normally survives a Java exit. Repair only its
# Paper port when both the supervisor and its listener have disappeared.
if [[ $1 = recover && -z ${SSH_TUNNEL:-} && -x $SCRIPT_PATH/run_socat.sh ]]; then
    relay=false
    for pid in $(pgrep -x run_socat.sh || true); do
        if grep -Fzxq 'SOCAT_PORT=4004' "/proc/$pid/environ" 2>/dev/null; then relay=true; break; fi
    done
    if ! "$relay" && ! awk '$2 ~ /:0FA4$/ && $4 == "0A" {found=1} END {exit !found}' /proc/net/tcp /proc/net/tcp6; then
        TRADING_MODE=paper SOCAT_PORT=4004 API_PORT=4002 nohup setsid "$SCRIPT_PATH/run_socat.sh" \
            9>&- </dev/null >/proc/1/fd/1 2>/proc/1/fd/2 &
        # Restoring the listener alone can reconnect an otherwise healthy Gateway.
        if [[ $java =~ ^[0-9]+$ ]]; then exit; fi
    fi
fi

if [[ -z $java && -z $wrapper && $1 = recover ]]; then
    # An unrecognized listener may already own the internal Paper API.
    if awk '$2 ~ /:0FA2$/ && $4 == "0A" {found=1} END {exit !found}' /proc/net/tcp /proc/net/tcp6; then exit 1; fi
    [[ -n ${TWS_MAJOR_VRSN:-} && -n ${TWS_PATH:-} && ${TWOFA_TIMEOUT_ACTION:-} = exit ]]
    # PID 1 continues waiting on Live. Reuse IBC's private INI and settings.
    export DISPLAY=:1 TRADING_MODE=paper TWS_SETTINGS_PATH="$settings" IBC_INI="$ini"
    unset TWS_USERID TWS_PASSWORD TWS_PASSWORD_FILE TWS_USERID_PAPER TWS_PASSWORD_PAPER TWS_PASSWORD_PAPER_FILE
    nohup setsid "$launcher" "$TWS_MAJOR_VRSN" -g "--tws-path=$TWS_PATH" \
        "--ibc-path=$IBC_PATH" "--ibc-ini=$ini" "--on2fatimeout=$TWOFA_TIMEOUT_ACTION" \
        "--tws-settings-path=$settings" 9>&- </dev/null >/proc/1/fd/1 2>/proc/1/fd/2 &
    printf '%s\n' "$!" > /tmp/.wheel-pid-paper
    mv /tmp/.wheel-pid-paper /tmp/pid_paper
    exit
fi

[[ $wrapper =~ ^[0-9]+$ && $java =~ ^[0-9]+$ && $wrapper != "$live" ]]
[[ $(cat /tmp/pid_paper) = "$wrapper" ]]
[[ $(ps -o ppid= -p "$java" | tr -d ' ') = "$wrapper" ]]
has_arg "$java" "-DjtsConfigDir=$settings"
[[ $(login_phase paper) = complete ]]
token=$(tr '\0' '\n' < "/proc/$java/cmdline" | sed -n 's/^-Dibcsessionid=//p')
[[ $token =~ ^[a-zA-Z0-9_-]+$ ]]
touch "$settings/COLDRESTART$token"
has_arg "$java" "$ini"
has_arg "$java" "-Dibcsessionid=$token"
kill -TERM "$java"
