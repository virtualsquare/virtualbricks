# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team

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

"""The TLS of the ssl sockets: the certificates of tests/data/tls."""

import os
import shutil

from OpenSSL import SSL
from twisted.internet import ssl
from twisted.python import failure
from twisted.trial import unittest

from virtualbricks.console import tls, wire
from virtualbricks.tests import DATA

TLS = os.path.join(DATA, "tls")


def data(name):
    return os.path.join(TLS, name)


class TestCertificates(unittest.TestCase):

    def unusable(self, function, *args):
        return str(self.assertRaises(wire.Unusable, function, *args))

    def test_a_certificate_and_its_key(self):
        certificate = tls.private_certificate(
            data("server.pem"), data("server.key")
        )
        self.assertEqual(certificate.getSubject().commonName, b"localhost")

    def test_one_file_for_both(self):
        path = os.path.join(self.mktemp())
        with open(path, "wb") as file:
            for name in ("alice.key", "alice.pem"):
                with open(data(name), "rb") as part:
                    file.write(part.read())
        certificate = tls.private_certificate(path, path)
        self.assertEqual(certificate.getSubject().commonName, b"alice")

    def test_files_that_dont_match(self):
        self.assertEqual(
            self.unusable(
                tls.private_certificate, data("server.pem"), data("bob.key")
            ),
            f"The key {data('bob.key')} isn't that of the certificate"
            f" {data('server.pem')}",
        )

    def test_not_pem(self):
        self.assertEqual(
            self.unusable(
                tls.private_certificate, data("README.md"), data("bob.key")
            ),
            f"{data('README.md')} isn't a certificate in PEM",
        )
        self.assertEqual(
            self.unusable(
                tls.private_certificate, data("bob.pem"), data("bob.pem")
            ),
            f"{data('bob.pem')} isn't a private key in PEM",
        )
        missing = data("nope.pem")
        self.assertEqual(
            self.unusable(tls.private_certificate, missing, missing),
            f"{missing} doesn't exist",
        )

    def test_chain(self):
        path = self.mktemp()
        with open(path, "wb") as file:
            for name in ("alice.pem", "bob.pem"):
                with open(data(name), "rb") as part:
                    file.write(part.read())
        self.assertEqual(len(tls.chain(path)), 2)
        self.assertEqual(
            self.unusable(tls.chain, data("README.md")),
            f"{data('README.md')} has no certificate in PEM",
        )


class TestTrusted(unittest.TestCase):

    def setUp(self):
        self.folder = os.path.abspath(self.mktemp())
        os.makedirs(self.folder)

    def unusable(self, folder):
        return str(self.assertRaises(wire.Unusable, tls.trusted, folder))

    def test_the_pem_files(self):
        for name in ("alice.pem", "README.md"):
            shutil.copy(data(name), self.folder)
        shutil.copy(data("bob.pem"), os.path.join(self.folder, "bob.PEM"))
        os.mkdir(os.path.join(self.folder, "old.pem"))
        names = [
            cert.getSubject().commonName for cert in tls.trusted(self.folder)
        ]
        self.assertEqual(names, [b"alice", b"bob"])

    def test_none(self):
        self.assertEqual(
            self.unusable(self.folder),
            f"{self.folder} has no .pem certificate",
        )
        shutil.copy(data("README.md"), os.path.join(self.folder, "x.pem"))
        self.assertEqual(
            self.unusable(self.folder),
            f"{os.path.join(self.folder, 'x.pem')} isn't a certificate in"
            " PEM",
        )

    def test_not_a_folder(self):
        self.assertEqual(
            self.unusable(data("alice.pem")),
            f"{data('alice.pem')} isn't a folder",
        )
        missing = os.path.join(self.folder, "nope")
        self.assertEqual(self.unusable(missing), f"{missing} doesn't exist")


class TestOptions(unittest.TestCase):

    def socket(self, **fields):
        socket = wire.parse_socket(
            f"ssl:8765:privateKey={data('server.key')}"
            f":certKey={data('server.pem')}"
        )
        return socket._replace(**fields)

    def test_options(self):
        options = tls.server_options(self.socket())
        self.assertIsInstance(options, ssl.CertificateOptions)
        self.assertFalse(options.verify)
        options = tls.server_options(self.socket(ca_dir=TLS))
        self.assertTrue(options.verify)
        self.assertTrue(options.requireCertificate)
        options = tls.server_options(self.socket(chain=data("alice.pem")))
        self.assertEqual(len(options.extraCertChain), 1)

    def test_a_file_that_cant_be_used(self):
        error = self.assertRaises(
            wire.Unusable,
            tls.server_options,
            self.socket(ca_dir=data("alice.pem")),
        )
        self.assertEqual(str(error), f"{data('alice.pem')} isn't a folder")


class TestTheLog(unittest.TestCase):

    def test_common_name(self):
        with open(data("alice.pem"), "rb") as file:
            certificate = ssl.Certificate.loadPEM(file.read())
        self.assertEqual(tls.common_name(certificate.original), "alice")
        self.assertIsNone(tls.common_name(None))

    def test_describe(self):
        error = SSL.Error([("SSL routines", "", "certificate verify failed")])
        self.assertEqual(
            tls.describe(failure.Failure(error)), "certificate verify failed"
        )
        self.assertEqual(
            tls.describe(failure.Failure(ConnectionError("reset"))), "reset"
        )
