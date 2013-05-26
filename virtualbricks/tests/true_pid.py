import os
import sys
import time

if __name__ == "__main__":
    pidfile = None
    i = 0
    for i in range(1, len(sys.argv)):
        if sys.argv[i] == "-P":
            pidfile = sys.argv[i+1]
            i += 2
            break
    print sys.argv, pidfile, i
    if pidfile:
        with open(pidfile, "w") as fp:
            fp.write(str(os.getpid()))
    time.sleep(int(sys.argv[i]))
