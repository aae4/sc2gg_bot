case "$1" in
  start)
    echo "Starting sc2gg_bot: "
    nohup python3.10 -u './main.py' > "${1%.*}.log" 2>&1 < /dev/null &
    echo "done."
  ;;
  stop)
    echo -n "Stopping sc2gg_bot: "
    ps -ef | grep "./main.py" | grep -v grep | awk '{print $2}' | xargs kill
    echo "process killed"
    echo "done."
  ;;
  *)
    N=./bot_runner
    echo "Usage: $N {start|stop}" >&2
    exit 1
  ;;
esac

mynohup () {
  [[ "$1" = "" ]] && echo "usage: mynohup python_script" && return 0
  nohup python3.10 -u "$1" > "${1%.*}.log" 2>&1 < /dev/null &
}

mykill() {
  ps -ef | grep "$1" | grep -v grep | awk '{print $2}' | xargs kill
  echo "process "$1" killed"
}
