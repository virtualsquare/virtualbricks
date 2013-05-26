import os
import sys
import time


if __name__ == "__main__":
    pidfile = None
    i = 0
    t = 0
    for i in range(1, len(sys.argv)):
        if sys.argv[i] == "-P":
            pidfile = sys.argv[i+1]
            break
        else:
            t = int(sys.argv[i])
    if pidfile:
        with open(pidfile, "w") as fp:
            fp.write(str(os.getpid()))
    time.sleep(t)
