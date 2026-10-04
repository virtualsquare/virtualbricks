# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team

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

"""The key of a tunnel, made from its password, and its OpenSSL."""

import os
import shutil
import stat
import subprocess

from twisted.trial import unittest

from virtualbricks.bricks.tunnellisten import (
    OPENSSL_CONFIG,
    tunnel_key,
    write_key,
    write_openssl_config,
)


class TestKey(unittest.TestCase):

    def test_as_sha1sum_writes_it(self):
        # printf 'secret\n' | sha1sum, printf 'two words\n' | sha1sum
        self.assertEqual(
            tunnel_key("secret"),
            b"fc683cd9ed1990ca2ea10b84e5e6fba048c24929  -\n",
        )
        self.assertEqual(
            tunnel_key("two words"),
            b"01bc085da1fcbec2829f96ab9ad34b5b964d0fc4  -\n",
        )

    def test_written_for_its_owner_only(self):
        folder = os.path.join(os.path.abspath(self.mktemp()), "run")
        path = os.path.join(folder, "tl.key")
        write_key(path, "secret")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(folder).st_mode), 0o700)
        with open(path, "rb") as fp:
            self.assertEqual(fp.read(), tunnel_key("secret"))

    def test_rewritten(self):
        path = os.path.abspath(self.mktemp())
        with open(path, "w") as fp:
            fp.write("an older and longer key, readable by everyone\n")
        os.chmod(path, 0o644)
        write_key(path, "secret")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        with open(path, "rb") as fp:
            self.assertEqual(fp.read(), tunnel_key("secret"))


class TestOpenSSL(unittest.TestCase):

    def test_written(self):
        folder = os.path.join(os.path.abspath(self.mktemp()), "run")
        path = os.path.join(folder, "tl.openssl.cnf")
        write_openssl_config(path)
        self.assertEqual(stat.S_IMODE(os.stat(folder).st_mode), 0o700)
        with open(path) as fp:
            self.assertEqual(fp.read(), OPENSSL_CONFIG)

    def test_blowfish(self):
        # the cipher of vde_cryptcab, which OpenSSL 3 has in its legacy
        # provider only
        openssl = shutil.which("openssl")
        if openssl is None:
            raise unittest.SkipTest("openssl isn't installed")
        path = os.path.abspath(self.mktemp())
        write_openssl_config(path)
        done = subprocess.run(
            [openssl, "enc", "-bf-cbc", "-e"]
            + ["-K", "00" * 16, "-iv", "00" * 8],
            input=b"a frame of a switch",
            env=dict(os.environ, OPENSSL_CONF=path),
            capture_output=True,
        )
        self.assertEqual(done.returncode, 0, done.stderr.decode())
