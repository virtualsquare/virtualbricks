# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

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
    print (sys.argv, pidfile, i)
    if pidfile:
        with open(pidfile, "w") as fp:
            fp.write(str(os.getpid()))
    time.sleep(int(sys.argv[i]))
