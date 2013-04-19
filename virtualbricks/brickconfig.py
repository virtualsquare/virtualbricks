# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2013 Virtualbricks team

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

class BrickConfig(dict):
    """Generic configuration for Brick

    >>> cfg = BrickConfig()
    >>> cfg.enabled = True
    >>> cfg['enabled'] == True
    True
    >>> cfg.enabled == True
    True
    >>> cfg.disabled = True
    >>> cfg['disabled'] == True
    True
    >>> cfg.disabled == True
    True
    >>> from copy import deepcopy
    >>> cfg2 = deepcopy(cfg)
    """
    def __getattr__(self, name):
        """override dict.__getattr__"""
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        """override dict.__setattr__"""
        self[name] = value
        #Set value for running brick
        self.set_running(name, value)

    def set(self, attr):
        kv = attr.split("=")
        if len(kv) < 2:
            return False
        else:
            val = ''
            if len(kv) > 2:
                val = '"'
                for c in kv[1:]:
                    val += c.lstrip('"').rstrip('"')
                    val += "="
                val = val.rstrip('=') + '"'
            else:
                val += kv[1]
            #print "setting %s to '%s'" % (kv[0], val)
            self[kv[0]] = val
            #Set value for running brick
            self.set_running(kv[0], val)
            return True

    def set_obj(self, key, obj):
        self[key] = obj

    def set_running(self, key, value):
        """
        Set the value for the running brick,
        if available and running
        """
        import inspect
        stack = inspect.stack()
        frame = stack[2][0]
        caller = frame.f_locals.get('self', None)
        #if not isinstance(caller, Brick):
        #    return
        try:
            if not callable(caller.get_cbset):
                return
            callback = caller.get_cbset(key)
        except:
            return
        if callable(callback):
            #self.debug("Callback: setting value %s for key %s" %(value,key))
            callback(caller, value)
        #else: self.debug("callback not found for key: %s" % (key))

    def dump(self):
        keys = sorted(self.keys())
        for k in keys:
            print "%s=%s" % (k, self[k])
